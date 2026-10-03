import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
import httpx
import pytest
from protocol.generated import python as dto
from remote_support import System, until
from runtime.attachments.capabilities import VerificationStore, REQUIRED_PROBES
from adapters.path_guard import PathGuard
from test_r15_joint_server import RealPair, server_source

def headers(body, name='input.txt', key='upload'):
    return {'Content-Type': 'application/octet-stream', 'Content-Length': str(len(body)), 'X-Content-Sha256': hashlib.sha256(body).hexdigest(), 'X-File-Name': quote(name, safe=''), 'Idempotency-Key': key}

async def synced(pair):
    await until(lambda: pair.system.repo.get('sync-work')['phase'] == 'synced')

async def upload_phone(pair, body=b'ATTACHMENT_CONTENT'):
    await synced(pair)
    conversation = pair.cloud_conversation(pair.legacy_ids[0])['conversationId']
    response = await pair.browser.post('/conversations/' + conversation + '/attachments', content=body, headers=headers(body))
    assert response.status_code == 201, response.text
    attachment = dto.RemoteAttachmentView.model_validate(response.json()['data']).attachment
    return (conversation, attachment)

async def send_phone(pair, conversation, attachment):
    response = await pair.browser.post('/conversations/' + conversation + '/messages', json={'clientMessageId': 'with-input', 'text': 'Read the supplied file', 'sessionMode': 'new', 'attachmentIds': [attachment.attachment_id]}, headers={'Idempotency-Key': 'with-input'})
    assert response.status_code == 202, response.text
    return response.json()['data']['commandId']

def test_local_library_streams_binds_and_limits_exact_read_scope(tmp_path):

    async def scenario():
        system = System(tmp_path)
        try:
            created = await system.local.post('/api/v2/conversations', json={'title': 'inputs', 'workspaceId': 'workspace', 'sceneId': 'analyze'}, headers={'Idempotency-Key': 'create'})
            conversation = created.json()['data']['id']
            body = b'LOCAL_FILE_PRIVATE_BODY'
            path = f'/api/v2/conversations/{conversation}/attachments'
            uploaded = await system.local.post(path, content=body, headers=headers(body, '../../private.txt'))
            assert uploaded.status_code == 201, uploaded.text
            value = dto.LocalAttachmentView.model_validate(uploaded.json()['data'])
            assert value.attachment.file_name == 'private.txt' and str(tmp_path) not in uploaded.text
            replay = await system.local.post(path, content=body, headers=headers(body, '../../private.txt'))
            assert replay.json()['data'] == uploaded.json()['data']
            original = await system.local.get('/api/v2/attachments/' + value.attachment.attachment_id + '/content')
            assert original.content == body and original.headers['cache-control'] == 'no-store'
            assert original.headers['content-disposition'].startswith('attachment;')
            assert (await system.local.get('/api/v2/attachments/' + value.attachment.attachment_id + '/thumbnail')).json()['error']['code'] == 'ATTACHMENT_THUMBNAIL_UNAVAILABLE'
            await system.chat.start()
            sent = await system.local.post(f'/api/v2/conversations/{conversation}/messages', json={'text': 'read input', 'clientMessageId': 'input', 'sessionMode': 'new', 'attachmentIds': [value.attachment.attachment_id]}, headers={'Idempotency-Key': 'input'})
            assert sent.status_code == 202, sent.text
            run = sent.json()['data']['runId']
            await until(lambda: system.chat.repository.run_record(run)['status'] in {'failed', 'succeeded'})
            assert system.chat.repository.run_record(run)['status'] == 'succeeded', system.chat.repository.run_record(run)['error']
            spec = system.adapter.started[0]
            assert len(spec.input_attachments) == 1
            attachment = spec.input_attachments[0]
            assert Path(attachment.local_path).read_bytes() == body
            isolated = tmp_path / 'isolated'
            isolated.mkdir()
            guard = PathGuard(str(isolated), ['**'], input_attachments=spec.input_attachments)
            assert guard.contains(attachment.local_path) and (not guard.allows(attachment.local_path))
            assert not guard.contains(str(Path(attachment.local_path).parent))
            overlapping = PathGuard(str(tmp_path), ['**'], input_attachments=spec.input_attachments)
            assert overlapping.contains(attachment.local_path)
            assert not overlapping.allows(attachment.local_path)
            deletion = await system.local.delete('/api/v2/attachments/' + value.attachment.attachment_id, headers={'Idempotency-Key': 'delete'})
            assert deletion.json()['error']['code'] == 'ATTACHMENT_IN_USE'
            messages = await system.local.get(f'/api/v2/conversations/{conversation}/messages')
            assert messages.json()['data'][0]['attachments'][0]['attachmentId'] == value.attachment.attachment_id
            assert attachment.local_path not in messages.text
        finally:
            await system.close()
    asyncio.run(scenario())

