"""Synthetic revision 5 smoke; no PI installation, credentials or model calls."""
import json
import secrets
import time

from protocol.generated import python as dto
from websockets.sync.client import connect

from server.common import stamp, uid


def pi_smoke(client, port, request):
    secret, store, epoch = secrets.token_urlsafe(32), uid(), uid()
    challenge = request('POST', '/worker/pairing-requests',
        dict(deviceName='PI synthetic Worker',workerStoreId=store,platform='linux',architecture='x86_64'),
        'RemotePairingChallenge', {'Cookie':'','Authorization':'Bearer '+secret}).json()['data']
    request('POST','/pairings/'+challenge['pairRequestId']+'/confirm',dict(pairCode=challenge['pairCode']),'RemoteDeviceView')
    worker = challenge['workerId']
    feature = {'X-HQ-Client-Features':'pi-v1'}
    before = request('GET','/events',model='RemoteBrowserEventPage').json()['data']['nextServerCursor']
    def receive(ws):
        value=json.loads(ws.recv(timeout=5))
        dto.RemoteV5ServerOutboundFrame.model_validate(value)
        return value
    def send(ws,value):
        dto.RemoteV5WorkerOutboundFrame.model_validate(value)
        ws.send(json.dumps(value))
    with connect(f'ws://127.0.0.1:{port}/ws/v2/worker',additional_headers={'Authorization':'Bearer '+secret,'X-Forwarded-Proto':'https'},proxy=None) as ws:
        send(ws,dict(type='worker.hello',wireRevision=5,protocolVersion=dto.PROTOCOL_VERSION,workerId=worker,workerStoreId=store,workerEpoch=epoch,platform='linux',architecture='x86_64',capabilityRevision=1,lastServerAck=None))
        assert receive(ws)['wireRevision']==5
        common=dict(wireRevision=5,workerId=worker,workerStoreId=store,workerEpoch=epoch,occurredAt=stamp(time.time()))
        send(ws,dict(common,type='capability.changed',eventId=uid(),seq=1,payload=dict(workerId=worker,workerStoreId=store,capabilityRevision=1,observedAt=stamp(time.time()),workspaces=[dict(workspaceId='ws',name='Synthetic',displayPath='Synthetic project',vcs='none',canWrite=False)],scenes=[],remotelyBlockedActions=[],authorizedRoots=[],runtimes=[dict(agentId='runtime-opaque',agentType='pi',nativeSessionsSupported=False,guard=dict(status='unverified',isolation='unknown',checkedAt=stamp(time.time()),reasons=['guard_not_loaded']))])))
        assert receive(ws)['position']['seq']==1
        send(ws,dict(common,type='native.index.upserted',eventId=uid(),seq=2,syncGeneration=1,payload=dict(nativeSessionId='local-native',workspaceId='ws',agentType='pi',title='Synthetic PI index',createdAt=stamp(time.time()),updatedAt=stamp(time.time()),indexVersion=1,sourceRevision='a'*64,format=dict(status='unsupported',unsupportedReason='reader_not_implemented',reason='Synthetic reader not implemented'),activity=dict(activity='unknown',observedAt=stamp(time.time()),processMatch='unknown',recentlyModified=False))))
        assert receive(ws)['position']['seq']==2
        old=request('GET',f'/devices/{worker}/native-sessions',model='RemoteNativeSessionPage').json()['data']
        assert old['items']==[]
        new=request('GET',f'/devices/{worker}/native-sessions',model='RemoteNativeSessionPage',extra=feature).json()['data']
        assert new['items'][0]['agentType']=='pi'
        identifier=new['items'][0]['nativeSessionId']
        assert client.get('/api/v2/native-sessions/'+identifier).status_code==404
        assert request('GET','/native-sessions/'+identifier,model='RemoteNativeSessionView',extra=feature).status_code==200
        assert client.get('/api/v2/events',params={'after':before},headers=feature).json()['error']['code']=='REMOTE_CURSOR_INVALID'
        seq = 2
        def emit(kind, **fields):
            nonlocal seq
            seq += 1
            send(ws, dict(common, type=kind, eventId=uid(), seq=seq, **fields))
            assert receive(ws)['position']['seq'] == seq
        for local, agent in [('normal-conv','codex'),('pi-conv','pi')]:
            emit('sync.conversation.upserted', syncGeneration=1, payload=dict(
                conversationId=local, workspaceId='ws', title='Synthetic '+agent,
                createdAt=stamp(time.time()), updatedAt=stamp(time.time()), archived=False,
                visibility='both', metadataVersion=1, authority='local', conversationKind='native',
                agentType=agent, nativeSessionId='session-'+local))
            emit('sync.run.state', syncGeneration=1, payload=dict(
                runId='run-'+local, conversationId=local, status='waiting_approval', observedAt=stamp(time.time())))
        legacy_cursor = request('GET','/events',model='RemoteBrowserEventPage').json()['data']['nextServerCursor']
        pi_cursor = request('GET','/events',model='RemoteBrowserEventPage',extra=feature).json()['data']['nextServerCursor']
        for local in ('normal-conv','pi-conv'):
            payload = dict(approvalId='approval-'+local, resultRef=dict(runId='run-'+local),
                           action='network', targetSummary='Safe synthetic action', riskLevel='low',
                           status='pending', requestedAt=stamp(time.time()), expiresAt=stamp(time.time()+120),
                           remoteApprovalAllowed=local=='normal-conv', workerPolicyRevision=1)
            if local=='pi-conv':
                payload['denialCode']='PI_TOOL_CALL_BLOCKED'
            emit('approval.state_changed', conversationId=local, payload=payload)
        old_events = request('GET','/events?after='+legacy_cursor,model='RemoteBrowserEventPage').json()['data']['items']
        new_events = request('GET','/events?after='+pi_cursor,model='RemoteBrowserEventPage',extra=feature).json()['data']['items']
        assert len(old_events)==1 and len(new_events)==2
        dto.RemoteBrowserLegacyApprovalEvent.model_validate(old_events[0])
        dto.RemoteBrowserPiApprovalEvent.model_validate(new_events[1])
        assert old_events[0]['payload']['wireRevision']==2 and new_events[1]['payload']['wireRevision']==5
    print('revision 5 negotiation, pi-v1 HTTP and cursor isolation: PASS')
    print('revision 5 approvals: legacy realtime projection and pi-v1 isolation: PASS')
    return [secret,challenge['pairCode']]
