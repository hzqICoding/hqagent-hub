import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from protocol.generated import python as dto

from r3_support import Worker3, native_page, directory_page
from r15_support import Worker2
from server.common import Fault, digest, stamp, uid
from test_r15_replica import database_text


@pytest.fixture
def env(r15_env):
    with r15_env.service.repo.transaction() as tx:
        r15_env.owner = r15_env.service.security.session(tx,r15_env.alice.cookie)['owner']
    return r15_env


def import_body(): return dict(terminalClosedConfirmed=True,expectedIndexVersion=1,sourceRevision='a'*64)
def path(w): return '/devices/'+w.worker


def test_r3_index_isolation_paging_and_reset_erasure(env):
    a,b = Worker3(env,env.alice),Worker3(env,env.alice)
    a.confirm();b.confirm()
    with a.connect(), b.connect():
        a.catalog(); b.catalog()
        first,_=a.index(title='first'); second,_=b.index(title='other-device')
        assert first['nativeSessionId'] != second['nativeSessionId'] and first['workspaceId'] != second['workspaceId']
        assert env.bob.get('/native-sessions/'+first['nativeSessionId']).status_code==404
        assert env.alice.get(path(a)+'/native-sessions?workspaceId='+second['workspaceId']).status_code==404
        a.index('second',title='second')
        page=env.alice.get(path(a)+'/native-sessions?limit=1').json()['data']
        assert page['hasMore']
        assert env.alice.get(path(a)+'/native-sessions?cursor='+page['nextCursor']).json()['data']['hasMore'] is False
        assert env.alice.get(path(b)+'/native-sessions?cursor='+page['nextCursor']).status_code==400
        a.emit(a.event('sync.reset',syncGeneration=2))
        disabled = env.alice.get('/native-sessions/'+first['nativeSessionId'])
        assert disabled.status_code == 409 and disabled.json()['error']['code'] == 'REMOTE_SYNC_DISABLED'
        with env.service.repo.transaction() as tx:
            assert tx.list(env.owner,'native-index',worker=a.worker)==[]
            assert len(tx.list(env.owner,'native-index',worker=b.worker))==1
        env.alice.request('DELETE',path(b))
        assert 'other-device' not in database_text(env)


def test_native_read_query_out_of_order_duplicate_no_database_or_logs(env,caplog):
    caplog.set_level('INFO',logger='hqremote')
    w=Worker3(env,env.alice);w.confirm()
    with w.connect(), ThreadPoolExecutor(max_workers=1) as pool:
        w.catalog(); index,_=w.index()
        response=pool.submit(env.alice.get,'/native-sessions/'+index['nativeSessionId']+'/messages?before=old-source-cursor-12345')
        query=w.receive()
        assert query['payload']['nativeSessionId']=='native' and 'sourceRevision' not in query['payload']
        frames=w.query_frames(query,native_page(text='ephemeral-secret-marker'*50),width=300)
        for frame in list(reversed(frames[1:]))+[frames[1],frames[0]]: w.ws.send_json(frame)
        result=response.result(timeout=3)
        assert result.status_code==200,result.text
        assert result.json()['data']['nativeSessionId']==index['nativeSessionId']
        assert result.headers['x-request-id']==query['requestId']==result.json()['requestId']
        assert 'ephemeral-secret-marker' not in database_text(env)+caplog.text
        assert 'old-source-cursor-12345' not in database_text(env)+caplog.text
        assert not env.service.queries.pending
        # No reliable seq allocated for queries, next ordinary event remains contiguous.
        assert w.busy()['position']['seq']==3


@pytest.mark.parametrize('outcome',['timeout','oversize','disconnect','reset','conflict'])
def test_query_failure_cleans_memory_and_never_persists(env,monkeypatch,outcome):
    w=Worker3(env,env.alice);w.confirm()
    if outcome=='timeout': monkeypatch.setattr('server.queries.QUERY_TIMEOUT',0.15)
    with w.connect(), ThreadPoolExecutor(max_workers=1) as pool:
        w.catalog(); index,_=w.index()
        future=pool.submit(env.alice.get,'/native-sessions/'+index['nativeSessionId']+'/messages')
        query=w.receive()
        frames=w.query_frames(query,native_page(text='temporary-query-marker'*50),width=300)
        w.ws.send_json(frames[0])
        expected={'timeout':504,'oversize':413,'disconnect':409,'reset':409,'conflict':409}[outcome]
        if outcome=='oversize': w.ws.send_json(dict(frames[1],totalUtf8Bytes=1048577))
        elif outcome=='disconnect': w.ws.close()
        elif outcome=='reset': w.emit(w.event('sync.reset',syncGeneration=2))
        elif outcome=='conflict': w.ws.send_json(dict(frames[0],text='different'))
        result=future.result(timeout=3)
        assert result.status_code==expected,result.text
        assert not env.service.queries.pending
        assert 'temporary-query-marker' not in database_text(env)


