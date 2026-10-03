"""Manage local browser access without restarting an active Worker."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from http.client import HTTPConnection
import json
import sys
from pathlib import Path

from protocol.generated.python import LocalConnectionCodeView
from runtime.paths import HubPaths


def _operator_request(data_dir: Path | None, endpoint: str) -> tuple[str, dict]:
    descriptor = json.loads((HubPaths.resolve(data_dir).runtime / 'hub.json').read_text(encoding='utf-8'))
    port, token = descriptor['port'], descriptor['token']
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535 or not isinstance(token, str) or not token:
        raise ValueError('Invalid local descriptor')
    # Never send the operator credential through an env proxy or a redirect, and
    # do not trust a descriptor-supplied remote baseUrl.
    connection = HTTPConnection('127.0.0.1', port, timeout=10)
    try:
        connection.request('POST', endpoint, body=b'{}',
                           headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError('Local renewal refused')
        result = json.loads(response.read())
        if result.get('success') is not True:
            raise ValueError('Local renewal failed')
        return f'http://127.0.0.1:{port}/connect', result['data']
    finally:
        connection.close()


def renew_code(data_dir: Path | None = None) -> tuple[str, LocalConnectionCodeView]:
    url, data = _operator_request(data_dir, '/internal/auth/connection-code')
    return url, LocalConnectionCodeView.model_validate(data)


def revoke_sessions(data_dir: Path | None = None) -> None:
    _, data = _operator_request(data_dir, '/internal/auth/revoke-sessions')
    if data.get('revoked') is not True:
        raise ValueError('Local revocation failed')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--revoke-sessions', action='store_true',
                        help='撤销所有本机浏览器会话（需要 Hub 正在运行）')
    args = parser.parse_args()
    if args.revoke_sessions:
        try:
            revoke_sessions(args.data_dir)
        except Exception:
            raise SystemExit('无法撤销会话，请确认 Hub 正在运行且当前用户可读取本机运行信息。') from None
        print('已撤销所有本机浏览器会话；下次访问需重新输入连接码。')
        return
    if not sys.stdout.isatty():
        raise SystemExit('连接短码只在交互终端显示，请使用 SSH -t，勿重定向到日志。')
    try:
        url, code = renew_code(args.data_dir)
    except Exception:
        raise SystemExit('无法续发连接码，请确认Worker正在运行且当前用户可读取本机运行信息。') from None
    deadline = datetime.now().astimezone() + timedelta(seconds=code.expires_in_seconds)
    print('Local page:', url)
    print('Local connection code (one use):', code.code)
    print('Valid until:', deadline.strftime('%Y-%m-%d %H:%M:%S %z'))


if __name__ == '__main__':
    main()
