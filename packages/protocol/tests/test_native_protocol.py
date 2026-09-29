"""R3 contract conformance only: synthetic data, no native files/CLI/network."""
from copy import deepcopy
from functools import lru_cache
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest
from pydantic import TypeAdapter, ValidationError
import yaml
from protocol.generated.python import models

P=Path(__file__).resolve().parents[1]
ROOT=P.parents[1]
BASE='2b3377c'
F=P/'fixtures/contracts'
M=json.loads((F/'manifest.json').read_text(encoding='utf-8'))['fixtures']
R3=json.loads((P/'schema/remote-native.json').read_text(encoding='utf-8'))['$defs']
API=yaml.safe_load((P/'openapi/remote-hub.v2.yaml').read_text(encoding='utf-8'))


@lru_cache(None)
def baseline(file):
    return subprocess.check_output(['git','show',f'{BASE}:packages/protocol/{file}'],cwd=ROOT).decode('utf-8')


def sample(kind):
    path=next(f for f,k in M.items() if k==kind and f.startswith('r3.'))
    return json.loads((F/path).read_text(encoding='utf-8'))


def defs():
    return {n:v for f in (P/'schema').glob('*.json')
            for n,v in json.loads(f.read_text(encoding='utf-8'))['$defs'].items()}


def dependencies(value):
    if isinstance(value,dict):
        if '$ref' in value:yield value['$ref']
        for v in value.values():yield from dependencies(v)
    elif isinstance(value,list):
        for v in value:yield from dependencies(v)


@pytest.mark.parametrize('revision,rootfile,rootnames',[
    (1,'remote.json',['RemoteWorkerOutboundFrame','RemoteServerOutboundFrame']),
    (2,'remote-sync.json',['RemoteV2WorkerOutboundFrame','RemoteV2ServerOutboundFrame']),
])
def test_frozen_wire_transitive_closure_not_just_top_level(revision,rootfile,rootnames):
    pending=[(rootfile,n) for n in rootnames];seen=set()
    while pending:
        file,name=pending.pop()
        if (file,name) in seen:continue
        seen.add((file,name))
        old=json.loads(baseline('schema/'+file))['$defs'][name]
        new=json.loads((P/'schema'/file).read_text(encoding='utf-8'))['$defs'][name]
        assert old==new,(revision,file,name)
        # Public registry growth may not silently widen a frozen wire field.
        assert '"x-registry": "error-codes"' not in json.dumps(new)
        for ref in dependencies(old):
            target,pointer=ref.split('#',1)
            pending.append((target or file,pointer.split('/')[-1]))


def test_old_fixture_files_byte_identical():
    # One git process for the manifest and each historical file, no user data.
    old=json.loads(baseline('fixtures/contracts/manifest.json'))['fixtures']
    for f,n in old.items():
        assert M[f]==n
        assert (F/f).read_text(encoding='utf-8')==baseline('fixtures/contracts/'+f)


def test_each_new_type_and_every_revision3_frame_has_fixture():
    assert set(R3) <= {n for f,n in M.items() if f.startswith('r3.')}
    assert models.PROTOCOL_VERSION==API['info']['version']=='0.9.1'
    assert set(API['x-worker-websocket']['revisions'])=={1,2,3}
    assert all(v['properties']['wireRevision']['const']==3 for v in R3.values() if 'wireRevision' in v.get('properties',{}))


@pytest.mark.parametrize('file,kind',[(f,n) for f,n in M.items() if f.startswith('r3.')])
def test_synthetic_fixture_roundtrip(file,kind):
    raw=json.loads((F/file).read_text(encoding='utf-8'))
    adapter=TypeAdapter(getattr(models,kind))
    assert adapter.dump_python(adapter.validate_python(raw),mode='json',by_alias=True,exclude_none=True)==raw


@pytest.mark.parametrize('root',['RemoteV3WorkerOutboundFrame','RemoteV3ServerOutboundFrame'])
def test_revision3_unions_accept_all_of_their_concrete_frames(root):
    all_defs=defs();seen=set();pending=[root];adapter=TypeAdapter(getattr(models,root))
    while pending:
        name=pending.pop()
        if name in seen:continue
        seen.add(name);value=all_defs[name]
        if 'oneOf' in value:
            pending.extend(v['$ref'].split('/')[-1] for v in value['oneOf'])
        else:
            raw=sample(name);adapter.validate_python(raw)
            raw['wireRevision']=2
            with pytest.raises(ValidationError):adapter.validate_python(raw)


