"""Real TLS P1 + Worker: reader upgrades must not reuse metadata CAS versions."""
import asyncio
import json

from adapters.history import FileHistory
from remote_support import until
from test_r15_joint_server import RealPair, server_source
from test_r3_native import fixture_history


def cloud_indexes(pair):
    with pair.service.repo.transaction() as tx:
        return tx.list(pair.owner, 'native-index', worker=pair.worker_id)


def test_reader_policy_upgrade_syncs_indexes_and_imported_metadata(tmp_path, monkeypatch):
    current_series = dict(FileHistory.verified_series)
    monkeypatch.setattr(FileHistory, 'structure_version', 'structures-v2')
    monkeypatch.setattr(FileHistory, 'verified_series', {**current_series, 'codex': (0, 153, 0)})

    async def scenario():
        async with RealPair(tmp_path, revision=4, native_history=True) as pair:
            native = pair.system.worker.native
            for i in range(3):
                fixture_history(tmp_path / 'synthetic-native' / str(i), tmp_path,
                                version='0.150.0', identifier=f'00000000-0000-4000-8000-{10+i:012d}')
            await native.scan()
            await until(lambda: len(cloud_indexes(pair)) == 4)
            await until(lambda: pair.cloud_conversation(pair.native_conversation.id) is not None)
            old_indexes = {i['_localId']: i for i in cloud_indexes(pair)}
            assert sum(i['format']['status'] == 'unsupported' for i in old_indexes.values()) == 3
            old_conversation = pair.cloud_conversation(pair.native_conversation.id)
            plugin = native.plugins[0]
            plugin.structure_version = 'structures-v3'
            plugin.verified_series = current_series
            native.indexes.clear()
            await native.scan()
            new_source = native.chat.repository.conversation(pair.native_conversation.id).native_source_revision
            await until(lambda: pair.system.repo.get('link')['view']['state'] == 'frozen' or
                        pair.cloud_conversation(pair.native_conversation.id).get('nativeSourceRevision') == new_source)
            assert pair.system.repo.get('link')['view']['state'] == 'paired', [
                f for f in pair.received if f['type'] == 'worker.hello_rejected']
            await until(lambda: all(i['format']['status'] == 'readable' for i in cloud_indexes(pair)))
            for index in cloud_indexes(pair):
                assert index['indexVersion'] > old_indexes[index['_localId']]['indexVersion']
            updated = pair.cloud_conversation(pair.native_conversation.id)
            assert updated['metadataVersion'] > old_conversation['metadataVersion']
            assert updated['nativeSourceRevision'] != old_conversation['nativeSourceRevision']
            assert updated['nativeActivity']['activity'] == 'unknown'
            version = updated['metadataVersion']
            await native.scan()
            with pair.system.db.locked_connection() as db:
                value = json.loads(db.execute('SELECT payload_json FROM local_conversations WHERE conversation_id=?',
                                             (pair.native_conversation.id,)).fetchone()[0])
            assert value['version'] == version  # observedAt alone must not churn CAS.
    asyncio.run(scenario())

def test_real_conflict_is_rejected_then_operator_reset_recovers_without_pairing(tmp_path):
    from protocol.generated.python import LocalConversationView
    from runtime.remote.recovery import SyncRecovery

    async def scenario():
        async with RealPair(tmp_path, revision=4, native_history=True) as pair:
            worker, repo = pair.system.worker, pair.system.repo
            conversation = pair.native_conversation.id
            await until(lambda: pair.cloud_conversation(conversation) is not None and
                        (repo.get('sync-work') or {}).get('phase') == 'synced')
            await worker.native.stop()
            worker.native.request_scan = lambda: None
            cloud_before = pair.cloud_conversation(conversation)
            messages_before = pair.cloud_messages(conversation)
            identity = repo.get('identity')
            credential_path = worker.link.vault.path
            credential_before = credential_path.read_bytes()
            generation = worker.sync.settings().sync_generation
            # Reproduce the old producer's persisted metadata edit with unchanged
            # CAS, not a damaged frame/hash or relaxed server validation.
            with pair.system.db.transaction() as tx:
                row = tx.connection.execute('SELECT payload_json FROM local_conversations WHERE conversation_id=?',
                                            (conversation,)).fetchone()
                body = json.loads(row[0])
                body['nativeSourceRevision'] = 'b' * 64
                tx.connection.execute('UPDATE local_conversations SET payload_json=? WHERE conversation_id=?',
                                      (json.dumps(body), conversation))
                worker.sync.upsert(tx, conversation)
                repo.seal(tx)
            await until(lambda: repo.get('link')['view']['state'] == 'frozen')
            assert repo.get('link')['view']['lastErrorCode'] == 'REMOTE_SYNC_CONFLICT'
            assert pair.cloud_conversation(conversation) == cloud_before
            with pair.service.repo.transaction() as tx:
                assert not tx.get(pair.owner, 'device', pair.worker_id)['_frozen']
            assert any(f['type'] == 'worker.hello_rejected' and
                       f['error']['code'] == 'REMOTE_SYNC_CONFLICT' and not f['error']['retryable']
                       for f in pair.received)
            await worker.stop()
            # Browser Cookie is insufficient; the operator must explicitly reset.
            denied = await pair.system.local.post('/internal/remote/resync', headers={'Authorization': ''})
            assert denied.status_code == 401
            recovery = await pair.system.local.post('/internal/remote/resync')
            assert recovery.status_code == 200 and recovery.headers['cache-control'] == 'no-store'
            assert worker.sync.settings().sync_generation == generation  # Wait for ready handshake.
            assert (await pair.system.local.post('/internal/remote/resync')).status_code == 200
            # Recovery intent survives a component/process lifecycle restart.
            worker.recovery = SyncRecovery(repo, worker.sync)
            await worker.start()
            await until(lambda: (repo.get('sync-recovery') or {}).get('phase') == 'complete')
            assert repo.get('link')['view']['state'] == 'paired'
            assert repo.get('link')['view']['connectionStatus'] == 'online'
            assert worker.sync.settings().sync_generation == generation + 2
            assert repo.get('identity')['store'] == identity['store']
            assert credential_path.read_bytes() == credential_before
            assert pair.cloud_conversation(conversation)['nativeSourceRevision'] == 'b' * 64
            assert pair.cloud_conversation(conversation)['conversationId'] == cloud_before['conversationId']
            assert not pair.system.adapter.started and not pair.system.adapter.resumed
            assert [m['text'] for m in pair.cloud_messages(conversation)] == [m['text'] for m in messages_before]
            assert len(pair.system.chat.repository.messages(conversation)) == len(messages_before)
            assert LocalConversationView.model_validate_json(body_json(pair, conversation)).conversation_kind == 'native'
            assert any(f['type'] == 'sync.content.redaction' for f in pair.sent)
            assert len([f for f in pair.sent if f['type'] == 'sync.reset']) == 1
    asyncio.run(scenario())


