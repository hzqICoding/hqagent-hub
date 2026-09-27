from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from protocol.generated import python as dto

from conftest import FakeWorker
from r15_support import Worker2
from server.app import create_app
from server.common import digest, stamp, uid
from server.service import Service


@pytest.fixture
def env(r15_env):
    return r15_env


def seed_r1_history(env, worker):
    legacy = Service(env.service.repo, env.settings, env.service.security)
    legacy.connections = env.service.connections
    with env.service.repo.transaction() as tx:
        owner = legacy.security.session(tx, env.alice.cookie)['owner']
        conv = legacy.create_conversation(tx, owner, dict(targetWorkerId=worker.worker, workerStoreId=worker.store, title='historical', workspaceId='ws', sceneId='scene', sceneVersion=1))
        receipt = legacy.send_message(tx, owner, conv['conversationId'], dict(clientMessageId=uid(), text='previously admitted R1', sessionMode='new'))
    return conv['conversationId'], receipt


def test_rev1_history_reconciliation_upgrade_fence_and_no_new_rev1_writes(env):
    old = FakeWorker(env, env.alice); old.confirm()
    with old.connect():
        old.catalog()
        create = env.alice.post('/conversations', dict(targetWorkerId=old.worker, workerStoreId=old.store, title='not allowed on rev1', workspaceId='ws', sceneId='scene', sceneVersion=1))
        assert create.json()['error']['code'] == 'REMOTE_REVISION_REQUIRED'
    conv, receipt = seed_r1_history(env, old)
    with env.client.websocket_connect('wss://testserver/ws/v2/worker', headers={'Authorization': 'Bearer ' + old.secret}) as socket:
        socket.send_json(old.hello(wireRevision=2, lastServerAck=dict(workerStoreId=old.store, seq=1)))
        rejected = socket.receive_json(); dto.RemoteV2ServerOutboundFrame.model_validate(rejected)
        assert rejected['error']['code'] == 'REMOTE_REVISION_REQUIRED'
    with old.connect():
        frame = old.receive()
        assert frame['wireRevision'] == 1 and frame['commandId'] == receipt['commandId']
        before_hash = digest(frame)
        old.emit(old.event('command.accepted', commandId=frame['commandId'], conversationId=conv, status='accepted', receivedAt=stamp(env.clock()), resultRef=dict(runId='old-run')))
        old.emit(old.event('command.completed', commandId=frame['commandId'], conversationId=conv, resultStatus='succeeded', resultRef=dict(runId='old-run')))
    with env.client.websocket_connect('wss://testserver/ws/v2/worker', headers={'Authorization': 'Bearer ' + old.secret}) as socket:
        socket.send_json(old.hello(wireRevision=2, lastServerAck=dict(workerStoreId=old.store, seq=old.seq)))
        ack = socket.receive_json(); dto.RemoteV2ServerOutboundFrame.model_validate(ack)
        assert ack['commandDelivery'] == 'ready'
    with env.service.repo.transaction() as tx:
        owner = env.service.security.session(tx, env.alice.cookie)['owner']
        assert digest(tx.get(owner, 'command', frame['commandId'])['_frame']) == before_hash
        assert tx.get(owner, 'device', old.worker)['_upgradeAck'] == old.seq
    with old.connect():
        assert old.ack['error']['code'] == 'REMOTE_PROTOCOL_UNSUPPORTED'


