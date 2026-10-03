"""Local operator CLI. All mutations use authenticated Hub HTTP APIs."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import socket
import sys
import time
from urllib.parse import quote
import uuid

from protocol.generated.python import HubRuntimeDescriptor, RemoteLinkView, LocalAuthorizedRootsView
from runtime.paths import HubPaths
from runtime.remote.security import safe_text


class CLIError(Exception):
    pass


class LocalClient:
    def __init__(self, data_dir=None):
        try:
            path = HubPaths.resolve(data_dir).runtime / 'hub.json'
            info = path.stat()
            if os.name != 'nt' and (info.st_uid != os.getuid() or info.st_mode & 0o077):
                raise ValueError()
            descriptor = HubRuntimeDescriptor.model_validate_json(path.read_text(encoding='utf-8'))
            self.port, self.token = (descriptor.port, descriptor.token)
        except Exception:
            raise CLIError('无法读取安全的本机 descriptor，请确认当前用户的 Hub 已启动。') from None

    def request(self, method, path, value=None):
        # Never trust baseUrl, proxies or redirects with the operator token.
        connection = HTTPConnection('127.0.0.1', self.port, timeout=15)
        try:
            body = json.dumps(value if value is not None else {}).encode()
            connection.request(
                method,
                path if path.startswith('/internal/') else '/api/v1' + path,
                body=body if method != 'GET' else None,
                headers={
                    'Authorization': 'Bearer ' + self.token,
                    'Content-Type': 'application/json',
                    'Origin': f'http://127.0.0.1:{self.port}',
                    'Idempotency-Key': str(uuid.uuid4()),
                },
            )
            response = connection.getresponse()
            raw = response.read(4 * 1024 * 1024 + 1)
            if not 200 <= response.status < 300 or len(raw) > 4 * 1024 * 1024:
                raise CLIError('本机 API 拒绝请求，请通过 Hub 状态核对原因。')
            envelope = json.loads(raw)
            if envelope.get('success') is not True:
                raise CLIError('本机 API 操作未完成。')
            return envelope['data']
        except CLIError:
            raise
        except Exception:
            raise CLIError('本机 API 不可达或响应无效。') from None
        finally:
            connection.close()


def printable(value, token=''):
    if isinstance(value, dict):
        return {
            k: printable(v, token)
            for k, v in value.items()
            if not any(
                part in k.lower()
                for part in ('secret', 'token', 'authorization', 'paircode', 'pairrequestid')
            )
        }
    if isinstance(value, list):
        return [printable(v, token) for v in value]
    if isinstance(value, str):
        return safe_text(value, (token,)).replace('\x1b', '').replace('\x00', '')
    return value


def pair(client, server, device, out, *, sleep=time.sleep):
    import segno

    if not out.isatty():
        raise CLIError('配对短码和二维码只在交互终端显示；请使用 SSH -t，勿重定向到日志。')
    view = RemoteLinkView.model_validate(
        client.request('POST', '/remote/pairing', {'serverOrigin': server, 'deviceName': device})
    ).model_dump(mode='json', by_alias=True, exclude_none=True)
    if view['state'] == 'paired':
        print('已配对。', file=out)
        return
    if view['state'] != 'pairing':
        raise CLIError('配对未开始，请检查本机 remote status。')
    code = view['pairCode']
    url = view['serverOrigin'].rstrip('/') + '/remote/pair#code=' + quote(code, safe='')
    request = view['pairRequestId']
    try:
        segno.make(url, micro=False).terminal(out=out, compact=True)
        print('配对短码:', code, file=out)
        print('有效期至:', view['expiresAt'], file=out, flush=True)
        while datetime.now(timezone.utc) < datetime.fromisoformat(view['expiresAt'].replace('Z', '+00:00')):
            state = RemoteLinkView.model_validate(
                client.request('GET', '/remote/link')
            ).model_dump(mode='json', by_alias=True, exclude_none=True)
            if state['state'] == 'paired':
                print('配对完成。', file=out)
                return
            if state['state'] != 'pairing' or state['pairRequestId'] != request:
                raise CLIError('配对已结束或已更换，请重新发起。')
            sleep(1)
        raise CLIError('配对已过期，请重新发起。')
    except KeyboardInterrupt:
        current = client.request('GET', '/remote/link')
        if current.get('state') == 'pairing' and current.get('pairRequestId') == request:
            client.request('DELETE', '/remote/pairing')
        raise CLIError('已取消本次配对。') from None


def parser():
    result = argparse.ArgumentParser(description='HQAgent-Hub 本机运维 CLI')
    result.add_argument('--data-dir', type=Path)
    groups = result.add_subparsers(dest='group', required=True)
    remote = groups.add_parser('remote').add_subparsers(dest='action', required=True)
    pairing = remote.add_parser('pair')
    pairing.add_argument('--server', required=True)
    pairing.add_argument('--device-name', default=socket.gethostname())
    remote.add_parser('status')
    remote.add_parser('unlink')
    resync = remote.add_parser('resync', help='修复同步冲突：清理云端副本并从本机完整重建')
    resync.add_argument('--confirm-reset', action='store_true', required=True,
                        help='确认云端副本在补传完成前暂时不完整')
    workspace = groups.add_parser('workspace').add_subparsers(dest='action', required=True)
    workspace.add_parser('add').add_argument('path', type=Path)
    workspace.add_parser('list')
    agents = groups.add_parser('agents').add_subparsers(dest='action', required=True)
    agents.add_parser('discover')
    verify = agents.add_parser('verify-image', help='显式调用真实模型验证图片输入，会产生模型用量')
    verify.add_argument('--agent', choices=('claude', 'codex'), required=True)
    verify.add_argument('--model')
    roots = groups.add_parser('roots').add_subparsers(dest='action', required=True)
    roots.add_parser('list')
    roots.add_parser('add').add_argument('path', type=Path)
    roots.add_parser('remove').add_argument('id')
    return result


def execute(args, client, out):
    if args.group == 'remote':
        if args.action == 'resync':
            data = client.request('POST', '/internal/remote/resync')
            print(json.dumps(data, ensure_ascii=False), file=out)
            return
        if args.action == 'pair':
            return pair(client, args.server, args.device_name, out)
        data = client.request(
            'GET' if args.action == 'status' else 'POST',
            '/remote/link' if args.action == 'status' else '/remote/unlink',
        )
    elif args.group == 'workspace':
        data = (
            client.request('GET', '/workspaces')
            if args.action == 'list'
            else client.request('POST', '/workspaces', {'path': str(args.path.expanduser().resolve())})
        )
    elif args.group == 'agents':
        data = client.request('POST', '/agents/discovery')
        if args.action == 'verify-image':
            from runtime.attachments.verification import verify_images
            record = asyncio.run(verify_images(HubPaths.resolve(args.data_dir).root, args.agent, args.model))
            data = {k: record[k] for k in ('agent', 'version', 'model', 'observedAt', 'passed', 'probes', 'diagnostics')}
    else:
        data = LocalAuthorizedRootsView.model_validate(
            client.request('GET', '/remote/authorized-roots')
        ).model_dump(mode='json', by_alias=True)
        if args.action != 'list':
            roots = [{k: v for k, v in r.items() if k != 'version'} for r in data['roots']]
            if args.action == 'add':
                path = args.path.expanduser().resolve()
                roots.append({'path': str(path), 'displayName': path.name or 'Root'})
            else:
                if not any((r['rootId'] == args.id for r in roots)):
                    raise CLIError('授权根 ID 不存在。')
                roots = [r for r in roots if r['rootId'] != args.id]
            data = client.request(
                'PUT', '/remote/authorized-roots', {'expectedVersion': data['version'], 'roots': roots}
            )
    print(json.dumps(printable(data, getattr(client, 'token', '')), ensure_ascii=False, indent=2), file=out)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        execute(args, LocalClient(args.data_dir), sys.stdout)
    except CLIError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print('操作未完成；请核对本机 Hub 状态。', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