@pytest.mark.parametrize('kind',['RemoteV3NativeReadQuery','RemoteV3DirectoryQuery','RemoteV3QueryResultSegment','RemoteV3QueryFailed'])
@pytest.mark.parametrize('field',['seq','eventId','commandId','conversationSeq'])
def test_ephemeral_queries_cannot_enter_reliable_or_command_lanes(kind,field):
    raw=sample(kind);raw[field]=1 if field.endswith('Seq') or field=='seq' else 'synthetic'
    with pytest.raises(ValidationError):getattr(models,kind).model_validate(raw)


@pytest.mark.parametrize('kind',['RemoteV3NativeImportCommand','RemoteV3WorkspaceRegisterCommand'])
def test_resource_commands_do_not_invent_conversation_or_sequence(kind):
    raw=sample(kind)
    for field in ['conversationSeq','conversationId','localConversationId','runId']:
        bad=deepcopy(raw);bad[field]=1 if field=='conversationSeq' else 'fake'
        with pytest.raises(ValidationError):getattr(models,kind).model_validate(bad)
    assert {'deliverBy','expiresAt','requestId','expectedWorkerStoreId'}<=raw.keys()


@pytest.mark.parametrize('code',['REMOTE_QUERY_TIMEOUT','NATIVE_SESSION_ACTIVE','REMOTE_PATH_OUTSIDE_ROOT'])
def test_r3_error_is_not_accepted_on_older_wire(code):
    for revision,kind in [(1,'RemoteWorkerHelloRejected'),(2,'RemoteV2WorkerHelloRejected')]:
        file=next(f for f,n in M.items() if n==kind)
        raw=json.loads((F/file).read_text(encoding='utf-8'));raw['error']['code']=code
        with pytest.raises(ValidationError):getattr(models,kind).model_validate(raw)
    raw=sample('RemoteV3QueryFailed');raw['error']['code']=code
    models.RemoteV3QueryFailed.model_validate(raw)


def test_d50_http_only_errors_stay_off_revision3():
    for code in ['REMOTE_DEVICE_SUSPENDED','REMOTE_API_TOKEN_INVALID','REMOTE_AUTH_AMBIGUOUS']:
        raw=sample('RemoteV3QueryFailed');raw['error']['code']=code
        with pytest.raises(ValidationError):models.RemoteV3QueryFailed.model_validate(raw)


def test_native_index_contains_no_content_or_path_and_has_explicit_activity():
    raw=sample('NativeSessionIndex')
    assert raw['activity']['activity']=='unknown'
    for field in ['text','messages','cwd','path','toolArguments','latest']:
        bad=deepcopy(raw);bad[field]='synthetic'
        with pytest.raises(ValidationError):models.NativeSessionIndex.model_validate(bad)
    bad=deepcopy(raw);bad['title']='a'*121
    with pytest.raises(ValidationError):models.NativeSessionIndex.model_validate(bad)


def test_no_arbitrary_path_on_cloud_browse_or_register():
    for kind in ['DirectoryListingInput','RemoteWorkspaceRegisterInput']:
        for field in ['path','relativePath','cwd','ownerId']:
            bad=sample(kind);bad[field]='../outside'
            with pytest.raises(ValidationError):getattr(models,kind).model_validate(bad)
    raw=sample('RemoteAuthorizedRoot');raw['path']='E:/private'
    with pytest.raises(ValidationError):models.RemoteAuthorizedRoot.model_validate(raw)


@pytest.mark.parametrize('kind,field,value',[
    ('DirectoryListingInput','limit',101),('DirectoryListingInput','limit',0),
    ('NativeReadInput','limit',101),('NativeReadInput','limit',True),
    ('RemoteV3QueryResultSegment','segmentCount',129),
    ('RemoteV3QueryResultSegment','totalUtf8Bytes',1048577),
    ('RemoteV3QueryResultSegment','text','a'*16001),
    ('RemoteNativeImportInput','terminalClosedConfirmed',False),
    ('RemoteNativeImportInput','terminalClosedConfirmed','true'),
])
def test_structural_limits_and_no_implicit_confirmation(kind,field,value):
    raw=sample(kind);raw[field]=value
    with pytest.raises(ValidationError):getattr(models,kind).model_validate(raw)


def test_query_segment_is_complete_typed_synthetic_json_and_hash_not_metadata_hash():
    raw=sample('RemoteV3QueryResultSegment');text=raw['text'].encode('utf-8')
    assert raw['totalUtf8Bytes']==len(text)
    assert raw['contentSha256']==hashlib.sha256(text).hexdigest()
    data=json.loads(text);models.NativeMessagePage.model_validate(data)
    part=data['items'][0]
    assert part['contentSha256']==hashlib.sha256(part['text'].encode('utf-8')).hexdigest()


