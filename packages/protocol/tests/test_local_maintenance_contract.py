"""Pure contract tests. Never import or invoke runtime image verification."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import subprocess

import pytest
from pydantic import TypeAdapter, ValidationError
import yaml
from protocol.generated.python import models

P=Path(__file__).resolve().parents[1]
F=P/'fixtures/contracts'
M=json.loads((F/'manifest.json').read_text(encoding='utf-8'))['fixtures']
DEFS=json.loads((P/'schema/local-maintenance.json').read_text(encoding='utf-8'))['$defs']
BASE='b9b32b19104f2c18ec42ca5b479ff741a7b71ee9'


def load(file):return yaml.safe_load((P/file).read_text(encoding='utf-8'))
def fixture(name):return json.loads((F/('maintenance.'+name+'.json')).read_text(encoding='utf-8'))


@lru_cache(None)
def old_defs(file):
    return json.loads(subprocess.check_output(['git','show',f'{BASE}:packages/protocol/schema/{file}'],cwd=P).decode('utf-8'))['$defs']


def references(node):
    if isinstance(node,dict):
        if '$ref' in node:yield node['$ref']
        for child in node.values():yield from references(child)
    elif isinstance(node,list):
        for child in node:yield from references(child)


@pytest.mark.parametrize('file,kind',[(f,k) for f,k in M.items() if f.startswith('maintenance.')])
def test_synthetic_maintenance_fixtures_round_trip(file,kind):
    raw=json.loads((F/file).read_text(encoding='utf-8'));adapter=TypeAdapter(getattr(models,kind))
    assert adapter.dump_python(adapter.validate_python(raw),mode='json',by_alias=True,exclude_none=True)==raw


def test_complete_coverage_and_no_wire_schema_changes():
    assert set(DEFS)=={k for f,k in M.items() if f.startswith('maintenance.')}
    assert models.PROTOCOL_VERSION==(P/'VERSION').read_text().strip()=='0.10.1'
    current={f.name:json.loads(f.read_text(encoding='utf-8'))['$defs'] for f in (P/'schema').glob('*.json')}
    pending=[('remote.json','RemoteWorkerOutboundFrame'),('remote.json','RemoteServerOutboundFrame')]
    for revision,file in [(2,'remote-sync.json'),(3,'remote-native.json'),(4,'remote-attachments.json')]:
        pending.extend((file,f'RemoteV{revision}{side}OutboundFrame') for side in ['Worker','Server'])
    seen=set()
    while pending:
        file,name=pending.pop()
        if (file,name) in seen:continue
        seen.add((file,name));old=old_defs(file)[name]
        assert current[file][name]==old,(file,name)
        for reference in references(old):
            target,pointer=reference.split('#',1)
            pending.append((target or file,pointer.split('/')[-1]))
    cloud=load('openapi/remote-hub.v2.yaml')
    assert set(cloud['x-worker-websocket']['revisions'])=={1,2,3,4}
    assert not any('image-verification' in path for path in cloud['paths'])
    assert 'delete' not in cloud['paths']['/api/v2/conversations/{conversationId}']
    assert len([op for item in cloud['paths'].values() for method,op in item.items() if method in {'get','post','put','patch','delete'}])==47


@pytest.mark.parametrize('ack',[None,False,'true',1])
def test_paid_job_requires_explicit_true_boolean(ack):
    raw=fixture('StartLocalImageVerificationInput')
    if ack is None:raw.pop('acknowledgeModelUsage')
    else:raw['acknowledgeModelUsage']=ack
    with pytest.raises(ValidationError):models.StartLocalImageVerificationInput.model_validate(raw)


@pytest.mark.parametrize('field',['raw','message','prompt','output','path','commandLine','modelResponse'])
def test_diagnostics_reject_unfiltered_vendor_content(field):
    raw=fixture('LocalImageProbeDiagnostic');raw[field]='synthetic private data'
    with pytest.raises(ValidationError):models.LocalImageProbeDiagnostic.model_validate(raw)
    raw={'unknown.path.stage':fixture('LocalImageProbeDiagnostic')}
    with pytest.raises(ValidationError):models.LocalImageVerificationDiagnostics.model_validate(raw)


def test_default_model_stale_success_and_uncertain_cleanup_are_distinct():
    default=fixture('default-model');assert 'modelId' not in default['target']
    models.LocalImageVerificationState.model_validate(default)
    stale=fixture('stale-version')
    assert stale['lastRecord']['passed'] is True and stale['passed'] is False and stale['invalidated'] is True
    assert stale['target']['cliVersion']!=stale['lastRecord']['target']['cliVersion']
    interrupted=fixture('interrupted-job')
    assert interrupted['slotHeld'] is True and interrupted['cleanupState']=='unconfirmed' and interrupted['executionMayStillBeRunning'] is True
    bad=fixture('StartLocalImageVerificationInput');bad['modelId']='C:/private/key'
    with pytest.raises(ValidationError):models.StartLocalImageVerificationInput.model_validate(bad)
    bad=fixture('CancelLocalImageVerificationInput');bad['force']=True
    with pytest.raises(ValidationError):models.CancelLocalImageVerificationInput.model_validate(bad)


def operations(file,ver):
    api=load('openapi/'+file)
    routes={}
    for path,item in api['paths'].items():
        for method,op in item.items():
            if 'image-verification' in path or (path==f'/api/{ver}/conversations/{{conversationId}}' and method=='delete'):
                routes[(path.removeprefix('/api/'+ver),method)]=op
    return routes


def test_local_aliases_auth_cas_cost_and_safe_examples():
    v1=operations('local-hub.v1.yaml','v1');v2=operations('local-chat.v2.yaml','v2')
    assert len(v1)==len(v2)==5 and v1.keys()==v2.keys()
    for key,a0 in v1.items():
        a=deepcopy(a0);b=deepcopy(v2[key])
        assert a.pop('security')==[{'bearerAuth':[]}]
        assert b.pop('security')==[{'localSession':[]}]
        assert a.pop('operationId').removesuffix('V1')==b.pop('operationId').removesuffix('V2')
        assert a==b
        if key[1] in {'post','delete'}:
            headers={p['name'] for p in a['parameters'] if p['in']=='header' and p['required']}
            assert {'Origin','Idempotency-Key'} <= headers
        if key[1]=='delete':
            cas=next(p for p in a['parameters'] if p['name']=='expectedVersion')
            assert cas['in']=='query' and cas['required'] and cas['schema']['minimum']==1
            assert '200' in a['responses'] and '202' not in a['responses']
        if 'requestBody' in a:
            body=a['requestBody']['content']['application/json']
            getattr(models,body['schema']['$ref'].split('/')[-1]).model_validate(body['example'])
        for status,response in a['responses'].items():
            assert response['headers']['Cache-Control']['schema']['const']=='no-store'
            for ex in response['content']['application/json']['examples'].values():
                envelope=ex['value'];assert envelope['requestId']==response['headers']['X-Request-Id']['example']
                models.ApiEnvelope.model_validate(envelope)
                if status.startswith('2'):
                    getattr(models,response['x-dataSchema']['$ref'].split('/')[-1]).model_validate(envelope['data'])
                elif envelope['error']['code']=='CONFLICT':models.LocalMaintenanceConflictError.model_validate(envelope['error'])


def test_all_five_probes_are_required_not_a_partial_pass():
    raw=fixture('LocalImageProbeResults')
    assert set(raw)=={'new','resume','mixedFive','cancel','error'}
    for key in raw:
        missing=deepcopy(raw);missing.pop(key)
        with pytest.raises(ValidationError):models.LocalImageProbeResults.model_validate(missing)
