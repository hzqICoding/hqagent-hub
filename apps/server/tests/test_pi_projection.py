import copy
import json
from pathlib import Path

import pytest
from protocol.generated import python as dto

from test_attachments import Worker4, upload
from server.common import stamp, uid


class FeatureBrowser:
    def __init__(self, browser):
        self.browser = browser

    def __getattr__(self, key):
        return getattr(self.browser,key)

    def request(self, method, path, body=None, **kwargs):
        headers = {'X-HQ-Client-Features':'pi-v1', **kwargs.pop('headers',{})}
        return self.browser.request(method,path,body,headers=headers,**kwargs)

    def get(self,path):
        return self.request('GET',path)

    def post(self,path,body=None,**kwargs):
        return self.request('POST',path,{} if body is None else body,**kwargs)


class Worker5(Worker4):
    def hello(self,**changes):
        return super().hello(**(dict(wireRevision=5)|changes))

    def receive(self):
        frame=self.ws.receive_json()
        from server.wire import CODECS
        getattr(dto,CODECS[frame['wireRevision']][1]).model_validate(frame)
        return frame

    def event(self,kind,seq=None,**fields):
        self.seq=self.seq+1 if seq is None else seq
        value=dict(type=kind,wireRevision=5,workerId=self.worker,workerStoreId=self.store,workerEpoch=self.epoch,
                   eventId=uid(),seq=self.seq,occurredAt=stamp(self.env.clock()),**fields)
        dto.RemoteV5WorkerOutboundFrame.model_validate(value)
        return value


@pytest.fixture
def env(r15_env):
    r15_env.pi=FeatureBrowser(r15_env.alice)
    return r15_env


def catalog(w):
    unknown=dict(support='unknown',cliEntry='supported',runtimeImplemented=False,verified=False,mimeTypes=[],maxBytes=0)
    pi_role=dict(roleId='executor',agentId='runtime-opaque',agentType='pi',modelId='provider/model',transport='pi-rpc-images-v1',imageInput=unknown)
    normal_role=dict(pi_role,agentId='normal-runtime',agentType='codex',transport='old-cli',modelId='normal-model')
    guard=dict(status='ready',isolation='hub_extension_only',checkedAt=stamp(w.env.clock()),reasons=[])
    return dict(scenes=[dict(sceneId='scene',name='normal',version=1,readOnly=False,roleImageCapabilities=[normal_role]),
                        dict(sceneId='pi-scene',name='PI scenario',version=1,readOnly=False,roleImageCapabilities=[pi_role])],
                runtimes=[dict(agentId='runtime-opaque',agentType='pi',nativeSessionsSupported=False,guard=guard),
                          dict(agentId='normal-runtime',agentType='codex',nativeSessionsSupported=True)],
                nativeImageCapabilities=[dict(agentType='pi',agentId='runtime-opaque',modelId='provider/model',transport='pi-rpc-images-v1',imageInput=unknown),
                                         dict(agentType='codex',agentId='normal-runtime',modelId='normal-model',transport='old-cli',imageInput=unknown)])


def prepare(w):
    assert w.catalog(**catalog(w))['type']=='worker.events_ack'
    normal=w.upsert('normal')
    pi=w.upsert('pi-local',sceneId='pi-scene',title='PRIVATE-PI-TITLE')
    w.busy()
    return normal,pi


def test_catalog_shapes_and_direct_pi_resources_are_gated(env):
    w=Worker5(env,env.pi);w.confirm()
    with w.connect():
        normal,pi=prepare(w)
        path='/devices/'+w.worker+'/catalog'
        old=env.alice.get(path).json()['data'];new=env.pi.get(path).json()['data']
        dto.RemoteV4CatalogView.model_validate(old)
        assert [s['sceneId'] for s in old['scenes']]==['scene']
        assert 'runtimes' not in old and 'modelId' not in old['scenes'][0]['roleImageCapabilities'][0]
        assert 'agentType' not in old['scenes'][0]['roleImageCapabilities'][0]
        assert 'agentId' not in old['nativeImageCapabilities'][0]
        assert len(new['scenes'])==2 and new['runtimes'][0]['guard']['status']=='ready'
        assert env.alice.get('/conversations/'+pi).status_code==404
        assert env.bob.request('GET','/conversations/'+pi,headers={'X-HQ-Client-Features':'pi-v1'}).status_code==404
        assert env.pi.get('/conversations/'+pi).status_code==200
        assert [c['conversationId'] for c in env.alice.get('/conversations').json()['data']['items']]==[normal]
        workspace=new['workspaces'][0]['workspaceId']
        create=dict(targetWorkerId=w.worker,workerStoreId=w.store,workspaceId=workspace,sceneId='pi-scene',sceneVersion=1,title='new')
        assert env.alice.post('/conversations',create).status_code==404
        assert env.pi.post('/conversations',create).status_code==202
        frame=w.receive();assert frame['wireRevision']==5 and frame['payload']['sceneId']=='pi-scene'
        assert env.alice.get('/commands/'+frame['commandId']).status_code==404


