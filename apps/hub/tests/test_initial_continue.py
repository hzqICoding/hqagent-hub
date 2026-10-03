import asyncio
import json
from pathlib import Path

import httpx
import pytest
from protocol.generated import python as dto
from remote_support import System, until
from test_remote_cookie_routes import login, ORIGIN
from test_r15_joint_server import RealPair, server_source


def observation(system, run):
    with system.db.locked_connection() as db:
        value = db.execute('SELECT value_json FROM hub_state WHERE key=?', ('local-run-session-mode:' + run,)).fetchone()
    return json.loads(value[0]) if value else None


async def create(system):
    result = await system.local.post('/api/v2/conversations', json={
        'title': 'continue default', 'workspaceId': 'workspace', 'sceneId': 'analyze'},
        headers={'Origin': ORIGIN, 'Idempotency-Key': 'create'})
    assert result.status_code == 201, result.text
    return result.json()['data']['id']


async def send(system, conversation, key):
    result = await system.local.post(f'/api/v2/conversations/{conversation}/messages', json={
        'clientMessageId': key, 'text': key, 'sessionMode': 'continue'},
        headers={'Origin': ORIGIN, 'Idempotency-Key': key})
    assert result.status_code == 202, result.text
    run = result.json()['data']['runId']
    await until(lambda: system.chat.repository.run_record(run)['status'] in {'failed', 'succeeded'})
    return system.chat.repository.run_record(run)


@pytest.mark.parametrize('failed_before', [False, True])
def test_cookie_initial_continue_and_failure_without_task_start_new(tmp_path, failed_before):
    async def scenario():
        system = System(tmp_path)
        try:
            await login(system)
            conversation = await create(system)
            if failed_before:
                old = system.chat.repository.enqueue(conversation, dto.SendLocalMessageInput(
                    clientMessageId='failed', text='failed preparation', sessionMode='continue'), 'failed')
                system.chat.repository.complete_run(old.run_id, 'failed', 'not dispatched', error_code='ATTACHMENT_PREPARATION_INTERRUPTED')
                assert system.chat.repository.run_record(old.run_id)['task_id'] is None
            await system.chat.start()
            record = await send(system, conversation, 'first')
            assert record['status'] == 'succeeded', record['error']
            assert record['session_mode'] == 'continue'
            assert observation(system, record['run_id']) == {
                'requestedMode': 'continue', 'effectiveMode': 'new', 'reason': 'no_prior_execution'}
            assert len(system.adapter.started) == 1 and not system.adapter.resumed
            first = system.adapter.started[0]
            assert str(first.reuse_policy) == 'new_session'
            second = await send(system, conversation, 'second')
            assert second['status'] == 'succeeded', second['error']
            assert len(system.adapter.started) == 1 and len(system.adapter.resumed) == 1
            assert system.adapter.resumed[0].session_id == first.session_id
            assert observation(system, second['run_id'])['effectiveMode'] == 'continue'
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('changed', ['model', 'instructions', 'closed', 'invalid', 'recovery', 'review_mode'])
def test_existing_context_is_never_silently_replaced(tmp_path, changed):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await create(system)
            await system.chat.start()
            first = await send(system, conversation, 'first')
            assert first['status'] == 'succeeded'
            if changed in {'model', 'instructions'}:
                scene = system.chat.repository.scene('analyze')
                patch = {'model_id_': 'other-model'} if changed == 'model' else {'instructions': 'different role instructions'}
                system.chat.repository.save_scene('analyze', dto.SaveLocalSceneInput(expectedVersion=scene.version,
                    roles=[role.model_copy(update=patch) for role in scene.roles]))
            elif changed in {'closed', 'invalid'}:
                sessions = system.tasks.runtime.sessions.repository
                session = await sessions.get(system.adapter.started[0].session_id)
                await sessions.save(session.model_copy(update={'status': dto.SessionStatus(changed), 'is_valid': changed != 'invalid'}))
            elif changed == 'recovery':
                spec = system.tasks.state.get('task_spec:' + first['task_id'])
                spec['recoveryRequired'] = True
                system.tasks.state.put('task_spec:' + first['task_id'], spec)
            else:
                # Simulate a preserved historical snapshot with a different
                # acceptance mode; comparison happens before any new dispatch.
                old_scene = json.loads(first['scene_json'])
                old_scene['reviewMode'] = 'original_planner'
                with system.db.transaction() as tx:
                    tx.connection.execute('UPDATE local_runs SET scene_json=? WHERE run_id=?',
                        (json.dumps(old_scene), first['run_id']))
            second = await send(system, conversation, 'second')
            assert second['status'] == 'failed'
            assert system.chat.repository.failure_code(second['run_id']) == 'SESSION_NOT_RESUMABLE'
            assert len(system.adapter.started) == 1 and not system.adapter.resumed
            assert observation(system, second['run_id']) is None
            if changed == 'recovery':
                assert '恢复核对' in second['error']
            else:
                assert '右上角 +' in second['error'] and '新话题' in second['error']
            assert '新一轮上下文' not in second['error']
        finally:
            await system.close()
    asyncio.run(scenario())


