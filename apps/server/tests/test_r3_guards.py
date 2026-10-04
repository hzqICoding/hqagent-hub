from concurrent.futures import ThreadPoolExecutor

import pytest
from protocol.generated import python as dto

from conftest import FakeWorker
from r15_support import Worker2
from r3_support import Worker3,native_page,directory_page
from server import wire
from server.common import Fault,digest,stamp,uid
from test_r3_native import env,import_body,path
from test_r15_replica import database_text


@pytest.mark.parametrize('old,new',[(2,3),(3,2)])
def test_bidirectional_upgrade_fence_blocks_pending_and_requires_ack(env,old,new):
    w=Worker3(env,env.alice);w.confirm()
    with w.connect(w.hello(wireRevision=old)):
        catalog=dict(workerId=w.worker,workerStoreId=w.store,capabilityRevision=1,observedAt=stamp(env.clock()),workspaces=[],scenes=[],remotelyBlockedActions=[])
        if old==3:catalog['authorizedRoots']=[]
        event=w.event('capability.changed',payload=catalog);event['wireRevision']=old
        assert w.emit(event)['type']=='worker.events_ack'
        with env.service.repo.transaction() as tx:
            # The immutable old command need not be sent for the upgrade fence.
            tx.put(env.owner,'command','unresolved',dict(_frame=dict(wireRevision=old),status='accepted'),worker=w.worker,store=w.store)
    hello=w.hello(wireRevision=new,lastServerAck=dict(workerStoreId=w.store,seq=w.seq))
    with w.connect(hello):
        assert w.ack['type']=='worker.hello_rejected' and w.ack['error']['code']=='REMOTE_REVISION_REQUIRED'
    with env.service.repo.transaction() as tx:
        tx.remove_record(env.owner,'command','unresolved')
        device=tx.get(env.owner,'device',w.worker)
        assert device['_upgradeTarget']==new and device['_wireRevision']==old
    with w.connect(w.hello(wireRevision=old,lastServerAck=dict(workerStoreId=w.store,seq=w.seq))):
        assert w.ack['type']=='worker.hello_ack'
        with env.service.repo.transaction() as tx:
            with pytest.raises(Fault,match='REMOTE_REVISION_REQUIRED'):
                env.service.ready(tx,env.owner,w.worker,w.store)
    with w.connect(hello):
        assert w.ack['type']=='worker.hello_ack' and w.ack['wireRevision']==new
        with env.service.repo.transaction() as tx:
            device=tx.get(env.owner,'device',w.worker)
            assert device['_upgradeWorkerAck']==device['_upgradeAck']==w.seq
            assert device['_wireRevision']==new and '_upgradeTarget' not in device


def test_upgrade_blocks_unapplied_old_event_and_wire_errors_stay_frozen(env):
    w=Worker3(env,env.alice);w.confirm()
    with w.connect(w.hello(wireRevision=2)):
        # Pending legacy reliable row is created through the repository, not decoded as revision3.
        with env.service.repo.transaction() as tx:
            tx.sync_log_put(env.owner,dict(type='events.omitted',wireRevision=2,eventId=uid(),workerId=w.worker,workerStoreId=w.store,workerEpoch=w.epoch,seq=2,firstSeq=2,occurredAt=stamp(env.clock()),reason='progress_coalesced'))
    with w.connect(w.hello(lastServerAck=dict(workerStoreId=w.store,seq=0))):
        assert w.ack['error']['code']=='REMOTE_REVISION_REQUIRED'
    for rev in (1,2):
        frame=wire.encode(dict(type='worker.hello_rejected',error=Fault('REMOTE_QUERY_TIMEOUT').view()),rev)
        assert frame['error']['code']=='INTERNAL' and frame['supportedWireRevisions']==[1,2,3,4,5]
    assert wire.encode(dict(type='worker.hello_rejected',error=Fault('REMOTE_QUERY_TIMEOUT').view()),3)['error']['code']=='REMOTE_QUERY_TIMEOUT'


@pytest.mark.parametrize('status,delivery,allowed',[
    ('accepted','acknowledged',True), ('accepted','awaiting_receipt',False), ('queued','acknowledged',False)])