def test_real_phone_input_download_is_verified_before_agent_start(tmp_path):

    async def scenario():
        async with RealPair(tmp_path, revision=4) as pair:
            pair.system.worker.attachments.library.http_factory = lambda: httpx.AsyncClient(verify=pair.tls, follow_redirects=False, trust_env=False)
            conversation, attachment = await upload_phone(pair)
            command = await send_phone(pair, conversation, attachment)
            await until(lambda: pair.system.worker.delivery.row(command) and pair.system.worker.delivery.row(command)['state'] in {'completed', 'failed', 'rejected'}, timeout=15)
            state = pair.system.worker.delivery.row(command)
            assert state['state'] == 'completed', state['result_json']
            spec = pair.system.adapter.started[0]
            assert len(spec.input_attachments) == 1 and Path(spec.input_attachments[0].local_path).read_bytes() == b'ATTACHMENT_CONTENT'
            assert spec.input_attachments[0].local_path not in json.dumps(pair.sent)
            assert all((f['wireRevision'] == 4 for f in pair.sent if f.get('payload', {}).get('attachments')))
    asyncio.run(scenario())

def test_real_local_pending_message_precedes_upload_and_available_revision(tmp_path):

    async def scenario():
        async with RealPair(tmp_path, revision=4) as pair:
            pair.system.worker.attachments.library.http_factory = lambda: httpx.AsyncClient(verify=pair.tls, follow_redirects=False, trust_env=False)
            await synced(pair)
            conversation = pair.legacy_ids[0]
            body = b'LOCAL_UPLOAD_FILE'
            response = await pair.system.local.post(f'/api/v2/conversations/{conversation}/attachments', content=body, headers=headers(body))
            assert response.status_code == 201, response.text
            item = response.json()['data']['attachment']['attachmentId']
            sent = await pair.system.local.post(f'/api/v2/conversations/{conversation}/messages', json={'text': 'local input', 'clientMessageId': 'local-input', 'sessionMode': 'new', 'attachmentIds': [item]}, headers={'Idempotency-Key': 'local-input'})
            assert sent.status_code == 202, sent.text
            await until(lambda: pair.system.worker.attachments.repo.view(item).sync_status in {'available', 'unavailable'}, timeout=15)
            value = pair.system.worker.attachments.repo.view(item)
            assert value.sync_status == 'available', value.sync_error
            await until(lambda: any((f['type'] == 'sync.message.segment' and any((a['availability'] == 'available' for a in f['payload'].get('attachments', []))) for f in pair.sent)))
            frames = [f for f in pair.sent if f['type'] == 'sync.message.segment' and f['payload']['messageId'] == sent.json()['data']['messageId']]
            assert frames[0]['payload']['attachments'][0]['availability'] == 'pending_upload'
            assert frames[-1]['payload']['messageRevision'] > frames[0]['payload']['messageRevision']
            assert pair.system.repo.get('link')['view']['state'] == 'paired'
    asyncio.run(scenario())

@pytest.mark.parametrize('mismatch', ['hash', 'length'])
def test_download_integrity_failure_never_starts_agent(tmp_path, mismatch):

    async def scenario():
        async with RealPair(tmp_path, revision=4) as pair:
            conversation, attachment = await upload_phone(pair)
            calls = []

            def corrupt(request):
                calls.append(True)
                return httpx.Response(200, content=b'X' * attachment.size_bytes, headers={'Content-Length': str(attachment.size_bytes + (1 if mismatch == 'length' else 0))})
            pair.system.worker.attachments.library.http_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(corrupt))
            command = await send_phone(pair, conversation, attachment)
            await until(lambda: pair.system.worker.delivery.row(command) and pair.system.worker.delivery.row(command)['state'] == 'failed')
            result = json.loads(pair.system.worker.delivery.row(command)['result_json'])
            assert result['error']['code'] == 'ATTACHMENT_HASH_MISMATCH'
            assert calls == [True] and (not pair.system.adapter.started)
            assert pair.system.worker.busy.ids() == []
            assert not list(pair.system.worker.attachments.library.root.glob('*/*.part'))
    asyncio.run(scenario())