def test_history_window_cannot_hide_an_older_executed_context(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await create(system)
            await system.chat.start()
            first = await send(system, conversation, 'first')
            await system.chat.stop()
            for index in range(205):
                receipt = system.chat.repository.enqueue(conversation, dto.SendLocalMessageInput(
                    clientMessageId=f'failed-{index}', text='not dispatched', sessionMode='continue'), f'failed-{index}')
                system.chat.repository.complete_run(receipt.run_id, 'failed', 'not dispatched')
            assert all(not row['task_id'] for row in system.chat.repository.runs(conversation))
            await system.chat.start()
            current = await send(system, conversation, 'after-window')
            assert current['status'] == 'succeeded', current['error']
            assert len(system.adapter.started) == 1 and len(system.adapter.resumed) == 1
            assert observation(system, current['run_id'])['effectiveMode'] == 'continue'
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('agent', ['claude', 'codex'])
def test_native_import_first_continue_keeps_original_external_session(tmp_path, agent):
    from test_r3_native import fixture_history, setup_native, indexed_listing
    async def scenario():
        system = System(tmp_path)
        try:
            source = tmp_path / 'native'
            fixture_history(source, tmp_path, agent)
            native = setup_native(system, source, agent)
            item = (await indexed_listing(native)).items[0]
            imported = await native.import_session(item.native_session_id, dto.RemoteNativeImportInput(
                terminalClosedConfirmed=True, expectedIndexVersion=item.index_version, sourceRevision=item.source_revision), 'import', 'request')
            assert not system.chat.repository.runs(imported.id)
            await system.chat.start()
            record = await send(system, imported.id, 'native-first')
            assert record['status'] == 'succeeded', record['error']
            assert not system.adapter.started and len(system.adapter.resumed) == 1
            assert system.adapter.resumed[0].external_session_id == '00000000-0000-4000-8000-000000000001'
            assert observation(system, record['run_id']) == {
                'requestedMode': 'continue', 'effectiveMode': 'continue', 'reason': 'native_bound_session'}
        finally:
            await system.close()
    asyncio.run(scenario())


def test_real_phone_create_then_first_continue_with_image(tmp_path):
    from test_image_target_resolution import configure, view, verify
    from test_r16_attachments import headers, synced
    from runtime.attachments.verification import synthetic_inputs
    async def scenario():
        async with RealPair(tmp_path, revision=4) as pair:
            caps = configure(pair.system, [view()])
            verify(caps)
            await caps.refresh()
            await synced(pair)
            await until(lambda: not pair.system.repo.frames())
            with pair.service.repo.transaction() as tx:
                catalog = tx.get(pair.owner, 'catalog', pair.worker_id)
            created = await pair.browser.post('/conversations', json={
                'targetWorkerId': pair.worker_id, 'workerStoreId': pair.system.repo.get('identity')['store'],
                'workspaceId': catalog['workspaces'][0]['workspaceId'], 'sceneId': 'analyze', 'sceneVersion': 1,
                'title': 'phone first image'}, headers={'Idempotency-Key': 'phone-create'})
            assert created.status_code == 202, created.text
            create_id = created.json()['data']['commandId']
            conversation = created.json()['data']['conversationId']
            await until(lambda: pair.system.worker.delivery.row(create_id) and pair.system.worker.delivery.row(create_id)['state'] == 'completed')
            def visible():
                with pair.service.repo.transaction() as tx:
                    record = tx.get(pair.owner, 'command', create_id)
                    return record['status'] == 'completed' and tx.get(pair.owner, 'conversation', conversation) is not None
            await until(visible)
            image_dir = tmp_path / 'images'
            image_dir.mkdir()
            png = synthetic_inputs(image_dir)[0][0]
            body = Path(png.local_path).read_bytes()
            upload = await pair.browser.post(f'/conversations/{conversation}/attachments', content=body, headers=headers(body, 'input.png'))
            assert upload.status_code == 201, upload.text
            identifier = upload.json()['data']['attachment']['attachmentId']
            pair.system.worker.attachments.library.http_factory = lambda: httpx.AsyncClient(verify=pair.tls, follow_redirects=False, trust_env=False)
            sent = await pair.browser.post(f'/conversations/{conversation}/messages', json={
                'clientMessageId': 'first-image', 'text': 'inspect this image', 'sessionMode': 'continue',
                'attachmentIds': [identifier]}, headers={'Idempotency-Key': 'first-image'})
            assert sent.status_code == 202, sent.text
            command = sent.json()['data']['commandId']
            await until(lambda: pair.system.worker.delivery.row(command) and
                pair.system.worker.delivery.row(command)['state'] in {'completed', 'failed', 'rejected'})
            row = pair.system.worker.delivery.row(command)
            assert row['state'] == 'completed', row['result_json']
            await until(lambda: pair.system.chat.repository.run_record(row['run_id'])['status'] == 'succeeded')
            assert len(pair.system.adapter.started) == 1 and not pair.system.adapter.resumed
            assert pair.system.adapter.started[0].input_attachments[0].attachment.kind == 'image'
            assert observation(pair.system, row['run_id'])['effectiveMode'] == 'new'
            original = next(f for f in pair.received if f['type'] == 'run.submit' and f['commandId'] == command)
            assert original['payload']['sessionMode'] == 'continue'
    asyncio.run(scenario())
