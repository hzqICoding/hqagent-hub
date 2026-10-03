"""0.10.1 erasure uses only synthetic local data and fake model adapters."""
import asyncio
import json

import httpx
import pytest
from protocol.generated import python as dto

from core.errors import HubError
from remote_support import System, until
from storage.local_chat import now
from test_r15_joint_server import RealPair, server_source
from test_r16_attachments import headers, synced, upload_phone, send_phone
from test_r3_native import fixture_history, setup_native, indexed_listing


def conversation(system, key='delete'):
    return system.chat.repository.create_conversation(dto.CreateLocalConversationInput(
        title='synthetic deletion', workspaceId='workspace', sceneId='analyze'), key)


def test_v1_v2_deletion_share_cas_idempotency_and_no_store(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            cid = conversation(system).id
            path = '/conversations/' + cid
            no_origin = await system.local.delete('/api/v1' + path + '?expectedVersion=1',
                headers={'Idempotency-Key': 'delete'})
            assert no_origin.status_code == 403 and no_origin.headers['cache-control'] == 'no-store'
            system.local.headers['Origin'] = 'http://127.0.0.1'
            missing = await system.local.delete('/api/v1' + path, headers={'Idempotency-Key': 'delete'})
            assert missing.status_code == 422 and missing.headers['cache-control'] == 'no-store'
            stale = await system.local.delete('/api/v1' + path + '?expectedVersion=2', headers={'Idempotency-Key': 'delete'})
            assert stale.status_code == 409 and stale.json()['error']['detail']['reason'] == 'version_mismatch'
            deleted = await system.local.delete('/api/v1' + path + '?expectedVersion=1',
                headers={'Idempotency-Key': 'delete', 'X-Request-Id': 'erase-request'})
            assert deleted.status_code == 200, deleted.text
            assert deleted.json()['requestId'] == deleted.headers['x-request-id'] == 'erase-request'
            assert deleted.headers['cache-control'] == 'no-store'
            from core.local_auth import COOKIE_NAME
            auth = system.application.local_auth
            system.local.cookies.set(COOKIE_NAME, auth.exchange(auth.issue_code()))
            replay = await system.local.delete('/api/v2' + path + '?expectedVersion=1', headers={'Idempotency-Key': 'delete'})
            assert replay.status_code == 200 and replay.json()['data'] == deleted.json()['data']
            assert replay.headers['cache-control'] == 'no-store'
            missing = await system.local.delete('/api/v2' + path + '?expectedVersion=1', headers={'Idempotency-Key': 'new-key'})
            assert missing.status_code == 404 and missing.headers['cache-control'] == 'no-store'
        finally:
            await system.close()
    asyncio.run(scenario())


def seed_runs(system, cid, count, status='succeeded'):
    with system.db.transaction() as tx:
        for index in range(count):
            tx.connection.execute('INSERT INTO local_messages VALUES(?,?,?,?,?,?,?)',
                (f'm-{index}', cid, index + 1, 'user', 'synthetic private text', f'r-{index}', now()))
            tx.connection.execute('INSERT INTO local_runs VALUES(?,?,?,?,?,?,?,?,?,?)',
                (f'r-{index}', cid, f'm-{index}', None, '{}', 'new', status, None, now(), now()))


def test_full_history_and_bounded_blocking_run_ids(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            cid = conversation(system).id
            seed_runs(system, cid, 310)
            with system.db.transaction() as tx:
                tx.connection.execute("UPDATE local_runs SET status='paused' WHERE run_id='r-0'")
            with pytest.raises(HubError) as error:
                await system.chat.delete_conversation(cid, 1, 'delete')
            assert error.value.detail == {'reason': 'active_runs', 'blockingRunIds': ['r-0'], 'hasMoreBlockingRuns': False}
            with system.db.transaction() as tx:
                tx.connection.execute("UPDATE local_runs SET status='queued'")
            with pytest.raises(HubError) as error:
                await system.chat.delete_conversation(cid, 1, 'delete')
            assert len(error.value.detail['blockingRunIds']) == 100
            assert error.value.detail['hasMoreBlockingRuns'] is True
            assert system.db.connection.execute('SELECT COUNT(*) FROM local_runs').fetchone()[0] == 310
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('flag,reason', [('recoveryRequired', 'recovery_required'), ('unresolvedCancellation', 'cancellation_unconfirmed')])
def test_terminal_task_with_recovery_still_blocks(tmp_path, flag, reason):
    async def scenario():
        system = System(tmp_path)
        try:
            cid = conversation(system).id
            seed_runs(system, cid, 1)
            with system.db.transaction() as tx:
                tx.connection.execute("UPDATE local_runs SET task_id='task-old'")
                tx.connection.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                    ('task-old', 'workspace', None, 'private objective', 'failed', 'desktop', '{}', now(), now()))
                tx.connection.execute('INSERT INTO hub_state VALUES(?,?,?)',
                    ('task_spec:task-old', json.dumps({flag: True}), now()))
            with pytest.raises(HubError) as error:
                await system.chat.delete_conversation(cid, 1, 'delete')
            assert error.value.detail['reason'] == reason
            assert error.value.detail['blockingRunIds'] == ['r-0']
            with system.db.transaction() as tx:
                tx.connection.execute("DELETE FROM tasks WHERE task_id='task-old'")
        finally:
            await system.close()
    asyncio.run(scenario())


def test_cas_complete_erasure_replay_and_old_send_key(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            cid = conversation(system).id
            body = b'SYNTHETIC_LOCAL_SECRET'
            response = await system.local.post(f'/api/v2/conversations/{cid}/attachments', content=body, headers=headers(body))
            assert response.status_code == 201, response.text
            attachment = response.json()['data']['attachment']['attachmentId']
            library = system.worker.attachments.library
            path = library.path(library.repo.row(attachment))
            value = dto.SendLocalMessageInput(clientMessageId='old-send', text='private text', sessionMode='new', attachmentIds=[attachment])
            receipt = system.chat.send(cid, value, 'old-send')
            with system.db.transaction() as tx:
                tx.connection.execute("UPDATE local_runs SET status='cancelled'")
                tx.connection.execute("UPDATE attachment_preparations SET state='cancelled'")
            with pytest.raises(HubError) as error:
                await system.chat.delete_conversation(cid, 2, 'delete')
            assert error.value.detail == {'reason': 'version_mismatch', 'currentVersion': 1}
            result = await system.chat.delete_conversation(cid, 1, 'delete')
            assert result.local_deleted is True and result.remote_cleanup == 'not_required'
            assert not path.exists()
            for table in ('local_conversations', 'local_messages', 'local_runs', 'local_attachments', 'local_attachment_messages', 'attachment_preparations', 'attachment_upload_keys', 'attachment_sync_jobs', 'local_commands'):
                assert system.db.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0, table
            assert await system.chat.delete_conversation(cid, 1, 'delete') == result
            with pytest.raises(HubError) as error:
                await system.chat.delete_conversation(cid, 1, 'different')
            assert error.value.code == 'NOT_FOUND'
            with pytest.raises(HubError) as error:
                system.chat.send(cid, value, 'old-send')
            assert error.value.code == 'NOT_FOUND'
            with pytest.raises(HubError) as error:
                await system.chat.delete_conversation(cid, 2, 'delete')
            assert error.value.code == 'IDEMPOTENCY_MISMATCH'
            assert receipt.conversation_id == cid
        finally:
            await system.close()
    asyncio.run(scenario())


def test_cleanup_failure_preserves_fence_and_restart_recovers(tmp_path, monkeypatch):
    async def scenario():
        system = System(tmp_path)
        cid = conversation(system).id
        library = system.worker.attachments.library
        original = library.erase_conversation
        async def denied(_conversation):
            raise PermissionError('synthetic path must never escape error')
        monkeypatch.setattr(library, 'erase_conversation', denied)
        with pytest.raises(HubError) as error:
            await system.chat.delete_conversation(cid, 1, 'delete')
        assert error.value.code == 'INTERNAL'
        assert 'synthetic path' not in error.value.message
        with pytest.raises(HubError) as error:
            system.chat.send(cid, dto.SendLocalMessageInput(clientMessageId='late', text='late', sessionMode='new'), 'late')
        assert error.value.detail == {'reason': 'deleting'}
        monkeypatch.setattr(library, 'erase_conversation', original)
        await system.close()
        reopened = System(tmp_path)
        try:
            retry = reopened.worker.attachments.library.erase_conversation
            monkeypatch.setattr(reopened.worker.attachments.library, 'erase_conversation', denied)
            await reopened.chat.start()
            assert reopened.chat.repository.conversations() == []
            assert reopened.db.connection.execute("SELECT state FROM local_conversation_deletions WHERE conversation_id=?", (cid,)).fetchone()[0] == 'cleaning'
            monkeypatch.setattr(reopened.worker.attachments.library, 'erase_conversation', retry)
            result = await reopened.chat.delete_conversation(cid, 1, 'delete')
            assert reopened.db.connection.execute('SELECT COUNT(*) FROM local_conversations').fetchone()[0] == 0
            assert result.local_deleted is True
        finally:
            await reopened.close()
    asyncio.run(scenario())


def test_real_server_ack_erases_replica_and_attachment_storage(tmp_path):
    async def scenario():
        async with RealPair(tmp_path, revision=4) as pair:
            system = pair.system
            system.worker.attachments.library.http_factory = lambda: httpx.AsyncClient(verify=pair.tls, follow_redirects=False, trust_env=False)
            await synced(pair)
            cid = pair.legacy_ids[0]
            body = b'SYNTHETIC_DELETE_ATTACHMENT'
            uploaded = await system.local.post(f'/api/v2/conversations/{cid}/attachments', content=body, headers=headers(body))
            assert uploaded.status_code == 201, uploaded.text
            attachment = uploaded.json()['data']['attachment']['attachmentId']
            sent = await system.local.post(f'/api/v2/conversations/{cid}/messages',
                json={'clientMessageId': 'with-delete', 'text': 'synthetic input', 'sessionMode': 'new', 'attachmentIds': [attachment]},
                headers={'Idempotency-Key': 'with-delete'})
            assert sent.status_code == 202, sent.text
            run = sent.json()['data']['runId']
            await until(lambda: system.chat.repository.run_record(run)['status'] == 'succeeded')
            await until(lambda: system.worker.attachments.repo.view(attachment).sync_status == 'available', timeout=15)
            cloud_id = pair.cloud_conversation(cid)['conversationId']
            local_file = system.worker.attachments.library.path(system.worker.attachments.repo.row(attachment))
            result = await system.chat.delete_conversation(cid, 1, 'real-delete')
            assert result.remote_cleanup == 'pending'
            assert not local_file.exists()
            await until(lambda: system.chat.deletions.receipt(cid).remote_cleanup == 'confirmed', timeout=15)
            assert pair.cloud_conversation(cid) is None
            assert any(f['type'] == 'sync.conversation.deleted' and f['conversationId'] == cid for f in pair.sent)
            cloud = pair.service.repo.connection
            assert cloud.execute("SELECT COUNT(*) FROM records WHERE id=? OR parent=?", (cloud_id, cloud_id)).fetchone()[0] == 0
            # Inspect the actual attachment tables and CAS files, not API hiding.
            assert cloud.execute("SELECT COUNT(*) FROM records WHERE kind='attachment' AND parent=?", (cloud_id,)).fetchone()[0] == 0
            import hashlib
            assert not pair.service.attachments.store.exists(hashlib.sha256(body).hexdigest())
            assert (await system.chat.delete_conversation(cid, 1, 'real-delete')).remote_cleanup == 'confirmed'
    asyncio.run(scenario())


def test_native_import_erases_hub_copy_and_keeps_vendor_file(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            source = fixture_history(tmp_path / 'native-source', tmp_path)
            original = source.read_bytes()
            native = setup_native(system, source.parent)
            item = (await indexed_listing(native)).items[0]
            response = await system.local.post(f'/api/v2/native-sessions/{item.native_session_id}/imports',
                json={'terminalClosedConfirmed': True, 'expectedIndexVersion': item.index_version,
                      'sourceRevision': item.source_revision},
                headers={'Idempotency-Key': 'native-import', 'Origin': 'http://127.0.0.1'})
            assert response.status_code == 201, response.text
            cid = response.json()['data']['id']
            result = await system.chat.delete_conversation(cid, 1, 'native-delete')
            assert result.local_deleted
            assert source.read_bytes() == original
            for table in ('native_sources', 'local_messages', 'local_conversations', 'local_commands', 'native_history_indexes'):
                assert system.db.connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0, table
            assert system.db.connection.execute('SELECT COUNT(*) FROM local_deleted_native_bindings').fetchone()[0] == 1
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('independent', [False, True])
def test_shared_task_and_other_conversation_survive(tmp_path, independent):
    async def scenario():
        system = System(tmp_path)
        try:
            first = conversation(system, 'first').id
            second = conversation(system, 'second').id
            body = b'SHARED_SYNTHETIC_ATTACHMENT'
            uploaded = await system.local.post(f'/api/v2/conversations/{first}/attachments', content=body, headers=headers(body))
            attachment = uploaded.json()['data']['attachment']['attachmentId']
            library = system.worker.attachments.library
            old_path = library.path(library.repo.row(attachment))
            await system.chat.start()
            receipt = system.chat.send(first, dto.SendLocalMessageInput(clientMessageId='run', text='synthetic shared', sessionMode='new', attachmentIds=[attachment]), 'run')
            await until(lambda: system.chat.repository.run_record(receipt.run_id)['status'] == 'succeeded')
            task_id = system.chat.repository.run_record(receipt.run_id)['task_id']
            with system.db.transaction() as tx:
                if independent:
                    task = dict(tx.connection.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone())
                    payload = json.loads(task['payload_json'])
                    payload.update(id='independent-task', profileId='independent-profile')
                    tx.connection.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                        ('independent-task', task['workspace_id'], 'independent-profile', task['objective'], task['status'], task['source'], json.dumps(payload), now(), now()))
                    spec = json.loads(tx.connection.execute('SELECT value_json FROM hub_state WHERE key=?', ('task_spec:' + task_id,)).fetchone()[0])
                    session = tx.connection.execute('SELECT session_id FROM sessions WHERE task_id=?', (task_id,)).fetchone()[0]
                    spec['request'].update(profileId='independent-profile', resumeSessions={'analyst': session})
                    tx.connection.execute('INSERT INTO hub_state VALUES(?,?,?)', ('task_spec:independent-task', json.dumps(spec), now()))
                else:
                    tx.connection.execute('INSERT INTO local_messages VALUES(?,?,?,?,?,?,?)', ('shared-message', second, 1, 'user', 'retained', 'shared-run', now()))
                    tx.connection.execute('INSERT INTO local_runs VALUES(?,?,?,?,?,?,?,?,?,?)',
                        ('shared-run', second, 'shared-message', task_id, '{}', 'new', 'succeeded', None, now(), now()))
            result = await system.chat.delete_conversation(first, 1, 'delete-first')
            assert result.local_deleted
            assert system.chat.repository.conversation(second).id == second
            assert system.db.connection.execute('SELECT 1 FROM tasks WHERE task_id=?', (task_id,)).fetchone()
            assert system.db.connection.execute('SELECT 1 FROM sessions WHERE task_id=?', (task_id,)).fetchone()
            assert system.db.connection.execute('SELECT 1 FROM hub_state WHERE key=?', ('task_spec:' + task_id,)).fetchone()
            retained = library.repo.row(attachment)
            assert retained['conversation_id'].startswith('retained-task-') if independent else retained['conversation_id'] == second
            assert library.path(retained).read_bytes() == body
            assert not old_path.exists()
            saved = json.loads(system.db.connection.execute('SELECT value_json FROM hub_state WHERE key=?', ('task_spec:' + task_id,)).fetchone()[0])
            assert saved['inputAttachments'][0]['localPath'] == str(library.path(retained))
            if independent:
                other = json.loads(system.db.connection.execute("SELECT value_json FROM hub_state WHERE key='task_spec:independent-task'").fetchone()[0])
                assert other['inputAttachments'][0]['localPath'] == str(library.path(retained))
                assert system.db.connection.execute("SELECT 1 FROM tasks WHERE task_id='independent-task'").fetchone()
            await library.maintain(restart=True)
            assert library.path(retained).read_bytes() == body
        finally:
            await system.close()
    asyncio.run(scenario())


def test_offline_deletion_is_pending_until_real_ack_and_survives_restart(tmp_path):
    async def scenario():
        system = System(tmp_path)
        cid = conversation(system).id
        with system.db.transaction() as tx:
            identity = system.repo.get('identity', tx)
            identity['wireRevision'] = 4
            system.repo.put('identity', identity, tx)
            system.repo.set_view(tx, {'state': 'paired', 'workerId': 'synthetic-worker', 'deviceName': 'fixture',
                'serverOrigin': 'https://paired.invalid', 'connectionStatus': 'offline', 'lastConnectedAt': None})
            tx.connection.execute('INSERT INTO remote_sync_versions VALUES(?,?,?,?,?,?)', (identity['store'], 1, 'conversation', cid, 1, 'digest'))
            system.repo.seal(tx)
        result = await system.chat.delete_conversation(cid, 1, 'offline-delete')
        assert result.remote_cleanup == 'pending'
        with system.db.locked_connection() as db:
            assert db.execute("SELECT COUNT(*) FROM remote_outbox WHERE json_extract(frame_json,'$.type')='sync.conversation.deleted'").fetchone()[0] == 1
        await system.close()
        reopened = System(tmp_path)
        try:
            assert (await reopened.chat.delete_conversation(cid, 1, 'offline-delete')).remote_cleanup == 'pending'
        finally:
            await reopened.close()
    asyncio.run(scenario())


def test_unacked_content_is_redacted_and_server_ack_confirms_deletion(tmp_path):
    async def scenario():
        async with RealPair(tmp_path, revision=4, hold_history=True) as pair:
            await asyncio.wait_for(pair.history_held.wait(), 8)
            previous = next(f for f in pair.sent if f['type'] == 'sync.message.segment')
            cid = previous['payload']['conversationId']
            # Queue an immutable content slot while ACK processing is held.
            # Deletion must cover this never-delivered slot without sending it.
            with pair.system.db.transaction() as tx:
                pair.system.repo.emit(tx, 'sync.message.segment', syncGeneration=previous['syncGeneration'],
                    payload={**previous['payload'], 'messageRevision': previous['payload']['messageRevision'] + 1})
                pair.system.repo.seal(tx)
            result = await pair.system.chat.delete_conversation(cid, 1, 'unacked-delete')
            assert result.remote_cleanup == 'pending'
            with pair.system.db.locked_connection() as db:
                proofs = [json.loads(r[0]) for r in db.execute('SELECT frame_json FROM remote_sync_redactions')]
                scoped = [p for p in proofs if p.get('conversationId') == cid]
                assert scoped and any(p['slots'] for p in scoped)
                for row in db.execute('SELECT frame_json FROM remote_outbox'):
                    frame = json.loads(row[0])
                    assert not (frame.get('type') in {'sync.conversation.upserted', 'sync.message.segment', 'sync.run.state'}
                                and frame.get('payload', {}).get('conversationId') == cid)
            pair.release_history.set()
            await until(lambda: pair.system.chat.deletions.receipt(cid).remote_cleanup == 'confirmed', timeout=15)
            assert pair.cloud_conversation(cid) is None
            assert pair.system.repo.get('link')['view']['state'] == 'paired'
    asyncio.run(scenario())


def test_deleted_remote_send_and_grant_replays_are_rejected_before_cache(tmp_path):
    async def scenario():
        async with RealPair(tmp_path, revision=4) as pair:
            system = pair.system
            system.worker.attachments.library.http_factory = lambda: httpx.AsyncClient(verify=pair.tls, follow_redirects=False, trust_env=False)
            cloud_id, attachment = await upload_phone(pair)
            command = await send_phone(pair, cloud_id, attachment)
            await until(lambda: system.worker.delivery.row(command) and system.worker.delivery.row(command)['state'] == 'completed', timeout=15)
            row = system.worker.delivery.row(command)
            cid = row['local_id']
            original = next(f for f in pair.received if f.get('type') == 'run.submit' and f.get('commandId') == command)
            grant = next(f for f in pair.received if f.get('type') == 'command.delivery_granted' and f.get('commandId') == command)
            starts = len(system.adapter.started)
            result = await system.chat.delete_conversation(cid, 1, 'remote-delete')
            assert result.local_deleted
            await system.worker.stop()
            for frame in (original, grant, {**original, 'commandId': 'late-after-delete'}):
                receipt, _ = await system.worker.delivery.receive(frame)
                assert receipt['type'] == 'command.rejected'
                assert receipt['error']['code'] == 'NOT_FOUND'
            assert len(system.adapter.started) == starts
            assert system.db.connection.execute('SELECT COUNT(*) FROM local_conversations WHERE conversation_id=?', (cid,)).fetchone()[0] == 0
            assert system.worker.delivery.row(command)['command_json'] is None
            assert not system.db.connection.execute("SELECT 1 FROM remote2_delivery WHERE command_id='late-after-delete'").fetchone()
    asyncio.run(scenario())


def test_execution_handles_and_session_only_caches_are_erased(tmp_path):
    async def scenario():
        from adapters.session_registry import SessionRegistry, AdapterSessionState
        from storage.events import EventDraft
        system = System(tmp_path)
        try:
            cid = conversation(system).id
            await system.chat.start()
            receipt = system.chat.send(cid, dto.SendLocalMessageInput(clientMessageId='exclusive', text='synthetic exclusive', sessionMode='new'), 'exclusive')
            await until(lambda: system.chat.repository.run_record(receipt.run_id)['status'] == 'succeeded')
            task = system.chat.repository.run_record(receipt.run_id)['task_id']
            node = system.db.connection.execute('SELECT node_id FROM task_nodes WHERE task_id=?', (task,)).fetchone()[0]
            session = system.db.connection.execute('SELECT session_id FROM sessions WHERE task_id=?', (task,)).fetchone()[0]
            system.tasks._dispatching.add(task)
            with pytest.raises(HubError) as error:
                await system.chat.delete_conversation(cid, 1, 'delete-exclusive')
            assert error.value.detail['reason'] == 'active_runs'
            system.tasks._dispatching.discard(task)
            system.tasks._outcomes[node] = object()
            with pytest.raises(HubError) as error:
                await system.chat.delete_conversation(cid, 1, 'delete-exclusive')
            assert error.value.detail['reason'] == 'active_runs'
            system.tasks._outcomes.pop(node)
            system.adapter.registry = SessionRegistry()
            state = AdapterSessionState(session_id=session, external_session_id='synthetic', spec=system.adapter.started[0], guard=None)
            state.finished.set()
            system.adapter.registry.add(state)
            with system.db.transaction() as tx:
                tx.connection.execute('INSERT INTO local_commands VALUES(?,?,?,?)', ('session-only', 'secret-key', 'hash', json.dumps({'id': session, 'output': 'SENSITIVE_CACHED_OUTPUT'})))
                tx.connection.execute('INSERT INTO idempotency_records VALUES(?,?,?,?,?)', ('cache', '/sessions/' + session, 'hash', json.dumps({'id': session, 'private': 'SENSITIVE_CACHED_OUTPUT'}), now()))
                tx.connection.execute('INSERT INTO remote_state VALUES(?,?)', ('session-cache', json.dumps({'sessionId': session, 'body': 'SENSITIVE_CACHED_OUTPUT'})))
                tx.connection.execute('INSERT INTO approvals VALUES(?,?,?,?,?,?,?)',
                    ('exclusive-approval', task, node, 'git_push', '{}', 'approved', now()))
                projection_keys = ['message:' + receipt.message_id, 'run:' + receipt.run_id,
                                   'approval:exclusive-approval']
                for projection in [*projection_keys, 'message:retained-unrelated']:
                    tx.connection.execute('INSERT INTO remote_projections VALUES(?,?)', (projection, 'digest'))
                system.repo.put('sync-work', {'phase': 'synced', 'store': system.repo.get('identity', tx)['store'],
                    'generation': 1, 'backfillId': 'retained-backfill', 'cursor': 0, 'high': 0, 'batch': 0}, tx)
                event, _ = system.events.append(tx, EventDraft(aggregate_type='session', aggregate_id=session, type='session.test', payload={'private': 'SENSITIVE_CACHED_OUTPUT'}))
                system.repo.seal(tx)
            persistent = {key: system.repo.get(key) for key in ('identity', 'link', 'sync-work')}
            result = await system.chat.delete_conversation(cid, 1, 'delete-exclusive')
            assert result.local_deleted
            assert system.adapter.registry.get(session) is None
            for table, field in [('local_commands', 'response_json'), ('idempotency_records', 'response_json'), ('remote_state', 'value_json'), ('events', 'payload_json')]:
                assert not any('SENSITIVE_CACHED_OUTPUT' in row[0] for row in system.db.connection.execute(f'SELECT {field} FROM {table}'))
            assert system.db.connection.execute('SELECT payload_json FROM events WHERE seq=?', (event.seq,)).fetchone()[0] == '{}'
            assert [r[0] for r in system.db.connection.execute('SELECT key FROM remote_projections')] == ['message:retained-unrelated']
            for key in ('link', 'sync-work'):
                assert system.repo.get(key) == persistent[key]
            identity = system.repo.get('identity')
            assert identity['revision'] > persistent['identity']['revision']
            assert {k: v for k, v in identity.items() if k != 'revision'} == {
                k: v for k, v in persistent['identity'].items() if k != 'revision'}
        finally:
            await system.close()
    asyncio.run(scenario())


def test_unacked_approval_body_blocks_without_forging_redaction_or_omission(tmp_path):
    async def scenario():
        from pydantic import ValidationError
        system = System(tmp_path)
        try:
            cid = conversation(system).id
            seed_runs(system, cid, 1)
            with system.db.transaction() as tx:
                identity = system.repo.get('identity', tx)
                identity['wireRevision'] = 4
                system.repo.put('identity', identity, tx)
                system.repo.set_view(tx, {'state': 'paired', 'workerId': 'approval-worker', 'deviceName': 'fixture',
                    'serverOrigin': 'https://paired.invalid', 'connectionStatus': 'offline', 'lastConnectedAt': None})
                tx.connection.execute('INSERT INTO remote_sync_versions VALUES(?,?,?,?,?,?)',
                    (identity['store'], 1, 'conversation', cid, 1, 'digest'))
                event = system.repo.emit(tx, 'approval.state_changed', conversationId=cid, payload={
                    'approvalId': 'private-approval', 'resultRef': {'runId': 'r-0'}, 'action': 'git_push',
                    'targetSummary': 'SENSITIVE_PENDING_APPROVAL', 'riskLevel': 'high', 'status': 'approved',
                    'requestedAt': now(), 'expiresAt': now(), 'remoteApprovalAllowed': False,
                    'workerPolicyRevision': 1, 'denialCode': 'REMOTE_APPROVAL_FORBIDDEN'})
                system.repo.seal(tx)
            original = tuple(system.db.connection.execute('SELECT frame_json,digest FROM remote_outbox WHERE seq=?', (event['seq'],)).fetchone())
            with pytest.raises(ValidationError):
                dto.RemoteV4RedactedSlot.model_validate({'seq': event['seq'], 'eventId': event['eventId'],
                    'eventSha256': original[1], 'originalType': 'approval.state_changed'})
            with pytest.raises(HubError) as error:
                await system.chat.delete_conversation(cid, 1, 'approval-delete')
            assert error.value.detail == {'reason': 'cancellation_unconfirmed', 'blockingRunIds': ['r-0'], 'hasMoreBlockingRuns': False}
            assert tuple(system.db.connection.execute('SELECT frame_json,digest FROM remote_outbox WHERE seq=?', (event['seq'],)).fetchone()) == original
            assert not system.db.connection.execute('SELECT 1 FROM local_conversation_deletions').fetchone()
            # Once the existing transport commits the actual ACK it prunes the
            # immutable frame, so the same DELETE can complete normally.
            system.repo.ack({'workerStoreId': identity['store'], 'seq': event['seq']})
            assert (await system.chat.delete_conversation(cid, 1, 'approval-delete')).local_deleted
            assert not any('SENSITIVE_PENDING_APPROVAL' in r[0] for r in system.db.connection.execute('SELECT payload_json FROM events'))
        finally:
            await system.close()
    asyncio.run(scenario())
