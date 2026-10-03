"""R1.6 static contracts, synthetic inputs only; no blob/model implementation."""
from copy import deepcopy
from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest
from pydantic import TypeAdapter, ValidationError
import yaml
from protocol.generated.python import models

P=Path(__file__).resolve().parents[1]
BASE='9770e4e'
F=P/'fixtures/contracts'
M=json.loads((F/'manifest.json').read_text(encoding='utf-8'))['fixtures']
D=json.loads((P/'schema/remote-attachments.json').read_text(encoding='utf-8'))['$defs']
API=yaml.safe_load((P/'openapi/remote-hub.v2.yaml').read_text(encoding='utf-8'))


def sample(n):return json.loads((F/('r16.'+n+'.json')).read_text(encoding='utf-8'))


@lru_cache(None)
def original(file):
    return subprocess.check_output(['git','show',f'{BASE}:packages/protocol/{file}'],cwd=P).decode('utf-8')


def refs(v):
    if isinstance(v,dict):
        if '$ref' in v:yield v['$ref']
        for x in v.values():yield from refs(x)
    elif isinstance(v,list):
        for x in v:yield from refs(x)


def test_old_three_revisions_transitive_closure_and_fixtures_unchanged():
    pending=[('remote.json','RemoteWorkerOutboundFrame'),('remote.json','RemoteServerOutboundFrame')]
    for rev,file in [(2,'remote-sync.json'),(3,'remote-native.json')]:
        pending += [(file,f'RemoteV{rev}WorkerOutboundFrame'),(file,f'RemoteV{rev}ServerOutboundFrame')]
    seen=set()
    while pending:
        file,n=pending.pop()
        if (file,n) in seen:continue
        seen.add((file,n))
        old=json.loads(original('schema/'+file))['$defs'][n]
        current=json.loads((P/'schema'/file).read_text(encoding='utf-8'))['$defs'][n]
        assert current==old,(file,n)
        assert '"x-registry": "error-codes"' not in json.dumps(current)
        for r in refs(old):
            target,pointer=r.split('#',1);pending.append((target or file,pointer.split('/')[-1]))
    for f,n in json.loads(original('fixtures/contracts/manifest.json'))['fixtures'].items():
        assert M[f]==n and (F/f).read_text(encoding='utf-8')==original('fixtures/contracts/'+f)


@pytest.mark.parametrize('file,kind',[(f,n) for f,n in M.items() if f.startswith('r16.')])
def test_all_new_fixtures_roundtrip(file,kind):
    raw=json.loads((F/file).read_text(encoding='utf-8'));adapter=TypeAdapter(getattr(models,kind))
    assert adapter.dump_python(adapter.validate_python(raw),mode='json',by_alias=True,exclude_none=True)==raw
    if isinstance(raw,dict) and 'wireRevision' in raw:
        assert len(json.dumps(raw,ensure_ascii=False).encode('utf-8'))<=262144


def test_type_coverage_version_and_limits():
    assert set(D)|{'AgentInputAttachment'}=={n for f,n in M.items() if f.startswith('r16.')}
    assert models.PROTOCOL_VERSION==API['info']['version']=='0.11.0'
    assert set(API['x-worker-websocket']['revisions'])=={1,2,3,4,5}
    l=sample('AttachmentLimits')
    assert [l[k] for k in ['imageMaxBytes','fileMaxBytes','messageMaxCount','accountQuotaBytes','unattachedTtlSeconds']]==[10000000,20000000,5,5000000000,86400]
    assert set(l['imageMimeTypes'])=={'image/jpeg','image/png','image/webp','image/gif'}
    assert {'.pdf','.txt','.md','.json','.py','.kt','.java'}<=set(l['fileExtensions'])
    assert not {'.html','.svg','.exe','.zip'} & set(l['fileExtensions'])


@pytest.mark.parametrize('kind',['RemoteV4WorkerOutboundFrame','RemoteV4ServerOutboundFrame'])
def test_every_new_codec_frame_is_revision4_and_paths_do_not_reach_wire(kind):
    all_defs={n:v for f in (P/'schema').glob('*.json') for n,v in json.loads(f.read_text(encoding='utf-8'))['$defs'].items()}
    pending=[kind];seen=set();adapter=TypeAdapter(getattr(models,kind))
    while pending:
        n=pending.pop()
        if n in seen:continue
        seen.add(n);v=all_defs[n]
        if 'oneOf' in v:pending.extend(r['$ref'].split('/')[-1] for r in v['oneOf'])
        else:
            raw=sample(n);adapter.validate_python(raw);raw['wireRevision']=3
            with pytest.raises(ValidationError):adapter.validate_python(raw)
    pending=[kind];seen=set()
    while pending:
        n=pending.pop()
        if n in seen:continue
        seen.add(n)
        assert n not in {'AgentInputAttachment','AgentTaskSpec','LocalAttachmentView'}
        pending.extend(r.split('/')[-1] for r in refs(all_defs[n]))


@pytest.mark.parametrize('field',['url','localPath','base64','data','ownerId','authorization'])
def test_manifest_cannot_smuggle_bytes_paths_urls_or_owner(field):
    raw=sample('AttachmentManifestItem');raw[field]='synthetic'
    with pytest.raises(ValidationError):models.AttachmentManifestItem.model_validate(raw)


@pytest.mark.parametrize('kind',['RemoteSendMessageInput','SendLocalMessageInput'])
def test_five_attachment_ids_max_and_no_client_manifest(kind):
    raw={'clientMessageId':'synthetic','text':'Read file','sessionMode':'continue','attachmentIds':['a','b','c','d','e']}
    getattr(models,kind).model_validate(raw)
    bad=deepcopy(raw);bad['attachmentIds'].append('f')
    with pytest.raises(ValidationError):getattr(models,kind).model_validate(bad)
    raw['attachments']=[sample('AttachmentManifestItem')]
    with pytest.raises(ValidationError):getattr(models,kind).model_validate(raw)