def body_json(pair, identifier):
    with pair.system.db.locked_connection() as db:
        return db.execute('SELECT payload_json FROM local_conversations WHERE conversation_id=?', (identifier,)).fetchone()[0]


def test_server_freeze_and_identity_faults_cannot_be_reset(tmp_path):
    async def scenario():
        async with RealPair(tmp_path, revision=4) as pair:
            worker, repo = pair.system.worker, pair.system.repo
            await worker.stop()
            generation = worker.sync.settings().sync_generation
            for code in ('REMOTE_STORE_CHANGED', 'REMOTE_ACK_CONFLICT', 'REMOTE_EPOCH_STALE', 'REMOTE_DEVICE_AUTH_FAILED'):
                worker.state('offline', code=code, frozen=True)
                response = await pair.system.local.post('/internal/remote/resync')
                assert response.status_code == 409
                assert repo.get('link')['view']['lastErrorCode'] == code
            worker.state('offline', code='REMOTE_SYNC_CONFLICT', frozen=True)
            with pair.service.repo.transaction() as tx:
                device = tx.get(pair.owner, 'device', pair.worker_id)
                pair.service.freeze(tx, pair.owner, device, 'REMOTE_ACK_CONFLICT')
            assert (await pair.system.local.post('/internal/remote/resync')).status_code == 200
            await worker.start()
            await until(lambda: repo.get('link')['view'].get('lastErrorCode') == 'REMOTE_ACK_CONFLICT')
            assert repo.get('link')['view']['state'] == 'frozen'
            assert repo.get('sync-recovery')['phase'] == 'blocked'
            assert worker.sync.settings().sync_generation == generation
            assert not any(f['type'] == 'sync.reset' for f in pair.sent)
            assert (await pair.system.local.post('/internal/remote/resync')).status_code == 409
    asyncio.run(scenario())


def test_same_index_version_different_payload_is_still_rejected(tmp_path):
    async def scenario():
        async with RealPair(tmp_path, revision=4, native_history=True) as pair:
            await until(lambda: len(cloud_indexes(pair)) == 1)
            native = pair.system.worker.native
            row = native.row(pair.native_index.native_session_id)
            payload = json.loads(row['index_json'])
            payload['title'] = 'synthetic conflicting title'
            original = cloud_indexes(pair)[0]
            with pair.system.db.transaction() as tx:
                pair.system.repo.emit(tx, 'native.index.upserted',
                    syncGeneration=pair.system.worker.sync.settings().sync_generation, payload=payload)
                pair.system.repo.seal(tx)
            await until(lambda: pair.system.repo.get('link')['view']['state'] == 'frozen')
            assert pair.system.repo.get('link')['view']['lastErrorCode'] == 'REMOTE_SYNC_CONFLICT'
            assert cloud_indexes(pair)[0] == original
    asyncio.run(scenario())


def test_resync_cli_requires_confirmation_and_uses_internal_endpoint():
    import io
    import pytest
    from runtime import cli
    calls = []
    class Client:
        def request(self, method, path):
            calls.append((method, path))
            return {'requested': True}
    with pytest.raises(SystemExit):
        cli.parser().parse_args(['remote', 'resync'])
    out = io.StringIO()
    cli.execute(cli.parser().parse_args(['remote', 'resync', '--confirm-reset']), Client(), out)
    assert calls == [('POST', '/internal/remote/resync')]
    assert json.loads(out.getvalue()) == {'requested': True}

def test_sync_disable_cancels_pending_recovery(tmp_path):
    from protocol.generated.python import RemoteSyncSettingsInput
    async def scenario():
        async with RealPair(tmp_path, revision=4) as pair:
            worker, repo = pair.system.worker, pair.system.repo
            await worker.stop()
            worker.state('offline', frozen=True, code='REMOTE_SYNC_CONFLICT')
            worker.recovery.request()
            worker.sync.set_settings(RemoteSyncSettingsInput(
                mirrorEnabled=False, expectedVersion=worker.sync.settings().version), 'disable-recovery')
            assert repo.get('sync-recovery')['phase'] == 'cancelled'
            generation = worker.sync.settings().sync_generation
            await worker.start()
            await until(lambda: repo.get('link')['view']['connectionStatus'] == 'online')
            assert worker.sync.settings().sync_generation == generation
            assert not worker.sync.settings().mirror_enabled
    asyncio.run(scenario())