def test_upgrade_preserves_acknowledged_unknown_control_evidence(env,status,delivery,allowed):
    w=Worker3(env,env.alice); w.confirm()
    with w.connect(w.hello(wireRevision=2)):
        assert w.ack['type']=='worker.hello_ack'
    evidence=dict(outcome='unconfirmed',executionMayStillBeRunning=True,orphanProcessIds=[424242],
        reason='synthetic recovery evidence',evidence='recovery_flag',observedAt=stamp(env.clock()))
    with env.service.repo.transaction() as tx:
        tx.put(env.owner,'command','historical-control',dict(_frame=dict(wireRevision=2),status=status,
            deliveryState=delivery,controlResult=evidence),worker=w.worker,store=w.store)
    with w.connect(w.hello(lastServerAck=dict(workerStoreId=w.store,seq=0))):
        assert w.ack['type']==('worker.hello_ack' if allowed else 'worker.hello_rejected')
        if not allowed:
            assert w.ack['error']['code']=='REMOTE_REVISION_REQUIRED'
    with env.service.repo.transaction() as tx:
        original=tx.get(env.owner,'command','historical-control')
        assert original['status']==status and original['controlResult']==evidence


def test_native_delete_redaction_gap_and_late_index_do_not_resurrect(env):
    w=Worker3(env,env.alice);w.confirm()
    with w.connect():
        w.catalog(); index,initial=w.index(title='delete-private-index-title')
        missing=w.event('native.index.upserted',syncGeneration=1,payload=dict(initial['payload'],indexVersion=2,title='never-persist-late-title'))
        deletion=w.event('native.index.deleted',syncGeneration=1,nativeSessionId='native',workspaceId='ws',deletedAt=stamp(env.clock()),reason='source_removed')
        assert w.emit(deletion)['position']['seq']==2
        assert 'delete-private-index-title' not in database_text(env)
        proof=dict(type='sync.content.redaction',wireRevision=3,redactionId=uid(),workerId=w.worker,workerStoreId=w.store,workerEpoch=w.epoch,syncGeneration=1,
                   deletionEventId=deletion['eventId'],deletionSeq=deletion['seq'],nativeSessionId='native',slots=[dict(seq=missing['seq'],eventId=missing['eventId'],eventSha256=digest(missing),originalType=missing['type'])])
        assert w.emit(proof)['position']['seq']==deletion['seq']
        assert w.emit(missing)['position']['seq']==deletion['seq']
        assert 'never-persist-late-title' not in database_text(env)
        assert env.alice.get('/native-sessions/'+index['nativeSessionId']).status_code==404


def test_workspace_removal_and_root_removal_invalidate_waiting_queries(env):
    w=Worker3(env,env.alice);w.confirm()
    with w.connect(), ThreadPoolExecutor(max_workers=2) as pool:
        w.catalog(); index,_=w.index(title='removed-workspace-marker')
        read=pool.submit(env.alice.get,'/native-sessions/'+index['nativeSessionId']+'/messages')
        native_query=w.receive()
        listing=pool.submit(env.alice.post,path(w)+'/directory-listings',dict(rootId='root',rootVersion=1))
        directory_query=w.receive()
        w.catalog(capabilityRevision=2,workspaces=[],authorizedRoots=[])
        assert read.result(timeout=3).status_code==404
        assert listing.result(timeout=3).json()['error']['code']=='REMOTE_ROOT_NOT_AUTHORIZED'
        w.answer(native_query,native_page());w.answer(directory_query,directory_page())
        assert env.alice.get('/native-sessions/'+index['nativeSessionId']).status_code==404
        assert 'removed-workspace-marker' not in database_text(env)
        assert not env.service.queries.pending


@pytest.mark.parametrize('grant_first',[False,True])
def test_resource_deadline_competes_with_received_and_not_import_completion(env,grant_first):
    w=Worker3(env,env.alice);w.confirm()
    with w.connect():
        w.catalog();index,_=w.index()
        queued=env.alice.post('/native-sessions/'+index['nativeSessionId']+'/imports',import_body())
        assert queued.status_code==202
        frame=w.receive()
        if grant_first:
            w.received(frame);assert w.receive()['type']=='command.delivery_granted'
        env.clock.advance(30)
        if not grant_first:w.received(frame)
        value=env.alice.get('/commands/'+frame['commandId']).json()['data']
        if grant_first:
            assert value['deliveryState']=='granted' and value['status']=='queued'
            assert w.accepted(frame)['type']=='worker.events_ack'
        else:
            assert value['status']=='failed' and value['error']['code']=='REMOTE_DELIVERY_EXPIRED'
            with env.service.repo.transaction() as tx:
                assert tx.get(env.owner,'outbox','grant:'+frame['commandId']) is None