def test_verification_records_are_bound_to_current_version_and_complete_probes(tmp_path):
    store = VerificationStore(tmp_path)
    assert not store.capability('claude', '2.1.285').verified
    store.record('claude', '2.1.285', None, {'new': True}, ['image/png'])
    assert not store.capability('claude', '2.1.285').verified
    store.record('claude', '2.1.285', None, {key: True for key in REQUIRED_PROBES}, ['image/png'])
    assert store.capability('claude', '2.1.285').verified
    assert not store.capability('claude', '2.1.286').verified
    assert not store.capability('claude', '2.1.285', 'other-model').verified

class HeldBody(httpx.AsyncByteStream):

    def __init__(self):
        self.entered = asyncio.Event()
        self.closed = asyncio.Event()

    async def __aiter__(self):
        self.entered.set()
        yield b'ATTACHMENT_'
        await asyncio.Event().wait()

    async def aclose(self):
        self.closed.set()

@pytest.mark.parametrize('restart', [False, True])
def test_preparation_cancel_or_restart_releases_busy_without_agent(tmp_path, restart):

    async def scenario():
        from test_r3_native import setup_native
        async with RealPair(tmp_path, revision=4) as pair:
            conversation, attachment = await upload_phone(pair)
            body = HeldBody()
            pair.system.worker.attachments.library.http_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=body, headers={'Content-Length': str(attachment.size_bytes)})))
            command = await send_phone(pair, conversation, attachment)
            await asyncio.wait_for(body.entered.wait(), 8)
            row = pair.system.worker.delivery.row(command)
            run = row['run_id']
            assert pair.legacy_ids[0] in pair.system.worker.busy.ids()
            assert not pair.system.adapter.started
            if restart:
                await pair.system.close()
                pair.system = System(tmp_path)
                setup_native(pair.system, tmp_path / 'empty-native')
                pair.system.worker.connector = pair.connect
                await pair.system.chat.start()
                # Recovery happens before connecting, even when the server is offline.
                prep = pair.system.worker.attachments.repo.preparation(run)
                assert prep['state'] == 'failed'
                assert prep['error_code'] == 'ATTACHMENT_PREPARATION_INTERRUPTED'
                assert pair.system.worker.busy.ids() == []
                await pair.system.worker.start()
                await until(lambda: pair.system.worker.delivery.row(command)['state'] == 'failed')
            else:
                with pair.service.repo.transaction() as tx:
                    public_run = tx.get(pair.owner, 'command', command)['resultRef']['runId']
                response = await pair.browser.post('/runs/' + public_run + '/commands', json={'action': 'cancel'}, headers={'Idempotency-Key': 'cancel-input'})
                assert response.status_code == 202, response.text
                cancel = response.json()['data']['commandId']
                await until(lambda: pair.system.worker.delivery.row(cancel) and pair.system.worker.delivery.row(cancel)['state'] in {'completed', 'failed', 'unconfirmed'})
                result = json.loads(pair.system.worker.delivery.row(cancel)['result_json'])
                assert result['controlResult']['outcome'] == 'confirmed', result
                assert result['controlResult']['evidence'] == 'input_preparation_cancelled'
                assert pair.system.worker.busy.ids() == []
            assert body.closed.is_set()
            assert not pair.system.adapter.started
            assert not list(pair.system.worker.attachments.library.root.glob('*/*.part'))
            if restart:
                pair.system.worker.attachments.library.http_factory = lambda: httpx.AsyncClient(verify=pair.tls, follow_redirects=False, trust_env=False)
                with pair.service.repo.transaction() as tx:
                    public_run = tx.get(pair.owner, 'command', command)['resultRef']['runId']
                response = await pair.browser.post('/runs/' + public_run + '/commands', json={'action': 'retry'}, headers={'Idempotency-Key': 'retry-interrupted-input'})
                assert response.status_code == 202, response.text
                retry = response.json()['data']['commandId']
                await until(lambda: pair.system.worker.delivery.row(retry) and pair.system.worker.delivery.row(retry)['state'] in {'completed', 'failed', 'unconfirmed'})
                result = json.loads(pair.system.worker.delivery.row(retry)['result_json'])
                assert result['resultStatus'] == 'retry_enqueued', result
                retry_run = result['resultRef']['runId']
                assert retry_run != run
                await until(lambda: pair.system.chat.repository.run_record(retry_run)['status'] in {'succeeded', 'failed'})
                assert pair.system.chat.repository.run_record(retry_run)['status'] == 'succeeded'
                assert len(pair.system.adapter.started) == 1
                await until(lambda: not pair.system.repo.frames())
                assert pair.system.repo.get('link')['view']['state'] == 'paired'
    asyncio.run(scenario())