def test_directory_query_digest_only_and_worker_token_rejection(env,caplog):
    caplog.set_level('INFO',logger='hqremote')
    w=Worker3(env,env.alice);w.confirm(); key=uid()
    body=dict(rootId='root',rootVersion=1,directoryToken='worker-issued-short-lived-choice')
    with w.connect(), ThreadPoolExecutor(max_workers=1) as pool:
        w.catalog()
        for _ in range(2):
            future=pool.submit(env.alice.post,path(w)+'/directory-listings',body,key=key)
            query=w.receive(); w.answer(query,directory_page())
            assert future.result(timeout=3).status_code==200
        assert env.alice.post(path(w)+'/directory-listings',dict(body,limit=10),key=key).status_code==409
        assert 'worker-issued-short-lived-choice' not in database_text(env)+caplog.text
        assert 'child-private-name' not in database_text(env)+caplog.text
        future=pool.submit(env.alice.post,path(w)+'/directory-listings',body)
        query=w.receive()
        failed=dict(type='query.failed',wireRevision=3,queryId=query['queryId'],requestId=query['requestId'],connectionId=query['connectionId'],workerId=w.worker,workerStoreId=w.store,workerEpoch=w.epoch,error=Fault('REMOTE_DIRECTORY_CHANGED').view())
        w.ws.send_json(failed)
        assert future.result(timeout=3).json()['error']['code']=='REMOTE_DIRECTORY_CHANGED'
        w.catalog(capabilityRevision=2,authorizedRoots=[])
        assert env.alice.post(path(w)+'/directory-listings',body).json()['error']['code']=='REMOTE_ROOT_NOT_AUTHORIZED'


def test_resource_import_confirmation_grant_and_native_full_sync(env):
    w=Worker3(env,env.alice);w.confirm()
    with w.connect():
        w.catalog(); index,_=w.index()
        result=env.alice.post('/native-sessions/'+index['nativeSessionId']+'/imports',import_body())
        assert result.status_code==202,result.text
        receipt=result.json()['data']; frame=w.receive()
        assert 'conversationId' not in receipt and 'conversationSeq' not in frame
        assert frame['payload']['confirmation']['requestId']==result.json()['requestId']
        w.received(frame); grant=w.receive()
        assert grant['type']=='command.delivery_granted' and 'conversationId' not in grant
        env.clock.advance(31)
        assert env.alice.get('/commands/'+frame['commandId']).json()['data']['deliveryState']=='granted'
        w.accepted(frame)
        w.emit(w.event('native.closure.confirmed',commandId=frame['commandId'],nativeSessionId='native',confirmation=frame['payload']['confirmation']))
        payload=dict(conversationId='imported',workspaceId='ws',title='Imported',createdAt=stamp(env.clock()),updatedAt=stamp(env.clock()),archived=False,visibility='both',metadataVersion=1,authority='local',conversationKind='native',agentType='codex',nativeSessionId='native',nativeSourceRevision='a'*64,
                     nativeActivity=dict(activity='closed_confirmed',observedAt=stamp(env.clock()),processMatch='absent',recentlyModified=False))
        assert w.emit(w.event('sync.conversation.upserted',syncGeneration=1,payload=payload))['type']=='worker.events_ack'
        control=dict(outcome='confirmed',executionMayStillBeRunning=False,orphanProcessIds=[],reason='committed',evidence='metadata_committed',observedAt=stamp(env.clock()))
        assert w.emit(w.event('command.completed',commandId=frame['commandId'],resultStatus='confirmed',controlResult=control,resourceRef=dict(workspaceId='ws',conversationId='imported',nativeSessionId='native')))['type']=='worker.events_ack'
        view=env.alice.get('/commands/'+frame['commandId']).json()['data']
        conv=view['resourceRef']['conversationId']
        assert view['resourceRef']['nativeSessionId']==index['nativeSessionId']
        w.emit(w.message('imported','complete imported history'))
        w.emit(w.event('native.index.deleted',syncGeneration=1,nativeSessionId='native',workspaceId='ws',deletedAt=stamp(env.clock()),reason='imported'))
        assert env.alice.get('/native-sessions/'+index['nativeSessionId']).status_code==404
        snapshot=env.alice.get('/conversations/'+conv+'/snapshot').json()['data']
        assert snapshot['messages'][0]['text']=='complete imported history'
        assert snapshot['conversation']['conversationKind']=='native' and 'sceneId' not in snapshot['conversation']
        w.busy()
        sent=env.alice.post('/conversations/'+conv+'/messages',dict(clientMessageId=uid(),text='continue',sessionMode='continue'))
        assert sent.status_code==202,sent.text
        submit=w.receive(); assert submit['payload']['nativeSessionId']=='native' and submit['payload']['workspaceId']=='ws'
        assert 'sceneId' not in submit['payload']


def test_pause_read_allowed_resource_blocked_and_workspace_register(env):
    w=Worker3(env,env.alice);w.confirm()
    with w.connect(), ThreadPoolExecutor(max_workers=1) as pool:
        w.catalog(); index,_=w.index()
        body=dict(rootId='root',rootVersion=1,directoryToken='worker-signed-directory')
        registered=env.alice.post(path(w)+'/workspaces',body)
        assert registered.status_code==202,registered.text
        frame=w.receive()
        env.alice.request('PATCH',path(w),dict(expectedVersion=1,remoteAccess='suspended'))
        w.received(frame)
        assert env.alice.get('/commands/'+frame['commandId']).json()['data']['status']=='failed'
        for p,b in [(path(w)+'/workspaces',body),(path(w)+'/directory-listings',body),('/native-sessions/'+index['nativeSessionId']+'/imports',import_body())]:
            assert env.alice.post(p,b).json()['error']['code']=='REMOTE_DEVICE_SUSPENDED'
        future=pool.submit(env.alice.get,'/native-sessions/'+index['nativeSessionId']+'/messages')
        q=w.receive();w.answer(q,native_page());assert future.result(timeout=3).status_code==200
