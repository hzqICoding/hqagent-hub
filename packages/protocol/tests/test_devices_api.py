"""0.8 HTTP-only contract conformance; no server/Worker side effects."""
from copy import deepcopy
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import re
import subprocess

import pytest
from pydantic import TypeAdapter, ValidationError
from protocol.generated.python import models
import yaml

P=Path(__file__).resolve().parents[1]
ROOT=P.parents[1]
BASE='ea63a7293db4097d2a0be5084f29bbbd2dc5c8d2'
F=P/'fixtures/contracts'
MANIFEST=json.loads((F/'manifest.json').read_text(encoding='utf-8'))['fixtures']
NEW=json.loads((P/'schema/remote-devices.json').read_text(encoding='utf-8'))['$defs']
API=yaml.safe_load((P/'openapi/remote-hub.v2.yaml').read_text(encoding='utf-8'))


def before(path):
    return subprocess.check_output(['git','show',f'{BASE}:packages/protocol/{path}'],cwd=ROOT).decode('utf-8')


def value(name):
    filename=next(f for f,k in MANIFEST.items() if k==name)
    return json.loads((F/filename).read_text(encoding='utf-8'))


@pytest.mark.parametrize('filename,kind',[(f,k) for f,k in MANIFEST.items() if f.startswith('devices.')])
def test_new_fixtures_round_trip(filename,kind):
    raw=json.loads((F/filename).read_text(encoding='utf-8'))
    adapter=TypeAdapter(getattr(models,kind))
    assert adapter.dump_python(adapter.validate_python(raw),mode='json',by_alias=True,exclude_none=True)==raw


def test_every_new_type_has_fixture_and_version_is_http_minor_only():
    assert set(NEW)<={k for f,k in MANIFEST.items() if f.startswith('devices.')}
    assert models.PROTOCOL_VERSION==API['info']['version']=='0.9.2'
    sync=json.loads((P/'schema/remote-sync.json').read_text(encoding='utf-8'))['$defs']
    assert {d['properties']['wireRevision']['const'] for d in sync.values() if 'wireRevision' in d.get('properties',{})}=={2}


def test_old_fixtures_remain_unchanged_and_validate_in_new_package():
    old=json.loads(before('fixtures/contracts/manifest.json'))['fixtures']
    for file,kind in old.items():
        text=(F/file).read_text(encoding='utf-8')
        assert text==before('fixtures/contracts/'+file)
        raw=json.loads(text);adapter=TypeAdapter(getattr(models,kind))
        assert adapter.dump_python(adapter.validate_python(raw),mode='json',by_alias=True,exclude_none=True)==raw


def test_wire1_is_unchanged_wire2_only_pins_old_error_value_set():
    old=json.loads(before('schema/remote.json'))['$defs']
    current=json.loads((P/'schema/remote.json').read_text(encoding='utf-8'))['$defs']
    # D51 changes these HTTP-only DTOs. Their exact deltas and all old wire
    # transitive closures are independently pinned in test_native_protocol.py.
    r3_http={'RemoteConversationView','RemoteCommandView','RemoteSendMessageInput'}
    for name,d in old.items():
        if name not in {'RemoteDeviceView','RemoteDevicePage'} | r3_http:assert current[name]==d
    sync_old=json.loads(before('schema/remote-sync.json'))
    expected=deepcopy(sync_old)
    for d in expected['$defs'].values():
        if d.get('properties',{}).get('wireRevision',{}).get('const')!=2:continue
        for field,prop in d['properties'].items():
            if prop.get('$ref')=='remote.json#/$defs/RemoteError':
                d['properties'][field]={'$ref':'remote-devices.json#/$defs/RemoteWire2Error'}
            if prop.get('$ref')=='remote.json#/$defs/RemoteApprovalView':
                d['properties'][field]={'$ref':'remote-devices.json#/$defs/RemoteWire2ApprovalView'}
    assert json.loads((P/'schema/remote-sync.json').read_text(encoding='utf-8'))==expected
    codes=[e['code'] for e in yaml.safe_load(before('registry/error-codes.yaml'))['errors']]
    assert NEW['RemoteWire2ErrorCode']['enum']==codes
    for original,frozen,field in [('RemoteError','RemoteWire2Error','code'),('RemoteApprovalView','RemoteWire2ApprovalView','denialCode')]:
        expected=deepcopy(old[original]);expected['properties'][field]={'$ref':'remote-devices.json#/$defs/RemoteWire2ErrorCode'}
        assert NEW[frozen]==expected


