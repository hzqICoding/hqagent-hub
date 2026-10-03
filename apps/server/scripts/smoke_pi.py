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
    print('revision 5 negotiation, pi-v1 HTTP and cursor isolation: PASS')
    return [secret,challenge['pairCode']]