def test_root_removed_before_grant_denies_registration(env):
    w=Worker3(env,env.alice);w.confirm()
    with w.connect():
        w.catalog()
        response=env.alice.post(path(w)+'/workspaces',dict(rootId='root',rootVersion=1,directoryToken='worker-signed-token-value'))
        assert response.status_code==202
        frame=w.receive();w.catalog(capabilityRevision=2,authorizedRoots=[])
        w.received(frame)
        assert env.alice.get('/commands/'+frame['commandId']).json()['data']['error']['code']=='REMOTE_ROOT_NOT_AUTHORIZED'


@pytest.mark.parametrize('change,code',[(dict(terminalClosedConfirmed=False),'VALIDATION_FAILED'),(dict(expectedIndexVersion=2),'NATIVE_SESSION_CHANGED'),(dict(sourceRevision='b'*64),'NATIVE_SESSION_CHANGED')])
def test_import_requires_exact_explicit_confirmation(env,change,code):
    w=Worker3(env,env.alice);w.confirm()
    with w.connect():
        w.catalog();index,_=w.index()
        response=env.alice.post('/native-sessions/'+index['nativeSessionId']+'/imports',import_body()|change)
        assert response.json()['error']['code']==code


def test_query_per_device_limit_and_pat_never_enters_r3(env):
    from test_devices_tokens import issue,pat
    w=Worker3(env,env.alice);w.confirm()
    with w.connect(), ThreadPoolExecutor(max_workers=4) as pool:
        w.catalog();index,_=w.index()
        p='/native-sessions/'+index['nativeSessionId']+'/messages'
        futures=[];queries=[]
        for _ in range(4):
            futures.append(pool.submit(env.alice.get,p));queries.append(w.receive())
        result=env.alice.get(p)
        assert result.status_code==429 and 'Retry-After' in result.headers
        for q in queries:w.answer(q,native_page())
        assert all(f.result(timeout=3).status_code==200 for f in futures)
        token=issue(env)['secret']
        for method,route,body in [('GET',path(w)+'/native-sessions',None),('GET',p,None),('GET',p.rsplit('/',1)[0],None),
                                  ('POST',p.rsplit('/',1)[0]+'/imports',import_body()),('POST',path(w)+'/directory-listings',dict(rootId='root',rootVersion=1)),('POST',path(w)+'/workspaces',dict(rootId='root',rootVersion=1,directoryToken='opaque-reference-token'))]:
            assert pat(env,token,method,route,body).json()['error']['code']=='REMOTE_API_TOKEN_SCOPE_INSUFFICIENT'


def test_query_account_limit_is_independent_of_device_limit(env):
    from contextlib import ExitStack
    workers=[Worker3(env,env.alice) for _ in range(5)]
    for w in workers:w.confirm()
    with ExitStack() as stack, ThreadPoolExecutor(max_workers=16) as pool:
        pages=[]
        for w in workers:
            stack.enter_context(w.connect());w.catalog();index,_=w.index()
            pages.append('/native-sessions/'+index['nativeSessionId']+'/messages')
        futures=[];queries=[]
        for w,p in zip(workers[:4],pages[:4]):
            for _ in range(4):
                futures.append(pool.submit(env.alice.get,p));queries.append((w,w.receive()))
        assert env.alice.get(pages[4]).status_code==429
        for w,q in queries:w.answer(q,native_page())
        assert all(f.result(timeout=5).status_code==200 for f in futures)
        assert not env.service.queries.pending


def test_late_index_behind_delete_gap_is_erased_before_contiguous_ack(env):
    w=Worker3(env,env.alice);w.confirm()
    with w.connect():
        w.catalog();index,initial=w.index()
        gap=w.event('sync.busy.snapshot',snapshotId=uid(),connectionId=w.ack['connectionId'],capturedAt=stamp(env.clock()),partIndex=0,partCount=1,conversationIds=[])
        late=w.event('native.index.upserted',syncGeneration=1,payload=initial['payload']|dict(indexVersion=2,title='LATE-ERASED-NATIVE-INDEX'))
        deletion=w.event('native.index.deleted',syncGeneration=1,nativeSessionId='native',workspaceId='ws',deletedAt=stamp(env.clock()),reason='source_removed')
        assert w.emit(deletion)['position']['seq']==2
        assert w.emit(late)['position']['seq']==2
        assert 'LATE-ERASED-NATIVE-INDEX' not in database_text(env)
        assert w.emit(gap)['position']['seq']==deletion['seq']


