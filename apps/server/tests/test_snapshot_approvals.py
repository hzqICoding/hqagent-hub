import pytest
from protocol.generated.python import RemoteConversationSnapshot

from server.common import stamp, uid, validated
from test_commands_events import admit_run
from test_controls_storage import approval_event


def snapshot(env, paired):
    result = env.alice.get('/conversations/' + paired.conv + '/snapshot')
    assert result.status_code == 200
    data = result.json()['data']
    RemoteConversationSnapshot.model_validate(data)
    return data


def test_late_snapshot_sees_high_risk_pending_and_resumes_after_cursor(env, paired):
    with paired.connect():
        admit_run(paired)
        approval = approval_event(paired, 'git_push', allowed=False)
        data = snapshot(env, paired)
        assert data['approvals'] == [approval]
        assert env.bob.get('/conversations/' + paired.conv + '/snapshot').status_code == 404
        other_conv = paired.conversation()
        assert env.alice.get('/conversations/' + other_conv + '/snapshot').json()['data']['approvals'] == []
        terminal = dict(approval, status='rejected')
        assert paired.emit(paired.event('approval.state_changed', conversationId=paired.conv, payload=terminal))['type'] == 'worker.events_ack'
        assert snapshot(env, paired)['approvals'] == []
        events = env.alice.get('/events?after=' + data['serverCursor']).json()['data']['items']
        assert any(e['type'] == 'worker.event' and e['payload']['type'] == 'approval.state_changed' and e['payload']['payload'] == terminal for e in events)


@pytest.mark.parametrize('decision,status', [('approve', 'approved'), ('reject', 'rejected')])
def test_snapshot_removes_confirmed_consumption_not_http_202(env, paired, decision, status):
    with paired.connect():
        admit_run(paired)
        approval = approval_event(paired, 'network')
        result = env.alice.post('/approvals/' + approval['approvalId'] + '/decisions', dict(decision=decision))
        assert result.status_code == 202
        assert snapshot(env, paired)['approvals'] == [approval]
        command = paired.receive()
        accepted = paired.event('command.accepted', conversationId=paired.conv, commandId=command['commandId'], receivedAt=stamp(env.clock()), status='accepted')
        assert paired.emit(accepted)['type'] == 'worker.events_ack'
        consumed = paired.event('command.completed', conversationId=paired.conv, commandId=command['commandId'], resultStatus='approval_consumed', resultRef=approval['resultRef'])
        assert paired.emit(consumed)['type'] == 'worker.events_ack'
        # The definitive consumption result is enough even before the terminal projection arrives.
        assert snapshot(env, paired)['approvals'] == []
        assert paired.emit(paired.event('approval.state_changed', conversationId=paired.conv, payload=dict(approval, status=status)))['type'] == 'worker.events_ack'
        assert snapshot(env, paired)['approvals'] == []


@pytest.mark.parametrize('status', ['approved', 'rejected', 'expired'])
def test_snapshot_excludes_worker_terminal_approval_projection(env, paired, status):
    with paired.connect():
        admit_run(paired)
        approval = approval_event(paired)
        assert paired.emit(paired.event('approval.state_changed', conversationId=paired.conv, payload=dict(approval, status=status)))['type'] == 'worker.events_ack'
        assert snapshot(env, paired)['approvals'] == []


def test_snapshot_expiry_boundary_without_new_worker_event(env, paired):
    with paired.connect():
        admit_run(paired)
        approval = approval_event(paired)
    env.clock.advance(119)
    assert snapshot(env, paired)['approvals'] == [approval]
    env.clock.advance(1)
    data = snapshot(env, paired)
    assert data['observedAt'] == approval['expiresAt']
    assert data['approvals'] == []


@pytest.mark.parametrize('count,has_more', [(100, False), (101, True)])
def test_snapshot_filters_before_bounding_and_preserves_owner_scope(env, paired, count, has_more):
    with env.service.repo.transaction() as tx:
        owner = env.service.security.session(tx, env.alice.cookie)['owner']
        other_owner = env.service.security.session(tx, env.bob.cookie)['owner']
        def save(approval_owner, status, expires):
            value = validated('RemoteApprovalView', dict(approvalId=uid(), resultRef=dict(runId='run'), action='git_push', targetSummary='pending action', riskLevel='high', status=status,
                              requestedAt=stamp(env.clock() - 100), expiresAt=stamp(expires), remoteApprovalAllowed=False, workerPolicyRevision=1))
            env.service.save(tx, approval_owner, 'approval', value['approvalId'], dict(value, _conversation=paired.conv, _worker=paired.worker, _store=paired.store))
            return value
        for _ in range(110):
            save(owner, 'approved', env.clock() + 100)
            save(owner, 'pending', env.clock())
            save(other_owner, 'pending', env.clock() + 100)
        expected = [save(owner, 'pending', env.clock() + 100) for _ in range(count)]
    data = snapshot(env, paired)
    assert data['approvals'] == expected[:100]
    assert data['hasMore'] is has_more


def test_snapshot_has_more_is_or_of_existing_collections(env, paired):
    with env.service.repo.transaction() as tx:
        owner = env.service.security.session(tx, env.alice.cookie)['owner']
        for i in range(101):
            value = dict(messageId=str(i), conversationId=paired.conv, role='user', text='bounded history', createdAt=stamp(env.clock()))
            env.service.save(tx, owner, 'message', str(i), dict(value, _worker=paired.worker, _store=paired.store))
    data = snapshot(env, paired)
    assert data['approvals'] == [] and len(data['messages']) == 100 and data['hasMore']