@pytest.mark.parametrize('code',['REMOTE_DEVICE_SUSPENDED','REMOTE_API_TOKEN_INVALID','REMOTE_API_TOKEN_EXPIRED','REMOTE_API_TOKEN_SCOPE_INSUFFICIENT','REMOTE_AUTH_AMBIGUOUS'])
def test_http_codes_never_enter_either_worker_error_domain(code):
    for name in ['RemoteWorkerHelloRejected','RemoteV2WorkerHelloRejected']:
        raw=value(name);raw['error']['code']=code
        with pytest.raises(ValidationError):getattr(models,name).model_validate(raw)
    models.RemoteHttpError.model_validate({'code':code,'message':'合成测试','retryable':False})


def test_device_extensions_are_additive_not_transport_status_changes():
    old=json.loads(before('schema/remote.json'))['$defs']['RemoteDeviceView']
    current=json.loads((P/'schema/remote.json').read_text(encoding='utf-8'))['$defs']['RemoteDeviceView']
    assert current['required']==old['required']
    assert current['properties']['status']==old['properties']['status']
    for k,v in old['properties'].items():assert current['properties'][k]==v
    assert set(current['properties'])-set(old['properties'])=={'remoteAccess','displayName','version','suspendedAt'}
    raw=json.loads((F/'devices.device-suspended.json').read_text(encoding='utf-8'))
    assert raw['status']=='online' and raw['remoteAccess']=='suspended'
    assert models.RemoteDeviceView.model_validate(raw).device_name=='Office PC'


@pytest.mark.parametrize('field,bad',[('expectedVersion',True),('expectedVersion',0),('remoteAccess','revoked'),('displayName',None)])
def test_device_patch_structural_limits(field,bad):
    raw=value('RemoteDevicePatchInput');raw[field]=bad
    with pytest.raises(ValidationError):models.RemoteDevicePatchInput.model_validate(raw)


def test_secret_only_first_issuance_and_metadata_rejects_secret_injection():
    issued=value('RemoteApiTokenIssuedView');replay=value('RemoteApiTokenIssueReplayView')
    assert issued['secretAvailable'] is True and replay['secretAvailable'] is False
    assert 'secret' not in replay
    assert re.fullmatch(r'hqr_pat_[0-9a-f]{24}_[A-Za-z0-9_-]{43}',issued['secret'])
    assert issued['secret'].startswith(issued['token']['tokenPrefix']+'_')
    assert (datetime.fromisoformat(issued['token']['expiresAt'])-datetime.fromisoformat(issued['token']['createdAt'])).total_seconds()<=365*86400
    for kind in ['RemoteApiTokenView','RemoteApiTokenPage','RemoteApiTokenIssueReplayView','RemoteApiTokenRevocationView']:
        raw=value(kind);raw['secret']=issued['secret']
        with pytest.raises(ValidationError):getattr(models,kind).model_validate(raw)


@pytest.mark.parametrize('scopes',[[],['devices:*'],['conversations:read'],['devices:read']*4])
def test_pat_scopes_are_bounded_explicit_values(scopes):
    raw=value('RemoteApiTokenCreateInput');raw['scopes']=scopes
    with pytest.raises(ValidationError):models.RemoteApiTokenCreateInput.model_validate(raw)


def test_http_detail_is_safe_and_not_a_worker_field():
    raw=value('RemoteHttpError');raw['detail']['requestBody']={'authorization':'synthetic'}
    with pytest.raises(ValidationError):models.RemoteHttpError.model_validate(raw)
    for kind in ['RemoteWire1Error','RemoteWire2Error','RemoteError']:
        raw=value(kind);raw['detail']={'fields':['name']}
        with pytest.raises(ValidationError):getattr(models,kind).model_validate(raw)