def test_http_and_adapter_delta_is_explicit_not_broad_schema_relaxation():
    for file,name,key,value in [
        ('remote.json','RemoteSendMessageInput','attachmentIds',{'type':'array','items':{'type':'string','minLength':1,'maxLength':160},'maxItems':5}),
        ('remote.json','RemoteMessageView','attachments',{'type':'array','items':{'$ref':'remote-attachments.json#/$defs/MessageAttachmentView'},'maxItems':5}),
        ('remote.json','RemoteCommandView','controlResult',{'$ref':'remote-attachments.json#/$defs/RemoteV4ControlResult'}),
        ('adapter-port.json','AgentTaskSpec','inputAttachments',{'type':'array','items':{'$ref':'adapter-port.json#/$defs/AgentInputAttachment'},'maxItems':5}),
    ]:
        old=json.loads(original('schema/'+file))['$defs'][name];old['properties'][key]=value
        current=json.loads((P/'schema'/file).read_text(encoding='utf-8'))['$defs'][name]
        assert old==current


def test_preparation_cancel_requires_new_evidence_domain():
    raw=json.loads((F/'r16.input-preparation-cancelled.json').read_text(encoding='utf-8'))
    models.RemoteV4ControlConfirmed.model_validate(raw)
    assert raw['executionMayStillBeRunning'] is False and raw['orphanProcessIds']==[]
    for kind in ['RemoteControlConfirmed','RemoteV2ControlConfirmed','RemoteV3ControlConfirmed']:
        with pytest.raises(ValidationError):getattr(models,kind).model_validate(raw)


def test_image_catalog_is_conservative_and_local_input_explicit():
    capability=sample('ImageInputCapability')
    assert capability['support']=='unknown'
    assert capability['cliEntry']=='unknown' and capability['runtimeImplemented'] is False and capability['verified'] is False
    assert capability['mimeTypes']==[] and capability['maxBytes']==0
    catalog=sample('RemoteV4CatalogView')
    assert catalog['scenes'][0]['roleImageCapabilities'][0]['imageInput']==capability
    assert catalog['nativeImageCapabilities'][0]['imageInput']==capability
    assert sample('SyncAttachmentItem')['availability']=='pending_upload'
    assert 'localPath' in sample('AgentInputAttachment')


def checker():
    spec=importlib.util.spec_from_file_location('attachment_api_check',P/'remote/api-contract.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_pause_and_auth_matrix_for_uploads_downloads_and_scopes():
    module=checker()
    for method,path in module.ATTACHMENT_OPERATIONS:
        op=API['paths'][path][method.lower()];worker=path.startswith('/api/v2/worker/')
        assert op['security']==[{'workerDevice' if worker else 'remoteSession':[]}]
        if method=='POST':
            module.check_binary_request(op)
            assert ('REMOTE_DEVICE_SUSPENDED' in op['x-error-codes']) is (not worker)
            headers={p['name'] for p in op['parameters'] if p['required']}
            if worker:assert {'X-Worker-Store-Id','X-Sync-Generation','X-Local-Conversation-Id','X-Local-Message-Id','X-Local-Attachment-Id'}<=headers
            else:assert {'X-CSRF-Token','Origin'}<=headers
        if op.get('x-binary-download'):
            assert 'REMOTE_DEVICE_SUSPENDED' not in op['x-error-codes']
            module.check_binary_response(op['responses']['200'])
    assert {v.value for v in models.RemoteApiTokenScope}=={'devices:read','devices:manage','devices:delete'}


@pytest.mark.parametrize('mutation',['inline','sniff','cache','length','hash','json'])
def test_binary_checks_reject_insecure_or_misleading_examples(mutation):
    module=checker()
    if mutation in ['inline','sniff','cache']:
        response=deepcopy(API['paths']['/api/v2/attachments/{attachmentId}/content']['get']['responses']['200'])
        if mutation=='inline':response['headers']['Content-Disposition']['example']='inline'
        if mutation=='sniff':response['headers']['X-Content-Type-Options']['schema']['const']=''
        if mutation=='cache':response['headers']['Cache-Control']['schema']['const']='public'
        with pytest.raises(AssertionError):module.check_binary_response(response)
    else:
        op=deepcopy(API['paths']['/api/v2/conversations/{conversationId}/attachments']['post'])
        if mutation=='length':op['x-request-example']['headers']['Content-Length']=1
        if mutation=='hash':op['x-request-example']['headers']['X-Content-Sha256']='0'*64
        if mutation=='json':op['requestBody']['content']['application/json']={}
        with pytest.raises(AssertionError):module.check_binary_request(op)


def test_local_upload_and_proxy_routes_exist_with_local_auth():
    for file,version,auth in [('local-hub.v1.yaml','v1','bearerAuth'),('local-chat.v2.yaml','v2','localSession')]:
        api=yaml.safe_load((P/'openapi'/file).read_text(encoding='utf-8'))
        prefix='/api/'+version
        for path,method in [('/attachments/limits','get'),('/conversations/{conversationId}/attachments','post'),('/attachments/{attachmentId}','get'),('/attachments/{attachmentId}','delete'),('/attachments/{attachmentId}/content','get'),('/attachments/{attachmentId}/thumbnail','get'),('/conversations/{conversationId}/attachment-capabilities','get')]:
            op=api['paths'][prefix+path][method]
            assert op['security']==[{auth:[]}]
            for r in op['responses'].values():assert r['headers']['Cache-Control']['schema']['const']=='no-store'