def test_image_encodings_are_local_only_and_check_exact_bytes(tmp_path):
    import base64
    from adapters.attachment_input import claude_input, claude_session_args, codex_input, codex_exec_args
    from core.errors import HubError
    # Encoding tests do not invoke a CLI or decode a real user's image.
    body = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aM1sAAAAASUVORK5CYII=')
    path = tmp_path / 'synthetic.png'
    path.write_bytes(body)
    value = dto.AgentInputAttachment(attachment={'attachmentId': 'synthetic-image', 'fileName': 'image.png', 'kind': 'image', 'mimeType': 'image/png', 'sizeBytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}, localPath=str(path))
    encoded = json.loads(claude_input('describe', [value]))
    image = encoded['message']['content'][1]
    assert image['type'] == 'image' and image['source']['media_type'] == 'image/png'
    assert base64.b64decode(image['source']['data']) == body
    assert str(path) not in json.dumps(encoded)
    assert claude_session_args('exact-session', resume=True, has_attachments=True) == ['--input-format', 'stream-json', '--resume', 'exact-session']
    assert claude_session_args('new-session', resume=False, has_attachments=False) == ['--session-id', 'new-session']
    assert codex_input('describe', [value])[1] == {'type': 'localImage', 'path': str(path)}
    assert codex_exec_args('codex', 'describe', [value], resume_id='exact-thread')[1:6] == ['exec', 'resume', 'exact-thread', '--image', str(path)]
    path.write_bytes(body[:-1])
    with pytest.raises(HubError) as caught:
        claude_input('describe', [value])
    assert caught.value.code == 'ATTACHMENT_HASH_MISMATCH'

def test_resumed_input_scope_is_replaced_not_carried_to_next_turn(tmp_path):
    from adapters.tests.test_contract_rules import StartableCodex, task_spec

    async def scenario():
        adapter = StartableCodex()
        workspace = tmp_path / 'workspace'
        workspace.mkdir()
        file = tmp_path / 'input.txt'
        file.write_bytes(b'synthetic input')
        value = dto.AgentInputAttachment(attachment={'attachmentId': 'input', 'fileName': 'input.txt', 'kind': 'file', 'mimeType': 'text/plain', 'sizeBytes': file.stat().st_size, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}, localPath=str(file))
        initial = task_spec(workspace)
        handle = await adapter.start(initial)
        current = initial.model_copy(update={'input_attachments': [value]})
        result = await adapter.resume(dto.ResumeRequest(sessionId=handle.session_id, externalSessionId=handle.external_session_id, message='read this turn', taskSpec=current))
        assert result is None
        state = adapter.registry.get(handle.session_id)
        assert state.guard.contains(str(file)) and (not state.guard.allows(str(file)))
        assert state.spec.input_attachments == [value]
        await adapter.resume(dto.ResumeRequest(sessionId=handle.session_id, externalSessionId=handle.external_session_id, message='text only', taskSpec=initial))
        assert not state.spec.input_attachments and (not state.guard.contains(str(file)))
    asyncio.run(scenario())

def test_attachment_message_waits_for_wire4_fence_then_backfills(tmp_path):

    async def scenario():
        from server import wire
        all_codecs = dict(wire.CODECS)
        async with RealPair(tmp_path, revision=3) as pair:
            await synced(pair)
            local = pair.legacy_ids[0]
            body = b'DEFERRED_ATTACHMENT'
            response = await pair.system.local.post(f'/api/v2/conversations/{local}/attachments', content=body, headers=headers(body))
            identifier = response.json()['data']['attachment']['attachmentId']
            sent = await pair.system.local.post(f'/api/v2/conversations/{local}/messages', json={'text': 'defer entire message', 'sessionMode': 'new', 'clientMessageId': 'deferred', 'attachmentIds': [identifier]}, headers={'Idempotency-Key': 'deferred'})
            assert sent.status_code == 202, sent.text
            message, run = (sent.json()['data']['messageId'], sent.json()['data']['runId'])
            await until(lambda: pair.system.chat.repository.run_record(run)['status'] == 'succeeded')
            await until(lambda: not pair.system.repo.frames())
            assert not any((f['type'] == 'sync.message.segment' and f['payload']['messageId'] == message for f in pair.sent))
            assert pair.system.worker.attachments.repo.view(identifier).sync_status == 'not_synced'
            pair.system.worker.attachments.library.http_factory = lambda: httpx.AsyncClient(verify=pair.tls, follow_redirects=False, trust_env=False)
            pair.wire_patch.setattr(wire, 'CODECS', all_codecs)
            pair.system.worker.next_revision2_probe = 0
            await until(lambda: pair.system.repo.get('identity')['wireRevision'] == 4, timeout=12)
            await until(lambda: pair.system.worker.attachments.repo.view(identifier).sync_status == 'available', timeout=12)
            segments = [f for f in pair.sent if f['type'] == 'sync.message.segment' and f['payload']['messageId'] == message]
            assert segments and all((f['wireRevision'] == 4 for f in segments))
            assert pair.system.repo.get('identity')['upgradeFence']['server'] is not None
            assert len(pair.system.adapter.started) == 1
    asyncio.run(scenario())

def test_pause_allows_desktop_upload_but_sync_off_prevents_it(tmp_path):

    async def scenario():
        async with RealPair(tmp_path, revision=4) as pair:
            await synced(pair)
            device = (await pair.browser.get('/devices/' + pair.worker_id)).json()['data']
            paused = await pair.browser.patch('/devices/' + pair.worker_id, json={'expectedVersion': device['version'], 'remoteAccess': 'suspended'}, headers={'Idempotency-Key': 'suspend'})
            assert paused.status_code == 200, paused.text
            local = pair.legacy_ids[0]
            public = pair.cloud_conversation(local)['conversationId']
            body = b'DESKTOP_DURING_PAUSE'
            denied = await pair.browser.post('/conversations/' + public + '/attachments', content=body, headers=headers(body))
            assert denied.status_code >= 400
            pair.system.worker.attachments.library.http_factory = lambda: httpx.AsyncClient(verify=pair.tls, follow_redirects=False, trust_env=False)

            async def local_message(key):
                uploaded = await pair.system.local.post(f'/api/v2/conversations/{local}/attachments', content=body, headers=headers(body, key=key))
                assert uploaded.status_code == 201, uploaded.text
                identifier = uploaded.json()['data']['attachment']['attachmentId']
                sent = await pair.system.local.post(f'/api/v2/conversations/{local}/messages', json={'text': key, 'sessionMode': 'new', 'clientMessageId': key, 'attachmentIds': [identifier]}, headers={'Idempotency-Key': key})
                assert sent.status_code == 202, sent.text
                await until(lambda: pair.system.chat.repository.run_record(sent.json()['data']['runId'])['status'] == 'succeeded')
                return identifier
            first = await local_message('paused-upload')
            await until(lambda: pair.system.worker.attachments.repo.view(first).sync_status == 'available')
            setting = pair.system.worker.sync.settings()
            pair.system.worker.sync.set_settings(dto.RemoteSyncSettingsInput(expectedVersion=setting.version, mirrorEnabled=False), 'disable')
            await until(lambda: pair.system.repo.get('sync-work')['phase'] == 'disabled')
            calls = []

            def forbidden(request):
                calls.append(request.method)
                return httpx.Response(500)
            pair.system.worker.attachments.library.http_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(forbidden))
            second = await local_message('disabled-upload')
            await pair.system.worker.attachments.sync.tick()
            assert not calls
            assert pair.system.worker.attachments.repo.view(second).sync_status == 'not_synced'
    asyncio.run(scenario())

def test_verify_image_entry_uses_injected_adapter_and_persists_version(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from orchestrator.tests.fakes import FakeAdapter
    from runtime.attachments import verification
    original = verification.synthetic_inputs
    adapter = FakeAdapter()

    def synthetic(path):
        values, colors, nonce = original(path)
        assert len(colors) == 16 and len({tuple(colors[i:i + 4]) for i in range(0, 16, 4)}) == 4
        assert not verification.recognizes(' '.join(colors[:4]) + ' ' + nonce, colors, nonce)
        adapter.result = adapter.result.model_copy(update={'summary': ' '.join(colors) + ' ' + nonce})
        return (values, colors, nonce)

    async def detect():
        return SimpleNamespace(detected_version='2.1.285')
    monkeypatch.setattr(verification, 'synthetic_inputs', synthetic)
    monkeypatch.setattr(adapter, 'detect', detect)
    record = asyncio.run(verification.verify_images(tmp_path, 'claude', adapter=adapter))
    assert record['passed'] and set(record['probes']) == REQUIRED_PROBES
    assert len(adapter.started) == 2 and len(adapter.resumed) == 2
    assert adapter.resumed[0].external_session_id == adapter.handle.external_session_id
    assert len(adapter.resumed[1].task_spec.input_attachments) == 5
    assert VerificationStore(tmp_path).capability('claude', '2.1.285').verified
    assert not VerificationStore(tmp_path).capability('claude', '2.1.286').verified
    assert not list((tmp_path / 'image-verification').glob('probe-*'))

def test_real_phone_image_uses_verified_catalog_and_local_input(tmp_path):

    async def scenario():
        from dataclasses import replace
        from types import SimpleNamespace
        from runtime.attachments.verification import synthetic_inputs
        async with RealPair(tmp_path, revision=4) as pair:
            image_dir = tmp_path / 'synthetic'
            image_dir.mkdir()
            image = synthetic_inputs(image_dir)[0][0]
            pair.system.tasks.directory.candidates = tuple((replace(a, adapter_id='claude') for a in pair.system.tasks.directory.candidates))
            pair.system.adapter.handle = pair.system.adapter.handle.model_copy(update={'adapter_id': 'claude'})

            async def detect():
                return SimpleNamespace(detected_version='2.1.285')
            pair.system.adapter.detect = detect

            async def agents():
                return [dto.AgentView(id='agent', adapterId='claude', displayName='synthetic', version='2.1.285', status='ready', detectedAt='2026-09-30T00:00:00Z', capabilities=[], assignedRoles=[], isPrimaryFor=[])]
            pair.system.ports.agents = SimpleNamespace(list_agents=agents)
            scene = pair.system.chat.repository.scene('analyze')
            pair.system.chat.repository.save_scene('analyze', dto.SaveLocalSceneInput(expectedVersion=scene.version, roles=[r.model_copy(update={'agent_instance_id': 'agent'}) for r in scene.roles]))
            caps = pair.system.worker.attachments.capabilities
            caps.store.record('claude', '2.1.285', None, {key: True for key in REQUIRED_PROBES}, ['image/png'])
            await caps.refresh()
            await pair.system.worker.projector.catalog()
            await until(lambda: not pair.system.repo.frames())
            await synced(pair)
            created = await pair.system.local.post('/api/v2/conversations', json={'title': 'verified image target', 'workspaceId': 'workspace', 'sceneId': 'analyze'}, headers={'Idempotency-Key': 'image-conversation'})
            assert created.status_code == 201, created.text
            local = created.json()['data']['id']
            await until(lambda: pair.cloud_conversation(local) is not None)
            public = pair.cloud_conversation(local)['conversationId']
            body = Path(image.local_path).read_bytes()
            response = await pair.browser.post('/conversations/' + public + '/attachments', content=body, headers=headers(body, 'synthetic.png'))
            assert response.status_code == 201, response.text
            identifier = response.json()['data']['attachment']['attachmentId']
            pair.system.worker.attachments.library.http_factory = lambda: httpx.AsyncClient(verify=pair.tls, follow_redirects=False, trust_env=False)
            sent = await pair.browser.post('/conversations/' + public + '/messages', json={'text': 'inspect synthetic image', 'clientMessageId': 'image-input', 'sessionMode': 'new', 'attachmentIds': [identifier]}, headers={'Idempotency-Key': 'image-input'})
            assert sent.status_code == 202, sent.text
            command = sent.json()['data']['commandId']
            await until(lambda: pair.system.worker.delivery.row(command) and pair.system.worker.delivery.row(command)['state'] in {'completed', 'failed', 'rejected'})
            row = pair.system.worker.delivery.row(command)
            assert row['state'] == 'completed', row['result_json']
            await until(lambda: pair.system.chat.repository.run_record(row['run_id'])['status'] in {'succeeded', 'failed'})
            assert pair.system.chat.repository.run_record(row['run_id'])['status'] == 'succeeded'
            inputs = pair.system.adapter.started[0].input_attachments
            assert len(inputs) == 1 and inputs[0].attachment.kind == 'image'
            assert Path(inputs[0].local_path).read_bytes() == body
    asyncio.run(scenario())

def test_cookie_attachment_library_auth_expiry_cleanup_and_redaction(tmp_path, caplog):

    async def scenario():
        from remote_support import TOKEN
        from test_remote_cookie_routes import login, ORIGIN
        system = System(tmp_path)
        try:
            system.local.headers.pop('Authorization')
            assert (await system.local.get('/api/v2/attachments/limits')).status_code == 401
            await login(system)
            created = await system.local.post('/api/v2/conversations', json={'title': 'cookie attachments', 'workspaceId': 'workspace', 'sceneId': 'analyze'}, headers={'Origin': ORIGIN, 'Idempotency-Key': 'create'})
            conversation = created.json()['data']['id']
            url = f'/api/v2/conversations/{conversation}/attachments'
            body = b'synthetic cookie upload'
            denied = await system.local.post(url, content=body, headers=headers(body))
            assert denied.status_code == 403
            responses = []
            for prefix in ('/api/v1', '/api/v2'):
                auth = {'Authorization': 'Bearer ' + TOKEN} if prefix.endswith('1') else {}
                limits = await system.local.get(prefix + '/attachments/limits', headers=auth)
                dto.AttachmentLimits.model_validate(limits.json()['data'])
                assert limits.headers['Cache-Control'] == 'no-store'
                responses.append(limits.text)
            upload_headers = {**headers(body, TOKEN + '.txt'), 'Origin': ORIGIN}
            uploaded = await system.local.post(url, content=body, headers=upload_headers)
            assert uploaded.status_code == 201, uploaded.text
            responses.append(uploaded.text)
            identifier = uploaded.json()['data']['attachment']['attachmentId']
            row = system.worker.attachments.repo.row(identifier)
            path = system.worker.attachments.library.path(row)
            assert path.parent.name == conversation and path.read_bytes() == body
            assert (await system.local.get('/api/v2/attachments/' + identifier + '/content', headers={'Range': 'bytes=0-2'})).status_code == 400
            rejected = await system.local.post(f'/api/v2/conversations/{conversation}/messages', json={'clientMessageId': 'many', 'text': 'too many', 'sessionMode': 'new', 'attachmentIds': ['x'] * 6}, headers={'Origin': ORIGIN, 'Idempotency-Key': 'many'})
            assert rejected.json()['error']['code'] == 'ATTACHMENT_COUNT_EXCEEDED'
            with system.db.transaction() as tx:
                tx.connection.execute("UPDATE local_attachments SET expires_at='2000-01-01T00:00:00Z' WHERE attachment_id=?", (identifier,))
            assert (await system.local.get('/api/v2/attachments/' + identifier)).status_code == 404
            system.worker.attachments.library.maintenance_at = 0
            await system.worker.attachments.library.maintain()
            assert not path.exists()
            assert system.worker.attachments.repo.row(identifier, available=False)['manifest_json'] == '{}'
            assert TOKEN not in '\n'.join(responses) + caplog.text
            # A deleted conversation triggers the same attachment file cleanup,
            # without introducing a new, unfrozen HTTP deletion operation.
            second = await system.local.post(url, content=body, headers={**headers(body, key='second'), 'Origin': ORIGIN})
            item = second.json()['data']['attachment']['attachmentId']
            file = system.worker.attachments.library.path(system.worker.attachments.repo.row(item))
            with system.db.transaction() as tx:
                tx.connection.execute('DELETE FROM local_conversations WHERE conversation_id=?', (conversation,))
            system.worker.attachments.library.maintenance_at = 0
            await system.worker.attachments.library.maintain()
            assert not file.exists()
        finally:
            await system.close()
    asyncio.run(scenario())

@pytest.mark.parametrize('status,attempts', [(503, 3), (403, 1), (302, 1)])
def test_download_retries_only_transient_errors_and_never_redirects(tmp_path, status, attempts, caplog):
    import logging
    caplog.set_level(logging.DEBUG, logger='httpx')

    async def scenario():
        from core.errors import HubError
        system = System(tmp_path)
        try:
            system.link.vault.create()
            with system.db.transaction() as tx:
                system.repo.set_view(tx, {'state': 'paired', 'workerId': 'worker-test', 'deviceName': 'synthetic', 'serverOrigin': 'https://paired.invalid', 'connectionStatus': 'offline', 'lastConnectedAt': None})
                system.repo.seal(tx)
            seen = []

            def response(request):
                seen.append((request.url.host, request.url.path))
                return httpx.Response(status, headers={'Location': 'https://outside.invalid/collect'})
            library = system.worker.attachments.library
            library.http_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(response), follow_redirects=True)
            manifest = {'attachmentId': 'file', 'fileName': 'input.txt', 'kind': 'file', 'mimeType': 'text/plain', 'sizeBytes': 1, 'sha256': hashlib.sha256(b'x').hexdigest()}
            with pytest.raises(HubError) as caught:
                await library.fetch(manifest, 'conversation', 'command')
            assert caught.value.code == 'ATTACHMENT_DOWNLOAD_FAILED'
            assert seen == [('paired.invalid', '/api/v2/worker/attachments/file/content')] * attempts
            assert not list(library.root.glob('*/*.part'))
            assert 'paired.invalid' not in caplog.text
            assert system.link.vault.read() not in caplog.text
        finally:
            await system.close()
    asyncio.run(scenario())


def test_wire4_preserves_native_ephemeral_reads(tmp_path):
    async def scenario():
        async with RealPair(tmp_path, revision=4, native_history=True) as pair:
            await synced(pair)
            page = await pair.browser.get(f'/devices/{pair.worker_id}/native-sessions')
            indexes = dto.RemoteNativeSessionPage.model_validate(page.json()['data'])
            assert len(indexes.items) == 1
            identifier = indexes.items[0].native_session_id
            response = await pair.browser.get(f'/native-sessions/{identifier}/messages')
            assert response.status_code == 200, response.text
            dto.NativeMessagePage.model_validate(response.json()['data'])
            results = [frame for frame in pair.sent if frame['type'].startswith('query.')]
            assert results and all(frame['wireRevision'] == 4 for frame in results)
            assert pair.system.repo.get('link')['view']['state'] == 'paired'
    asyncio.run(scenario())


def test_reset_reenable_uses_new_bindings_for_downloaded_phone_inputs(tmp_path):
    async def scenario():
        async with RealPair(tmp_path, revision=4) as pair:
            pair.system.worker.attachments.library.http_factory = lambda: httpx.AsyncClient(
                verify=pair.tls, follow_redirects=False, trust_env=False)
            conversation, original = await upload_phone(pair)
            command = await send_phone(pair, conversation, original)
            await until(lambda: pair.system.worker.delivery.row(command) and
                pair.system.worker.delivery.row(command)['state'] == 'completed')
            run = pair.system.worker.delivery.row(command)['run_id']
            await until(lambda: pair.system.chat.repository.run_record(run)['status'] == 'succeeded')
            message = pair.system.chat.repository.run_record(run)['message_id']
            local_id = pair.system.worker.attachments.repo.message_rows(message)[0]['attachment_id']
            sync = pair.system.worker.sync
            setting = sync.settings()
            sync.set_settings(dto.RemoteSyncSettingsInput(expectedVersion=setting.version, mirrorEnabled=False), 'reset-inputs')
            await until(lambda: pair.system.repo.get('sync-work')['phase'] == 'disabled')
            assert pair.system.worker.attachments.repo.view(local_id).sync_status == 'not_synced'
            missing = await pair.browser.get('/attachments/' + original.attachment_id)
            assert missing.status_code == 404
            setting = sync.settings()
            sync.set_settings(dto.RemoteSyncSettingsInput(expectedVersion=setting.version, mirrorEnabled=True), 'reenable-inputs')
            await until(lambda: pair.system.worker.attachments.repo.view(local_id).sync_status == 'available', timeout=12)
            await until(lambda: pair.system.repo.get('sync-work')['phase'] == 'synced')
            frames = [f for f in pair.sent if f['type'] == 'sync.message.segment' and
                f['syncGeneration'] == sync.settings().sync_generation and f['payload']['messageId'] == message]
            assert frames and all('sourceCommandId' not in f['payload'] for f in frames)
            assert all('originAttachmentId' not in a for f in frames for a in f['payload']['attachments'])
            assert pair.system.repo.get('link')['view']['state'] == 'paired'
            assert (await pair.browser.get('/attachments/' + original.attachment_id)).status_code == 404
    asyncio.run(scenario())