def test_published_spec_examples_are_valid_for_generated_dtos():
    envelope=TypeAdapter(models.ApiEnvelope)
    error=TypeAdapter(models.RemoteHttpError)
    for path,ops in API['paths'].items():
        for method,op in ops.items():
            if 'requestBody' in op:
                media=op['requestBody']['content']['application/json']
                adapter=TypeAdapter(getattr(models,media['schema']['$ref'].split('/')[-1]))
                for sample in media['examples'].values():adapter.validate_python(sample['value'])
            for status,response in op['responses'].items():
                if path=='/api/v2/openapi.json' and status=='200':continue
                media=response['content']['application/json']
                for sample in media['examples'].values():
                    data=sample['value'];envelope.validate_python(data)
                    if data['success']:
                        kind=response['x-dataSchema']['$ref'].split('/')[-1]
                        TypeAdapter(getattr(models,kind)).validate_python(data['data'])
                    else:error.validate_python(data['error'])
                    has_secret=bool(re.search(r'hqr_pat_[0-9a-f]{24}_[A-Za-z0-9_-]{43}',json.dumps(data)))
                    assert has_secret==(path=='/api/v2/api-tokens' and method=='post' and status=='201')


def test_spec_bundle_auth_examples_and_error_table_do_not_drift():
    spec=importlib.util.spec_from_file_location('device_api_contract',P/'remote/api-contract.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    registry=yaml.safe_load((P/'registry/error-codes.yaml').read_text(encoding='utf-8'))['errors']
    guidance=yaml.safe_load((P/'remote/http-error-guidance.yaml').read_text(encoding='utf-8'))['errors']
    bundle=module.bundled(API,registry)
    runtime_count,total=module.check(API,registry,guidance,bundle)
    assert total==39 and runtime_count==39  # All six R3 routes are now implemented in integration.
    assert bundle==json.loads((P/'openapi/remote-hub.v2.bundle.json').read_text(encoding='utf-8'))
    guide=(P/'remote/api-guide.md').read_text(encoding='utf-8')
    for name,block in module.table_blocks(API,registry,guidance).items():
        assert f'<!-- BEGIN {name} -->\n{block}\n<!-- END {name} -->' in guide
    missing=deepcopy(API);missing['paths'].pop('/api/v2/openapi.json')
    with pytest.raises(AssertionError):module.check(missing,registry,guidance,bundle)
    wrong_auth=deepcopy(API);wrong_auth['paths']['/api/v2/api-tokens']['get']['security']=[{'personalAccessToken':[]}]
    with pytest.raises(AssertionError):module.check(wrong_auth,registry,guidance,bundle)
    for path,ops in bundle['paths'].items():
        for op in ops.values():
            for status,response in op['responses'].items():
                if path=='/api/v2/openapi.json' and status=='200':continue
                branch=response['content']['application/json']['schema']['allOf'][1]
                forbidden='error' if branch['properties']['success']['const'] else 'data'
                assert branch['properties'][forbidden] is False


@pytest.mark.parametrize('mutation',['offline','control_sequence','long_deadline','device_state','unsafe_approval','expired_snapshot'])
def test_http_example_semantic_regressions_are_rejected(mutation):
    spec=importlib.util.spec_from_file_location('api_example_audit',P/'remote/api-contract.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    bad=deepcopy(API)
    def example(path,method,status):
        return bad['paths'][path][method]['responses'][status]['content']['application/json']['examples']['success']['value']['data']
    if mutation=='offline':
        example('/api/v2/conversations','post','202')['deliveryState']='queued_offline'
    elif mutation=='control_sequence':
        example('/api/v2/runs/{runId}/commands','post','202')['conversationSeq']=2
    elif mutation=='long_deadline':
        example('/api/v2/conversations','post','202')['expiresAt']='2026-09-26T12:05:00Z'
    elif mutation=='device_state':
        example('/api/v2/devices/{workerId}','patch','200')['remoteAccess']='enabled'
    elif mutation=='unsafe_approval':
        op=bad['paths']['/api/v2/approvals/{approvalId}/decisions']['post']
        op['requestBody']['content']['application/json']['examples']['request']['value']['decision']='approve'
        op['x-request-example']['body']['decision']='approve'
    else:
        example('/api/v2/conversations/{conversationId}/snapshot','get','200')['approvals'][0]['expiresAt']='2026-09-26T11:00:00Z'
    with pytest.raises(AssertionError):module.check_example_semantics(bad)
