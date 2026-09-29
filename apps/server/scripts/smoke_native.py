"""Revision 3 real-socket portion of the local-only smoke."""
import hashlib
import json
import secrets
import time
from concurrent.futures import ThreadPoolExecutor

from protocol.generated import python as dto
from websockets.sync.client import connect

from server.common import digest,stamp,uid


def native_smoke(client, port, request):
    secret,store,epoch=secrets.token_urlsafe(32),uid(),uid()
    challenge=request('POST','/worker/pairing-requests',dict(deviceName='Native smoke',workerStoreId=store,platform='linux',architecture='x86_64'),
                      'RemotePairingChallenge',{'Cookie':'','Authorization':'Bearer '+secret}).json()['data']
    request('POST','/pairings/'+challenge['pairRequestId']+'/confirm',dict(pairCode=challenge['pairCode']),'RemoteDeviceView')
    worker=challenge['workerId']; seq=0
    def receive(ws):
        value=json.loads(ws.recv(timeout=5));dto.RemoteV3ServerOutboundFrame.model_validate(value);return value
    def send(ws,value):
        dto.RemoteV3WorkerOutboundFrame.model_validate(value);ws.send(json.dumps(value))
    def emit(ws,kind,**fields):
        nonlocal seq
        seq+=1
        send(ws,dict(type=kind,wireRevision=3,eventId=uid(),workerId=worker,workerStoreId=store,workerEpoch=epoch,seq=seq,occurredAt=stamp(time.time()),**fields))
        assert receive(ws)['position']['seq']==seq
    def answer(ws,query,value):
        text=json.dumps(value,separators=(',',':'))
        send(ws,dict(type='query.result.segment',wireRevision=3,queryId=query['queryId'],requestId=query['requestId'],connectionId=query['connectionId'],
                     workerId=worker,workerStoreId=store,workerEpoch=epoch,resultType=query['type'][6:],segmentIndex=0,segmentCount=1,totalUtf8Bytes=len(text.encode()),contentSha256=hashlib.sha256(text.encode()).hexdigest(),text=text))
    with connect(f'ws://127.0.0.1:{port}/ws/v2/worker',additional_headers={'Authorization':'Bearer '+secret,'X-Forwarded-Proto':'https'},proxy=None) as ws, ThreadPoolExecutor(max_workers=1) as pool:
        send(ws,dict(type='worker.hello',wireRevision=3,protocolVersion=dto.PROTOCOL_VERSION,workerId=worker,workerStoreId=store,workerEpoch=epoch,platform='linux',architecture='x86_64',capabilityRevision=1,lastServerAck=None))
        assert receive(ws)['commandDelivery']=='ready'
        emit(ws,'capability.changed',payload=dict(workerId=worker,workerStoreId=store,capabilityRevision=1,observedAt=stamp(time.time()),workspaces=[dict(workspaceId='workspace',name='Synthetic',displayPath='/synthetic',vcs='git',canWrite=True)],scenes=[],remotelyBlockedActions=[],authorizedRoots=[dict(rootId='root',displayName='Projects',version=1)]))
        emit(ws,'native.index.upserted',syncGeneration=1,payload=dict(nativeSessionId='local-native',workspaceId='workspace',agentType='codex',title='Synthetic native',createdAt=stamp(time.time()),updatedAt=stamp(time.time()),indexVersion=1,sourceRevision='a'*64,format=dict(status='readable',readerId='synthetic'),activity=dict(activity='unknown',observedAt=stamp(time.time()),processMatch='unknown',recentlyModified=False)))
        index=request('GET',f'/devices/{worker}/native-sessions',model='RemoteNativeSessionPage').json()['data']['items'][0]
        public=index['nativeSessionId']
        waiting=pool.submit(request,'GET',f'/native-sessions/{public}/messages',None,'NativeMessagePage')
        query=receive(ws)
        marker='EPHEMERAL-SMOKE-NEVER-STORED'
        answer(ws,query,dict(nativeSessionId='local-native',sourceRevision='a'*64,snapshotCursor='synthetic-source-cursor',hasMore=False,items=[dict(messageId='m',role='assistant',text=marker,segmentIndex=0,segmentCount=1,totalUtf8Bytes=len(marker),contentSha256=hashlib.sha256(marker.encode()).hexdigest())]))
        assert waiting.result(timeout=5).json()['data']['nativeSessionId']==public
        waiting=pool.submit(request,'POST',f'/devices/{worker}/directory-listings',dict(rootId='root',rootVersion=1),'DirectoryListingPage')
        query=receive(ws)
        answer(ws,query,dict(rootId='root',rootVersion=1,directoryToken='synthetic-worker-selection',entries=[],hasMore=False))
        assert waiting.result(timeout=5).status_code==200
        issued=request('POST',f'/native-sessions/{public}/imports',dict(terminalClosedConfirmed=True,expectedIndexVersion=1,sourceRevision='a'*64),'RemoteResourceQueuedReceipt')
        command=receive(ws)
        assert command['payload']['confirmation']['requestId']==issued.json()['requestId']
        emit(ws,'command.received',commandId=command['commandId'],commandDigest=digest(command),deliverBy=command['deliverBy'],receivedAt=stamp(time.time()))
        assert receive(ws)['type']=='command.delivery_granted'
        emit(ws,'command.accepted',commandId=command['commandId'],receivedAt=stamp(time.time()),status='accepted')
        emit(ws,'sync.conversation.upserted',syncGeneration=1,payload=dict(conversationId='imported',workspaceId='workspace',title='Imported synthetic',createdAt=stamp(time.time()),updatedAt=stamp(time.time()),archived=False,visibility='both',metadataVersion=1,authority='local',conversationKind='native',agentType='codex',nativeSessionId='local-native'))
        text='Whole imported history'
        emit(ws,'sync.message.segment',syncGeneration=1,payload=dict(messageId='full',conversationId='imported',messageSequence=1,messageRevision=1,role='assistant',createdAt=stamp(time.time()),text=text,segmentIndex=0,segmentCount=1,totalUtf8Bytes=len(text),contentSha256=hashlib.sha256(text.encode()).hexdigest()))
        emit(ws,'command.completed',commandId=command['commandId'],resultStatus='confirmed',resourceRef=dict(workspaceId='workspace',conversationId='imported',nativeSessionId='local-native'),controlResult=dict(outcome='confirmed',executionMayStillBeRunning=False,orphanProcessIds=[],reason='metadata committed',evidence='metadata_committed',observedAt=stamp(time.time())))
        conv=request('GET','/commands/'+command['commandId'],model='RemoteCommandView').json()['data']['resourceRef']['conversationId']
        assert request('GET','/conversations/'+conv+'/snapshot',model='RemoteConversationSnapshot').json()['data']['messages'][0]['text']==text
    print('revision 3 index, ephemeral queries, resource grant and imported history: PASS')
    return [secret,challenge['pairCode'],marker,'synthetic-worker-selection']