def test_http_view_and_input_deltas_are_exact_and_wire_submit_gets_own_type():
    old=json.loads(baseline('schema/remote.json'))['$defs'];new=defs()
    view=deepcopy(old['RemoteConversationView'])
    view['required']=[x for x in view['required'] if x not in ['sceneId','sceneVersion']]
    extra={'conversationKind','agentType','nativeSessionId','nativeActivity','nativeSourceRevision'}
    current=new['RemoteConversationView']
    assert set(current['properties'])-set(view['properties'])==extra
    for k,v in view['properties'].items():assert current['properties'][k]==v
    assert current['required']==view['required']
    command=deepcopy(old['RemoteCommandView']);command['required'].remove('conversationId')
    command['properties']['type']['enum']+=['native.import','workspace.register']
    command['properties']['resourceRef']={'$ref':'remote-native.json#/$defs/RemoteResourceResultRef'}
    command['description']=new['RemoteCommandView']['description']
    assert command==new['RemoteCommandView']
    send=deepcopy(old['RemoteSendMessageInput'])
    send['properties']['nativeConfirmation']={'$ref':'remote-native.json#/$defs/NativeContinuationConfirmationInput'}
    send['description']=new['RemoteSendMessageInput']['description']
    assert send==new['RemoteSendMessageInput']
    assert new['RemoteRunSubmitPayload']==old['RemoteRunSubmitPayload']
    assert new['RemoteV3RunSubmitCommand']['properties']['payload']=={'$ref':'remote-native.json#/$defs/RemoteV3RunSubmitPayload'}


def test_native_views_and_submit_need_no_fake_scene():
    for n in ['LocalConversationView','RemoteConversationView']:
        raw=sample(n);assert 'sceneId' not in raw and raw['conversationKind']=='native'
        getattr(models,n).model_validate(raw)
    raw=json.loads((F/'r3.native-run-submit-payload.json').read_text(encoding='utf-8'))
    models.RemoteV3RunSubmitPayload.model_validate(raw)
    with pytest.raises(ValidationError):models.RemoteRunSubmitPayload.model_validate(raw)


def test_new_http_routes_cookie_only_and_local_roots_never_cloud_writable():
    routes=[(path,op) for path,item in API['paths'].items() for op in item.values()
            if 'native-sessions' in path or path.endswith('/directory-listings') or path.endswith('/workspaces')]
    assert len(routes)==6
    for path,op in routes:
        assert op['security']==[{'remoteSession':[]}]
        assert op['x-auth-mode']=='cookie'
    assert not any('authorized-roots' in path for path in API['paths'])
    for file,version,auth in [('local-hub.v1.yaml','v1','bearerAuth'),('local-chat.v2.yaml','v2','localSession')]:
        api=yaml.safe_load((P/'openapi'/file).read_text(encoding='utf-8'))
        ops=api['paths'][f'/api/{version}/remote/authorized-roots']
        assert set(ops)=={'get','put'}
        for op in ops.values():assert op['security']==[{auth:[]}]
        body=ops['put']['requestBody']['content']['application/json']['schema']
        assert body=={'$ref':'../schema/remote-native.json#/$defs/LocalAuthorizedRootsInput'}


def test_pat_enabled_scopes_not_expanded_and_revision3_no_attempt_identity():
    all_defs=defs()
    scopes=all_defs['RemoteApiTokenScope']['enum']
    assert set(scopes)=={'devices:read','devices:manage','devices:delete'}
    text=json.dumps(R3)
    for forbidden in ['attemptId','retryOfRunId','modelApiKey','modelSecret']:
        assert '"'+forbidden+'"' not in text


@pytest.mark.parametrize('mutation',['persist','sequence','wrong_type','deadline','missing_more_cursor'])
def test_api_check_rejects_r3_misleading_examples(mutation):
    spec=importlib.util.spec_from_file_location('r3_api_check',P/'remote/api-contract.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    bad=deepcopy(API)
    query=bad['paths']['/api/v2/devices/{workerId}/directory-listings']['post']
    resource=bad['paths']['/api/v2/native-sessions/{nativeSessionId}/imports']['post']
    data=resource['responses']['202']['content']['application/json']['examples']['success']['value']['data']
    if mutation=='persist':query['x-persist-response']=True
    elif mutation=='sequence':data['conversationSeq']=1
    elif mutation=='wrong_type':data['type']='workspace.register'
    elif mutation=='deadline':data['expiresAt']='2026-09-28T12:05:00Z'
    else:query['responses']['200']['content']['application/json']['examples']['success']['value']['data']['hasMore']=True
    with pytest.raises(AssertionError):module.check_example_semantics(bad)