def test_old_connection_query_segments_do_not_complete_replacement(env):
    w=Worker3(env,env.alice);w.confirm()
    with w.connect(),ThreadPoolExecutor(max_workers=1) as pool:
        w.catalog();index,_=w.index()
        future=pool.submit(env.alice.get,'/native-sessions/'+index['nativeSessionId']+'/messages')
        q=w.receive();frame=w.query_frames(q,native_page())[0]
        w.ws.send_json(dict(frame,connectionId='old-connection'))
        w.ws.send_json(dict(frame,workerEpoch='old-epoch'))
        w.ws.send_json(dict(frame,queryId='unknown-query'))
        w.ws.send_json(frame)
        assert future.result(timeout=3).status_code==200
        assert w.busy()['position']['seq']==3


def test_registration_completes_from_worker_fact_not_server_catalog_mutation(env):
    w=Worker3(env,env.alice);w.confirm()
    with w.connect():
        w.catalog()
        result=env.alice.post(path(w)+'/workspaces',dict(rootId='root',rootVersion=1,directoryToken='signed-readonly-folder'))
        assert result.status_code==202
        command=w.receive();w.received(command);w.receive();w.accepted(command)
        control=dict(outcome='confirmed',executionMayStillBeRunning=False,orphanProcessIds=[],reason='registered',evidence='metadata_committed',observedAt=stamp(env.clock()))
        assert w.emit(w.event('command.completed',commandId=command['commandId'],resultStatus='confirmed',resourceRef=dict(workspaceId='new-local-workspace'),controlResult=control))['type']=='worker.events_ack'
        value=env.alice.get('/commands/'+command['commandId']).json()['data']
        assert set(value['resourceRef'])=={'workspaceId'} and value['resourceRef']['workspaceId']!='new-local-workspace'
        assert len(env.alice.get(path(w)+'/catalog').json()['data']['workspaces'])==1
        w.catalog(capabilityRevision=2,workspaces=[dict(workspaceId='new-local-workspace',name='Read only',displayPath='Selected project',vcs='none',canWrite=False)])
        assert env.alice.get(path(w)+'/catalog').json()['data']['workspaces'][0]['workspaceId']==value['resourceRef']['workspaceId']


def test_granted_import_reconciles_after_reset_without_restoring_body(env):
    w=Worker3(env,env.alice);w.confirm()
    with w.connect():
        w.catalog();index,_=w.index()
        response=env.alice.post('/native-sessions/'+index['nativeSessionId']+'/imports',import_body())
        assert response.status_code==202
        frame=w.receive();w.received(frame);w.receive();w.accepted(frame)
        w.emit(w.event('sync.reset',syncGeneration=2))
        control=dict(outcome='confirmed',executionMayStillBeRunning=False,orphanProcessIds=[],reason='ERASE-THIS-LATE-DISPLAY',evidence='metadata_committed',observedAt=stamp(env.clock()))
        assert w.emit(w.event('command.completed',commandId=frame['commandId'],resultStatus='confirmed',resourceRef=dict(workspaceId='ws',conversationId='imported',nativeSessionId='native'),controlResult=control))['type']=='worker.events_ack'
        with env.service.repo.transaction() as tx:
            command=tx.get(env.owner,'command',frame['commandId'])
            assert command['_granted'] and command['status']=='completed'
            assert tx.list(env.owner,'native-index',worker=w.worker)==[]
            assert tx.list(env.owner,'conversation',worker=w.worker)==[]
        assert 'ERASE-THIS-LATE-DISPLAY' not in database_text(env)


def test_import_completion_is_pollable_before_conversation_backfill(env):
    w=Worker3(env,env.alice);w.confirm()
    with w.connect():
        w.catalog();index,_=w.index()
        env.alice.post('/native-sessions/'+index['nativeSessionId']+'/imports',import_body())
        frame=w.receive();w.received(frame);w.receive();w.accepted(frame)
        control=dict(outcome='confirmed',executionMayStillBeRunning=False,orphanProcessIds=[],reason='committed',evidence='metadata_committed',observedAt=stamp(env.clock()))
        assert w.emit(w.event('command.completed',commandId=frame['commandId'],resultStatus='confirmed',resourceRef=dict(workspaceId='ws',conversationId='not-yet-synced',nativeSessionId='native'),controlResult=control))['type']=='worker.events_ack'
        polled=env.alice.get('/commands/'+frame['commandId'])
        assert polled.status_code==200 and polled.json()['data']['status']=='completed'
        assert env.alice.get('/conversations/'+polled.json()['data']['resourceRef']['conversationId']).status_code==404