def test_busy_does_not_gate_cancel_and_ids_are_local_on_wire(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv = w.upsert(); w.busy(['local'])
        run_event = w.event('sync.run.state', syncGeneration=1, payload=dict(runId='run-local', conversationId='local', status='running', observedAt=stamp(env.clock())))
        w.emit(run_event)
        public = env.alice.get('/conversations/' + conv + '/runs').json()['data']['items'][0]['runId']
        assert public != 'run-local'
    with w.connect():
        assert not env.alice.get('/conversations/' + conv).json()['data']['busyFresh']
        result = env.alice.post('/runs/' + public + '/commands', dict(action='cancel'))
        assert result.status_code == 202
        frame = w.receive()
        assert frame['payload']['runId'] == 'run-local' and frame['localConversationId'] == 'local'
        w.received(frame); assert w.receive()['type'] == 'command.delivery_granted'
        w.accept(frame, resultRef=dict(runId='run-local'))
        control = dict(outcome='confirmed', executionMayStillBeRunning=False, orphanProcessIds=[], reason='stopped', evidence='adapter_confirmed', observedAt=stamp(env.clock()))
        assert w.emit(w.event('command.completed', commandId=frame['commandId'], conversationId=conv, resultStatus='confirmed', resultRef=dict(runId='run-local'), controlResult=control))['type'] == 'worker.events_ack'
        assert env.alice.get('/commands/' + frame['commandId']).json()['data']['controlResult'] == control


def test_restart_invalidates_freshness_without_retaining_lock(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        conv = w.upsert(); w.busy(['local'])
    old_client = env.client
    with TestClient(create_app(env.settings), base_url=env.settings.origin) as restarted:
        env.client = restarted
        try:
            view = env.alice.get('/conversations/' + conv).json()['data']
            assert view['busy'] is True and view['busyFresh'] is False
            with w.connect():
                assert not env.alice.get('/conversations/' + conv).json()['data']['busyFresh']
                w.busy([])
                view = env.alice.get('/conversations/' + conv).json()['data']
                assert not view['busy'] and view['busyFresh']
        finally:
            env.client = old_client


def test_newer_busy_snapshot_is_not_union_and_old_parts_cannot_overwrite(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        conv = w.upsert(); other = w.upsert('other')
        stale = uid()
        w.busy(['local'], snapshotId=stale, partCount=2)
        w.busy(['other'])
        w.busy([], snapshotId=stale, partCount=2, partIndex=1)
        first = env.alice.get('/conversations/' + conv).json()['data']
        second = env.alice.get('/conversations/' + other).json()['data']
        assert first['busyFresh'] and not first['busy']
        assert second['busyFresh'] and second['busy']


def test_backfill_counts_high_water_completion_and_incomplete_message(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        conv = w.upsert()
        marker = w.event('sync.backfill.progress', syncGeneration=1, backfillId='history', batchIndex=0, batchEventCount=1, snapshotHighWater=500, complete=False)
        assert w.emit(marker)['type'] == 'worker.events_ack'
        done = w.event('sync.backfill.progress', syncGeneration=1, backfillId='history', batchIndex=1, batchEventCount=0, snapshotHighWater=500, complete=True)
        assert w.emit(done)['type'] == 'worker.events_ack'
        with env.service.repo.transaction() as tx:
            owner = env.service.security.session(tx, env.alice.cookie)['owner']
            state = env.service.replica.state(tx, owner, w.worker, w.store)
            assert state['complete'] and state['backfill']['high'] == 500
        partial = w.message('local', 'a', message='partial', parts=2, total=2, content_hash='0' * 64)
        w.emit(partial)
        invalid = w.event('sync.backfill.progress', syncGeneration=1, backfillId='new-history', batchIndex=0, batchEventCount=1, snapshotHighWater=700, complete=True)
        assert w.emit(invalid)['error']['code'] == 'REMOTE_SYNC_CONFLICT'


def test_revision_two_permission_is_not_implicit_in_ack(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv = w.upsert(); w.busy()
        receipt = w.send(conv); frame = w.receive()
        # A Worker that skips the provisional/explicit grant step is rejected.
        result = w.accept(frame, resultRef=dict(runId='unauthorized-run'))
        assert result['error']['code'] == 'REMOTE_EVENT_CONFLICT'
        view = env.alice.get('/commands/' + receipt['commandId']).json()['data']
        assert view['status'] == 'queued'


def test_busy_snapshot_multiple_parts_more_than_one_hundred_ids(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        conv = w.upsert('last')
        snap = uid()
        w.busy([str(i) for i in range(100)], snapshotId=snap, partCount=2)
        assert not env.alice.get('/conversations/' + conv).json()['data']['busyFresh']
        w.busy(['last'], snapshotId=snap, partIndex=1, partCount=2)
        value = env.alice.get('/conversations/' + conv).json()['data']
        assert value['busy'] and value['busyFresh']


def test_backfill_byte_budget_rejects_false_complete_marker(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.upsert()
        for sequence in range(1, 68):
            assert w.emit(w.message('local', 'x' * 16000, message=str(sequence), sequence=sequence))['type'] == 'worker.events_ack'
        marker = w.event('sync.backfill.progress', syncGeneration=1, backfillId='oversized', batchIndex=0, batchEventCount=68, snapshotHighWater=100, complete=True)
        assert w.emit(marker)['error']['code'] == 'REMOTE_SYNC_CONFLICT'
        with env.service.repo.transaction() as tx:
            owner = env.service.security.session(tx, env.alice.cookie)['owner']
            assert not env.service.replica.state(tx, owner, w.worker, w.store)['complete']


def test_complete_backfill_retires_server_only_r1_shadow(env):
    old = FakeWorker(env, env.alice); old.confirm()
    with old.connect():
        old.catalog()
    legacy = Service(env.service.repo, env.settings, env.service.security)
    with env.service.repo.transaction() as tx:
        owner = legacy.security.session(tx, env.alice.cookie)['owner']
        shadow = legacy.create_conversation(tx, owner, dict(targetWorkerId=old.worker, workerStoreId=old.store, title='never created on computer', workspaceId='ws', sceneId='scene', sceneVersion=1))
    with env.client.websocket_connect('wss://testserver/ws/v2/worker', headers={'Authorization': 'Bearer ' + old.secret}) as socket:
        socket.send_json(old.hello(wireRevision=2, lastServerAck=dict(workerStoreId=old.store, seq=1)))
        assert socket.receive_json()['commandDelivery'] == 'ready'
        assert env.alice.get('/conversations/' + shadow['conversationId']).status_code == 200
        event = dict(type='sync.backfill.progress', wireRevision=2, eventId=uid(), workerId=old.worker, workerStoreId=old.store, workerEpoch=old.epoch, seq=2, occurredAt=stamp(env.clock()), syncGeneration=1, backfillId='full', batchIndex=0, batchEventCount=0, snapshotHighWater=0, complete=True)
        dto.RemoteV2WorkerOutboundFrame.model_validate(event)
        socket.send_json(event)
        assert socket.receive_json()['position']['seq'] == 2
        assert env.alice.get('/conversations/' + shadow['conversationId']).status_code == 404