def test_pi_message_run_approval_attachment_and_events_do_not_leak(env):
    w=Worker5(env,env.pi);w.confirm()
    with w.connect():
        normal,pi=prepare(w)
        old_tail=env.alice.get('/events').json()['data']['nextServerCursor']
        new_tail=env.pi.get('/events').json()['data']['nextServerCursor']
        assert w.emit(w.message('pi-local','PRIVATE-PI-TEXT'))['type']=='worker.events_ack'
        assert w.emit(w.event('sync.run.state',syncGeneration=1,payload=dict(runId='pi-run',conversationId='pi-local',status='waiting_approval',observedAt=stamp(env.clock()))))['type']=='worker.events_ack'
        approval=dict(approvalId='pi-approval',resultRef=dict(runId='pi-run'),action='git_push',targetSummary='PRIVATE-PI-TARGET',riskLevel='high',status='pending',requestedAt=stamp(env.clock()),expiresAt=stamp(env.clock()+120),remoteApprovalAllowed=False,workerPolicyRevision=1)
        assert w.emit(w.event('approval.state_changed',conversationId='pi-local',payload=approval))['type']=='worker.events_ack'
        snapshot=env.pi.get('/conversations/'+pi+'/snapshot').json()['data']
        run=snapshot['runs'][0]['runId'];aid=snapshot['approvals'][0]['approvalId']
        for path in ['/conversations/'+pi+'/messages','/conversations/'+pi+'/snapshot','/runs/'+run,'/approvals/'+aid]:
            assert env.alice.get(path).status_code==404
            assert env.pi.get(path).status_code==200
        assert env.pi.post('/approvals/'+aid+'/decisions',dict(decision='approve')).json()['error']['code']=='REMOTE_APPROVAL_FORBIDDEN'
        rejected=env.pi.post('/approvals/'+aid+'/decisions',dict(decision='reject'))
        assert rejected.status_code==202
        command=w.receive();assert command['wireRevision']==5
        old=env.alice.get('/events?after='+old_tail).json()['data']
        assert old['items']==[] and old['nextServerCursor']!=old_tail and not old['hasMore']
        new=env.pi.get('/events?after='+new_tail).json()['data']
        assert new['items'] and any(e['type']=='conversation.updated' for e in new['items'])
        assert 'PRIVATE-PI' not in json.dumps(old)
        assert env.alice.get('/events?after='+new_tail).json()['error']['code']=='REMOTE_CURSOR_INVALID'
        assert env.pi.get('/events?after='+old_tail).json()['error']['code']=='REMOTE_CURSOR_INVALID'
        uploaded=upload(env,pi,b'pi input',headers={'X-HQ-Client-Features':'pi-v1'})
        assert uploaded.status_code==201
        attachment=uploaded.json()['data']['attachment']['attachmentId']
        assert env.alice.get('/attachments/'+attachment).status_code==404
        assert env.pi.get('/attachments/'+attachment).status_code==200
        before_delete=env.alice.get('/events').json()['data']['nextServerCursor']
        w.emit(w.event('sync.conversation.deleted',syncGeneration=1,conversationId='pi-local',deletedAt=stamp(env.clock())))
        assert env.alice.get('/events?after='+before_delete).json()['data']['items']==[]


def test_native_pi_index_and_diagnostics_feature_binding(env):
    w=Worker5(env,env.pi);w.confirm()
    with w.connect():
        w.catalog(**catalog(w))
        normal,_=w.index(title='normal-index',format=dict(status='unsupported',reason='unsupported',unsupportedReason='reader_not_implemented'))
        pi,_=w.index('pi-native',title='PRIVATE-PI-INDEX',agentType='pi',format=dict(status='unsupported',reason='not implemented',unsupportedReason='reader_not_implemented'))
        old=env.alice.get('/devices/'+w.worker+'/native-sessions').json()['data']
        assert len(old['items'])==1 and old['items'][0]['nativeSessionId']==normal['nativeSessionId']
        dto.NativeSessionIndex.model_validate({k:v for k,v in old['items'][0].items() if k not in {'workerId','workerOnline'}})
        assert 'unsupportedReason' not in old['items'][0]['format']
        assert len(env.pi.get('/devices/'+w.worker+'/native-sessions').json()['data']['items'])==2
        assert env.alice.get('/native-sessions/'+pi['nativeSessionId']).status_code==404
        assert env.alice.get('/native-sessions/'+pi['nativeSessionId']+'/messages').status_code==404
        assert env.pi.get('/native-sessions/'+pi['nativeSessionId']+'/messages').json()['error']['code']=='NATIVE_SESSION_UNSUPPORTED'
        w.emit(w.event('sync.reset',syncGeneration=2))
        assert env.alice.get('/native-sessions/'+pi['nativeSessionId']).status_code==404
        assert env.pi.get('/native-sessions/'+pi['nativeSessionId']).json()['error']['code']=='REMOTE_SYNC_DISABLED'


