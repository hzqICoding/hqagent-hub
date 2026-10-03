import asyncio
import json

import pytest

from adapters.history import FileHistory, digest
from adapters.history_index import HistoryIndex
from remote_support import System
from test_r3_native import fixture_history, setup_native


@pytest.mark.parametrize('agent,version', [
    ('codex', '0.98.0'), ('codex', '0.111.0'), ('codex', '0.159.2'), ('codex', '0.160.0'),
    ('claude', '2.1.251'), ('claude', '2.1.288'), ('claude', '2.2.0')])
@pytest.mark.parametrize('damage,field', [('missing', 'content'), ('text', 'text'), ('role', 'role'), ('channel', 'channel')])
def test_old_current_and_future_fail_closed_with_specific_structural_reason(tmp_path, agent, version, damage, field):
    root = tmp_path / 'records'
    path = fixture_history(root, tmp_path, agent, version=version)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    message = rows[1]['payload'] if agent == 'codex' else rows[0]['message']
    if damage == 'missing':
        message.pop('content')
    elif damage == 'text':
        message['content'] = [{'type': 'text', 'text': {'private': 'PRIVATE_SENTINEL'}}]
    elif damage == 'role':
        message['role'] = 'PRIVATE_SENTINEL'
    else:
        message['channel'] = 'PRIVATE_SENTINEL'
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    reader = FileHistory(agent, root)
    source = reader.inspect(path)
    assert not source.readable and not source.messages
    assert field in source.reason and 'PRIVATE_SENTINEL' not in source.reason
    assert '尚未验证' not in source.reason


@pytest.mark.parametrize('agent,version', [('codex', '0.160.0'), ('claude', '2.2.0')])
def test_future_version_index_diagnostics_persist_and_append_still_validates(tmp_path, agent, version):
    async def scenario():
        system = System(tmp_path)
        try:
            root = tmp_path / 'records'
            path = fixture_history(root, tmp_path, agent, version=version, text='visible sk-SECRETKEY')
            native = setup_native(system, root, agent)
            await native.scan()
            item = (await native.listing()).items[0]
            assert item.format.status == 'readable'
            assert item.format.reason == FileHistory.compatible_reason
            reader = native.plugins[0]
            index = native.index_for(reader)
            assert FileHistory.compatible_reason in reader.capabilities()['versionDiagnostics'][-1]
            assert 'SECRETKEY' not in (await native.read(item.native_session_id)).model_dump_json()
            # New instance uses persisted index without parsing, but restores diagnostics.
            restarted = FileHistory(agent, root, runtime_id=reader.runtime_id)
            restored = HistoryIndex(restarted, native.index_repository)
            entry = restored.refresh(path)
            assert restored.parsed_bytes == 0
            assert FileHistory.compatible_reason in restarted.capabilities()['versionDiagnostics'][-1]
            assert restored.source(entry).readable
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            broken = rows[1] if agent == 'codex' else {**rows[1], 'uuid': 'new', 'parentUuid': '1'}
            message = broken['payload'] if agent == 'codex' else broken['message']
            message['content'] = [{'type': 'text', 'text': 4}]
            with path.open('a') as stream:
                stream.write(json.dumps(broken) + '\n')
            await native.scan()
            item = (await native.listing()).items[0]
            assert item.format.status == 'unsupported' and 'text' in item.format.reason
        finally:
            await system.close()
    asyncio.run(scenario())


class LegacyReader(FileHistory):
    verified_series = {'codex': (0, 153, 4), 'claude': (2, 1, 261)}
    structure_version = 'structures-v2'
    version_policy = 'verified-series-minimum-patch-and-record-structure'

    def verified_version(self, version):
        value = self.version_tuple(version)
        minimum = self.verified_series[self.agent_type]
        return value is not None and value[:2] == minimum[:2] and value[2] >= minimum[2]

    def version_rejection(self, version):
        return '' if self.verified_version(version) else '该 CLI 版本尚未验证'


@pytest.mark.parametrize('agent,version', [('codex', '0.111.0'), ('codex', '0.159.2'), ('claude', '2.1.251')])
def test_legacy_persistent_unsupported_index_recomputed_after_restart(tmp_path, agent, version):
    async def scenario():
        system = System(tmp_path)
        try:
            root = tmp_path / 'records'
            path = fixture_history(root, tmp_path, agent, version=version)
            native = setup_native(system, root, agent)
            reader = LegacyReader(agent, root, runtime_id='agent')
            native.plugins = [reader]
            old_index = native.index_for(reader)
            # Exact pre-repair policy fingerprint, not just a fake stale string.
            old_index.policy = HistoryIndex.policy + ':' + digest([
                reader.structure_version, reader.version_policy, reader.verified_series])
            await native.scan()
            before = (await native.listing()).items[0]
            assert before.format.status == 'unsupported'
            assert old_index.repository.load(old_index.key(path))['policy'] == old_index.policy
            await system.close()
            system = System(tmp_path)
            native = setup_native(system, root, agent)
            index = native.index_for(native.plugins[0])
            assert index.load(path) is None
            await native.scan()
            after = (await native.listing()).items[0]
            assert after.native_session_id == before.native_session_id
            assert after.format.status == 'readable'
            assert after.source_revision != before.source_revision
            assert after.index_version > before.index_version
            assert index.parsed_bytes >= path.stat().st_size
            assert len((await native.read(after.native_session_id)).items) == 2
            assert index.repository.load(index.key(path))['policy'] == index.policy
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('source', ['vscode', 'exec', {'subagent': {'thread': 'synthetic'}}])
def test_current_and_future_versions_do_not_relax_terminal_provenance(tmp_path, source):
    root = tmp_path / 'records'
    for version in ('0.159.2', '0.160.0'):
        path = fixture_history(root, tmp_path, version=version, source=source)
        assert FileHistory('codex', root).inspect(path) is None


def test_later_future_version_is_reported_and_major_jump_is_rejected(tmp_path):
    root = tmp_path / 'records'
    path = fixture_history(root, tmp_path, version='0.111.0')
    with path.open('a') as stream:
        stream.write(json.dumps({'type': 'turn_context', 'payload': {'cli_version': '0.160.0'}}) + '\n')
    reader = FileHistory('codex', root)
    source = reader.inspect(path)
    assert source.readable and source.reason == reader.compatible_reason
    assert '0.160.0' in reader.capabilities()['observedVersions']
    with path.open('a') as stream:
        stream.write(json.dumps({'type': 'turn_context', 'payload': {'cli_version': '1.0.0'}}) + '\n')
    source = reader.inspect(path)
    assert not source.readable and 'cli_version' in source.reason and '主版本' in source.reason
