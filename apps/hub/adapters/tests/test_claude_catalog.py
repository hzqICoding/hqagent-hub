import asyncio
import json
from types import SimpleNamespace

import pytest

from adapters import claude_catalog as catalog
from adapters.claude_adapter import ClaudeAdapter


class Runner:
    def __init__(self, rows=None, mode='success'):
        self.mode = mode
        self.rows = rows if rows is not None else [
            {'value': 'default', 'resolvedModel': 'runtime-model', 'displayName': 'Default',
             'supportsEffort': True, 'supportedEffortLevels': ['low', 'max']},
            {'value': 'custom[1m]', 'displayName': 'Custom'},
        ]
        self.closed = False
        self.requests = []

    def find(self, _name):
        return None if self.mode == 'missing' else 'claude.exe'

    async def start(self, args, *, cwd, env):
        self.args, self.cwd, self.env = args, cwd, env
        stdout, stderr = asyncio.StreamReader(), asyncio.StreamReader()
        self.process = SimpleNamespace(stdout=stdout, stderr=stderr)
        def write(data):
            request = json.loads(data)
            self.requests.append(request)
            if self.mode == 'timeout':
                return
            response = {'type': 'control_response', 'response': {'request_id': request['request_id'],
                'subtype': 'success', 'response': {'models': self.rows, 'account': {'secret': 'DO_NOT_LEAK'}}}}
            if self.mode == 'malformed':
                stdout.feed_data(b'invalid\n')
            elif self.mode == 'eof':
                stdout.feed_eof()
            else:
                stdout.feed_data((json.dumps(response) + '\n').encode())
        async def drain():
            pass
        self.process.stdin = SimpleNamespace(write=write, drain=drain)
        return self.process


def prepare(monkeypatch, runner):
    monkeypatch.setattr(catalog, 'command_environment', lambda _: {'HTTPS_PROXY': 'test-proxy'})
    async def terminate(process):
        assert process is runner.process
        runner.closed = True
    monkeypatch.setattr(catalog, 'terminate_process_tree', terminate)


def test_runtime_catalog_alias_effort_and_cleanup(monkeypatch):
    runner = Runner()
    prepare(monkeypatch, runner)
    result = asyncio.run(ClaudeAdapter(runner=runner).list_models('local.claude.default'))
    assert result.verified
    assert [m.id for m in result.models] == ['default', 'custom[1m]']
    assert result.models[0].efforts == ['low', 'max']
    assert result.models[0].is_default
    assert result.models[1].efforts == []
    assert 'runtime-model' in result.models[0].name
    assert runner.closed and len(runner.requests) == 1
    assert runner.requests[0]['request'] == {'subtype': 'initialize'}
    assert '--no-session-persistence' in runner.args and '--safe-mode' in runner.args
    assert runner.args[-2:] == ['--tools', '']
    assert runner.env['HTTPS_PROXY'] == 'test-proxy'
    assert 'DO_NOT_LEAK' not in result.model_dump_json()


@pytest.mark.parametrize('mode', ['missing', 'malformed', 'eof', 'timeout'])
def test_unavailable_is_explicit_and_does_not_invent_models(monkeypatch, mode):
    runner = Runner(mode=mode)
    prepare(monkeypatch, runner)
    monkeypatch.setattr(catalog, 'CATALOG_TIMEOUT_SECONDS', 0.02)
    result = asyncio.run(catalog.query_models(runner, 'claude'))
    assert not result.verified and result.models == [] and result.reason
    assert mode == 'missing' or runner.closed


@pytest.mark.parametrize('rows', [[], None, [{}], [{'value': 'a', 'supportsEffort': True,
    'supportedEffortLevels': 'high'}], [{'value': 'a'}, {'value': 'a'}]])
def test_invalid_catalog_rejected(rows):
    with pytest.raises(ValueError):
        catalog._models(rows)


def test_cancellation_cleans_process(monkeypatch):
    runner = Runner(mode='timeout')
    prepare(monkeypatch, runner)
    async def run():
        task = asyncio.create_task(catalog.query_models(runner, 'claude'))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert runner.closed
