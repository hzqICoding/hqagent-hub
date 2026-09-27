import hashlib
import json

import pytest
from protocol.generated import python as dto

from r15_support import Worker2
from server.common import digest, stamp, uid


@pytest.fixture
def env(r15_env):
    return r15_env


def database_text(env):
    with env.service.repo.transaction() as tx:
        tables = [r[0] for r in tx.db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return '\n'.join(str(value) for table in tables for row in tx.db.execute('SELECT * FROM "' + table + '"') for value in row)


def test_out_of_order_segments_duplicate_and_revision_are_atomic(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        conv = w.upsert(); w.busy()
        text = ('汉字\x00\r\n😀' * 7000)
        parts = [text[i:i+16000] for i in range(0, len(text), 16000)]
        message = 'same-local-message'; hash_ = hashlib.sha256(text.encode()).hexdigest()
        for index in list(range(1, len(parts))) + [0]:
            event = w.message('local', parts[index], message=message, index=index, parts=len(parts), total=len(text.encode()), content_hash=hash_)
            assert w.emit(event)['type'] == 'worker.events_ack'
            assert w.emit(event)['type'] == 'worker.events_ack'
            current = env.alice.get('/conversations/' + conv + '/messages').json()['data']['items']
            if index:
                assert current == []
        assert current[0]['text'] == text and current[0]['messageRevision'] == 1
        new = 'replacement content'
        assert w.emit(w.message('local', new[:8], message=message, revision=2, index=0, parts=2, total=len(new), content_hash=hashlib.sha256(new.encode()).hexdigest()))['type'] == 'worker.events_ack'
        assert env.alice.get('/conversations/' + conv + '/messages').json()['data']['items'][0]['text'] == text
        assert w.emit(w.message('local', new[8:], message=message, revision=2, index=1, parts=2, total=len(new), content_hash=hashlib.sha256(new.encode()).hexdigest()))['type'] == 'worker.events_ack'
        assert env.alice.get('/conversations/' + conv + '/messages').json()['data']['items'][0]['text'] == new
        assert w.emit(w.message('local', 'old', message=message, revision=1))['type'] == 'worker.events_ack'
        assert env.alice.get('/conversations/' + conv + '/messages').json()['data']['items'][0]['messageRevision'] == 2


@pytest.mark.parametrize('fault', ['metadata', 'content', 'hash', 'quota'])
def test_segment_conflicts_and_quota_never_publish_partial(env, fault):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        conv = w.upsert()
        if fault == 'quota':
            env.settings.sync_message_bytes = 2
            event = w.message('local', 'too big')
        elif fault == 'hash':
            event = w.message('local', 'wrong hash', content_hash='0' * 64)
        else:
            first = w.message('local', 'a', message='m', parts=2, total=2, content_hash=hashlib.sha256(b'ab').hexdigest())
            w.emit(first)
            payload = dict(first['payload'], **({'role': 'user'} if fault == 'metadata' else {'text': 'z'}))
            event = w.event('sync.message.segment', syncGeneration=1, payload=payload)
        result = w.emit(event)
        assert result['error']['code'] in {'REMOTE_SYNC_CONFLICT', 'REMOTE_SYNC_RESOURCE_LIMIT'}
        assert env.alice.get('/conversations/' + conv + '/messages').json()['data']['items'] == []


@pytest.mark.parametrize('operation', ['delete', 'reset', 'revoke'])
def test_true_deletion_removes_content_from_all_logical_tables(env, operation):
    marker = 'R15-PRIVATE-BODY-UNIQUE'
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv = w.upsert(title=marker); w.busy()
        complete = w.message('local', marker, message='complete')
        assert w.emit(complete)['type'] == 'worker.events_ack'
        assert w.emit(w.message('local', marker, message='incomplete', sequence=2, index=1, parts=2, total=len(marker.encode()) * 2, content_hash=hashlib.sha256((marker * 2).encode()).hexdigest()))['type'] == 'worker.events_ack'
        receipt = w.send(conv, text=marker)
        command = w.receive()
        assert marker in database_text(env)
        if operation == 'revoke':
            assert env.alice.post('/devices/' + w.worker + '/revocations').status_code == 200
        elif operation == 'reset':
            assert w.emit(w.event('sync.reset', syncGeneration=2))['type'] == 'worker.events_ack'
        else:
            assert w.emit(w.event('sync.conversation.deleted', syncGeneration=1, conversationId='local', deletedAt=stamp(env.clock())))['type'] == 'worker.events_ack'
        assert marker not in database_text(env)
        assert env.alice.get('/conversations/' + conv).status_code == 404
        assert env.alice.get('/commands/' + command['commandId']).status_code == 404
        if operation != 'revoke':
            assert w.emit(complete)['type'] == 'worker.events_ack'
            assert marker not in database_text(env)


def test_reset_before_gap_then_redaction_preserves_original_hash_and_ack(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        conv = w.upsert()
        original = w.message('local', 'never upload after deletion', message='missing')
        deletion = w.event('sync.reset', syncGeneration=2)
        ack = w.emit(deletion)
        assert ack['position']['seq'] == 1
        assert env.alice.get('/conversations/' + conv).status_code == 404
        proof = dict(type='sync.content.redaction', wireRevision=2, redactionId=uid(), workerId=w.worker, workerStoreId=w.store, workerEpoch=w.epoch,
                     syncGeneration=2, deletionEventId=deletion['eventId'], deletionSeq=deletion['seq'],
                     slots=[dict(seq=original['seq'], eventId=original['eventId'], eventSha256=digest(original), originalType=original['type'])])
        dto.RemoteV2WorkerOutboundFrame.model_validate(proof)
        assert w.emit(proof)['position']['seq'] == deletion['seq']
        assert w.emit(proof)['position']['seq'] == deletion['seq']
        assert w.emit(original)['position']['seq'] == deletion['seq']
        assert original['payload']['text'] not in database_text(env)
        assert w.upsert(generation=3) == conv
        assert env.alice.get('/conversations/' + conv).status_code == 200


def test_redaction_cannot_swallow_noncontent_or_foreign_conversation(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.upsert('one'); w.upsert('two')
        other = w.message('two', 'other must remain', message='other')
        w.emit(other)
        deletion = w.event('sync.conversation.deleted', syncGeneration=1, conversationId='one', deletedAt=stamp(env.clock()))
        w.emit(deletion)
        proof = dict(type='sync.content.redaction', wireRevision=2, redactionId=uid(), workerId=w.worker, workerStoreId=w.store, workerEpoch=w.epoch,
                     syncGeneration=1, deletionEventId=deletion['eventId'], deletionSeq=deletion['seq'], conversationId='one',
                     slots=[dict(seq=other['seq'], eventId=other['eventId'], eventSha256=digest(other), originalType=other['type'])])
        assert w.emit(proof)['error']['code'] == 'REMOTE_SYNC_CONFLICT'
        assert 'other must remain' in database_text(env)


def test_pc_only_in_every_browser_resource_and_event(env):
    w = Worker2(env, env.alice); w.confirm()
    with w.connect():
        w.catalog(); conv = w.upsert(); w.busy()
        w.emit(w.event('sync.run.state', syncGeneration=1, payload=dict(runId='local-run', conversationId='local', status='waiting_approval', observedAt=stamp(env.clock()))))
        w.emit(w.event('approval.state_changed', conversationId='local', payload=dict(approvalId='local-approval', resultRef=dict(runId='local-run'), action='git_push', targetSummary='private target', riskLevel='high', status='pending', requestedAt=stamp(env.clock()), expiresAt=stamp(env.clock() + 300), remoteApprovalAllowed=False, workerPolicyRevision=1)))
        message = w.message('local', 'private message'); w.emit(message)
        snap = env.alice.get('/conversations/' + conv + '/snapshot').json()['data']
        run = snap['runs'][0]['runId']; approval = snap['approvals'][0]['approvalId']
        command = w.send(conv); w.receive()
        before = env.alice.get('/events').json()['data']['nextServerCursor']
        w.upsert(version=2, visibility='pc_only', title='private title')
        for path in ['/conversations/' + conv, '/conversations/' + conv + '/snapshot', '/conversations/' + conv + '/messages', '/conversations/' + conv + '/runs', '/conversations/' + conv + '/commands', '/runs/' + run, '/approvals/' + approval, '/commands/' + command['commandId']]:
            assert env.alice.get(path).json()['error']['code'] == 'NOT_FOUND'
        assert env.alice.post('/approvals/' + approval + '/decisions', dict(decision='reject')).status_code == 404
        assert env.alice.get('/conversations?workerId=' + w.worker).json()['data']['items'] == []
        events = env.alice.get('/events?after=' + before).json()['data']['items']
        assert [e['type'] for e in events] == ['conversation.deleted']
        assert all('private' not in json.dumps(e) for e in events)
        assert 'private message' in database_text(env)  # visibility never suppresses sync/storage
        w.upsert(version=3, visibility='mobile_only')
        assert env.alice.get('/conversations/' + conv).status_code == 200


def test_multi_device_ids_and_fixed_message_pagination(env):
    a, b = Worker2(env, env.alice), Worker2(env, env.alice)
    a.confirm(); b.confirm()
    with a.connect():
        ca = a.upsert('same-local-id')
        for sequence in (1, 2, 3):
            a.emit(a.message('same-local-id', 'a-' + str(sequence), message='m' + str(sequence), sequence=sequence))
        page = env.alice.get('/conversations/' + ca + '/messages?limit=2').json()['data']
        assert [m['messageSequence'] for m in page['items']] == [3, 2]
        a.emit(a.message('same-local-id', 'a-4', message='m4', sequence=4))
        older = env.alice.get('/conversations/' + ca + '/messages?before=' + page['before']).json()['data']
        assert [m['messageSequence'] for m in older['items']] == [1]
        assert older['snapshotCursor'] == page['snapshotCursor'] and not older['hasMore']
        assert env.alice.get('/conversations/' + ca + '/messages').json()['data']['items'][0]['messageSequence'] == 4
    with b.connect():
        cb = b.upsert('same-local-id')
        b.emit(b.message('same-local-id', 'b-only', message='m1', sequence=1))
        assert ca != cb
        assert env.alice.get('/conversations/' + cb + '/messages').json()['data']['items'][0]['messageId'] != older['items'][0]['messageId']
        assert env.alice.get('/conversations/' + cb + '/messages?before=' + page['before']).status_code == 400
        assert env.alice.get('/conversations?workerId=' + a.worker + '&workspaceId=ws').json()['data']['items'][0]['conversationId'] == ca
        assert env.alice.get('/conversations?workerId=' + b.worker + '&workspaceId=missing').json()['data']['items'] == []
        assert env.bob.get('/conversations?workerId=' + b.worker).status_code == 404