def test_all_list_and_message_cursors_bind_features(env):
    w=Worker5(env,env.pi);w.confirm()
    other=Worker5(env,env.pi);other.confirm()
    with w.connect():
        normal,pi=prepare(w)
        w.upsert('second-normal')
        for n in range(2):w.emit(w.message('normal','message',sequence=n+1))
        for path in ['/devices?limit=1','/conversations?limit=1']:
            cursor=env.pi.get(path).json()['data']['nextCursor']
            assert env.alice.get(path+'&cursor='+cursor).json()['error']['code']=='REMOTE_CURSOR_INVALID'
        before=env.pi.get('/conversations/'+normal+'/messages?limit=1').json()['data']['before']
        assert env.alice.get('/conversations/'+normal+'/messages?before='+before).json()['error']['code']=='REMOTE_CURSOR_INVALID'


def test_header_validation_and_no_guess_from_package_or_user_agent(env):
    for value in ['', 'PI-V1', 'unknown', 'pi-v1,other']:
        response=env.alice.request('GET','/devices',headers={'X-HQ-Client-Features':value})
        assert response.status_code==422
    w=Worker5(env,env.pi);w.confirm()
    with w.connect():
        _,pi=prepare(w)
        assert env.alice.request('GET','/conversations/'+pi,headers={'User-Agent':'0.11.0 pi-v1'}).status_code==404


def test_native_pi_query_import_and_ungranted_receipt_stay_feature_scoped(env):
    from concurrent.futures import ThreadPoolExecutor
    from r3_support import native_page
    w=Worker5(env,env.pi);w.confirm()
    profile=dict(readerId='pi.jsonl.v3.tree',sessionVersion=3,structure='tree',branchSelection='last_persisted_entry')
    with w.connect(), ThreadPoolExecutor(max_workers=1) as pool:
        w.catalog(**catalog(w))
        index,_=w.index('pi-native',agentType='pi',format=dict(status='readable',readerId='pi.jsonl.v3.tree',pi=profile))
        pending=pool.submit(env.pi.get,'/native-sessions/'+index['nativeSessionId']+'/messages')
        query=w.receive();assert query['wireRevision']==5
        for frame in w.query_frames(query,native_page('pi-native','ephemeral PI history')):
            frame['wireRevision']=5
            dto.RemoteV5WorkerOutboundFrame.model_validate(frame)
            w.ws.send_json(frame)
        assert pending.result(timeout=3).status_code==200
        path='/native-sessions/'+index['nativeSessionId']+'/imports'
        body=dict(terminalClosedConfirmed=True,expectedIndexVersion=1,sourceRevision='a'*64)
        assert env.alice.post(path,body).status_code==404
        result=env.pi.post(path,body)
        assert result.status_code==202
        command=w.receive();assert command['type']=='native.import' and command['wireRevision']==5
        assert env.alice.get('/commands/'+command['commandId']).status_code==404
        w.received(command);assert w.receive()['type']=='command.delivery_granted'


def test_pi_image_support_needs_exact_instance_and_transport(env):
    import io
    from PIL import Image
    w=Worker5(env,env.pi);w.confirm()
    with w.connect():
        _,pi=prepare(w)
        image=io.BytesIO();Image.new('RGB',(2,2)).save(image,format='PNG')
        item=upload(env,pi,image.getvalue(),'image.png',headers={'X-HQ-Client-Features':'pi-v1'}).json()['data']['attachment']
        body=dict(clientMessageId=uid(),text='image',sessionMode='new',attachmentIds=[item['attachmentId']])
        assert env.pi.post('/conversations/'+pi+'/messages',body).json()['error']['code']=='AGENT_IMAGE_UNSUPPORTED'
        updated=catalog(w);binding=updated['scenes'][1]['roleImageCapabilities'][0]
        binding['imageInput']=dict(support='supported',cliEntry='supported',runtimeImplemented=True,verified=True,mimeTypes=['image/png'],maxBytes=10000000)
        binding.pop('transport')
        w.catalog(capabilityRevision=2,**updated)
        assert env.pi.post('/conversations/'+pi+'/messages',body).json()['error']['code']=='AGENT_IMAGE_UNSUPPORTED'
        binding['transport']='pi-rpc-images-v1'
        w.catalog(capabilityRevision=3,**updated)
        assert env.pi.post('/conversations/'+pi+'/messages',body).status_code==202
        command=w.receive();assert command['payload']['attachmentCapabilityRevision']==3


def test_legacy_snapshot_skips_all_pi_events_without_cursor_stall(env):
    w=Worker5(env,env.pi);w.confirm()
    with w.connect():
        _,pi=prepare(w)
        tail=env.alice.get('/events').json()['data']['nextServerCursor']
        for n in range(8):w.emit(w.message('pi-local','PI-only',sequence=n+1))
        page=env.alice.get('/events?after='+tail+'&limit=1').json()['data']
        assert page['items']==[] and page['nextServerCursor']!=tail and not page['hasMore']
        assert env.alice.get('/events?after='+page['nextServerCursor']+'&limit=1').json()['data']['items']==[]
