"""Read Claude's runtime model catalog without sending a user/model turn."""
from __future__ import annotations

import asyncio
import json
import tempfile
import uuid

from protocol.generated.python import LocalAgentModel, LocalAgentModelsView
from adapters.process import command_environment, executable_args, terminate_process_tree

CATALOG_TIMEOUT_SECONDS = 20
MAX_CATALOG_BYTES = 2 * 1024 * 1024


def _models(rows: object) -> list[LocalAgentModel]:
    if not isinstance(rows, list) or not rows:
        raise ValueError('Missing runtime model catalog')
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid model entry')
        model_id = row.get('value')
        name = row.get('displayName') or model_id
        if not isinstance(model_id, str) or not model_id.strip() or not isinstance(name, str):
            raise ValueError('Invalid model identity')
        if model_id in seen:
            raise ValueError('Duplicate model identity')
        seen.add(model_id)
        # CLI aliases and suffixes are executable selections; resolvedModel is
        # display information, not a replacement for the CLI's model value.
        resolved = row.get('resolvedModel')
        if isinstance(resolved, str) and resolved != model_id:
            name = f'{name} · {resolved}'
        efforts = row.get('supportedEffortLevels', []) if row.get('supportsEffort') is True else []
        if not isinstance(efforts, list) or any(not isinstance(e, str) or not e.strip() for e in efforts):
            raise ValueError('Invalid effort catalog')
        result.append(LocalAgentModel(id=model_id, name=name, efforts=list(dict.fromkeys(efforts)),
                                      is_default=model_id == 'default'))
    return result


async def _discard(stream) -> None:
    # Drain stderr without buffering or exposing credentials/diagnostics.
    while await stream.read(8192):
        pass


async def query_models(runner, agent_instance_id: str) -> LocalAgentModelsView:
    process = None
    stderr_task = None
    try:
        executable = runner.find('claude')
        if not executable:
            return LocalAgentModelsView(agent_instance_id=agent_instance_id, models=[], verified=False,
                                        reason='Claude未安装')
        with tempfile.TemporaryDirectory(prefix='hqagent-claude-catalog-') as directory:
            try:
                async with asyncio.timeout(CATALOG_TIMEOUT_SECONDS):
                    process = await runner.start(executable_args(executable, '--safe-mode', '--print',
                        '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose',
                        '--no-session-persistence', '--permission-mode', 'dontAsk', '--tools', ''),
                        cwd=directory, env=command_environment('claude'))
                    if process.stderr is not None:
                        stderr_task = asyncio.create_task(_discard(process.stderr))
                    request_id = uuid.uuid4().hex
                    process.stdin.write((json.dumps({'type': 'control_request', 'request_id': request_id,
                        'request': {'subtype': 'initialize'}}) + '\n').encode())
                    await process.stdin.drain()
                    received = 0
                    while True:
                        line = await process.stdout.readline()
                        if not line:
                            raise ValueError('Runtime exited before catalog response')
                        received += len(line)
                        if received > MAX_CATALOG_BYTES:
                            raise ValueError('Catalog response exceeds limit')
                        event = json.loads(line)
                        if not isinstance(event, dict) or event.get('type') != 'control_response':
                            continue
                        response = event.get('response')
                        if not isinstance(response, dict) or response.get('request_id') != request_id:
                            continue
                        if response.get('subtype') != 'success':
                            raise ValueError('Runtime rejected catalog initialization')
                        payload = response.get('response')
                        if not isinstance(payload, dict):
                            raise ValueError('Invalid initialization response')
                        return LocalAgentModelsView(agent_instance_id=agent_instance_id,
                            models=_models(payload.get('models')), verified=True,
                            reason='来自本机Claude运行时目录；不代表已逐个验证当前账号或代理的调用权限')
            finally:
                if process is not None:
                    await terminate_process_tree(process)
                if stderr_task is not None:
                    stderr_task.cancel()
                    await asyncio.gather(stderr_task, return_exceptions=True)
    except (OSError, ValueError, RuntimeError, TimeoutError, AttributeError):
        return LocalAgentModelsView(agent_instance_id=agent_instance_id, models=[], verified=False,
            reason='Claude模型目录查询失败或当前版本不支持；请检查安装与配置，仍可手动填写。未切换代理或使用替代模型')
