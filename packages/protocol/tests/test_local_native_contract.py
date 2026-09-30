"""0.9.1 local native aliases; synthetic contract tests, no native sessions read."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest
from pydantic import ValidationError
import yaml
from protocol.generated.python import models

P=Path(__file__).resolve().parents[1]
BASE='9dbb3f2'


def load(file):
    return yaml.safe_load((P/file).read_text(encoding='utf-8'))


def operations(file,version):
    return {path.removeprefix('/api/'+version):value for path,value in load('openapi/'+file)['paths'].items()
            if path.startswith('/api/'+version+'/native-sessions')}


def test_local_aliases_have_identical_dtos_and_no_remote_receipts():
    v1=operations('local-hub.v1.yaml','v1');v2=operations('local-chat.v2.yaml','v2')
    expected={'/native-sessions','/native-sessions/{nativeSessionId}',
              '/native-sessions/{nativeSessionId}/messages','/native-sessions/{nativeSessionId}/imports'}
    assert set(v1)==set(v2)==expected
    for path in expected:
        method='post' if path.endswith('/imports') else 'get'
        assert set(v1[path])==set(v2[path])=={method}
        a=deepcopy(v1[path][method]);b=deepcopy(v2[path][method])
        assert a.pop('security')==[{'bearerAuth':[]}]
        assert b.pop('security')==[{'localSession':[]}]
        assert a.pop('operationId').removesuffix('V1')==b.pop('operationId').removesuffix('V2')
        assert a==b
        assert '202' not in a['responses']
        assert 'REMOTE_DEVICE_OFFLINE' not in a['x-error-codes']
        assert 'REMOTE_REVISION_REQUIRED' not in a['x-error-codes']
        for response in a['responses'].values():
            assert response['headers']['Cache-Control']['schema']['const']=='no-store'
        success=a['responses']['201' if method=='post' else '200']
        name=success['x-dataSchema']['$ref'].split('/')[-1]
        data=success['content']['application/json']['example']['data']
        getattr(models,name).model_validate(data)
        if method=='post':
            assert name=='LocalConversationView' and data['conversationKind']=='native'
            assert 'sceneId' not in data
            assert {'Origin','Idempotency-Key'} <= {p['name'] for p in a['parameters'] if p['required']}
            body=a['requestBody']['content']['application/json']
            assert body['schema']['$ref'].endswith('/RemoteNativeImportInput')
            models.RemoteNativeImportInput.model_validate(body['example'])


def test_filters_read_input_and_local_page_fixture():
    ops=operations('local-chat.v2.yaml','v2')
    params={p['name']:p for p in ops['/native-sessions']['get']['parameters']}
    assert set(params)=={'workspaceId','agentType','cursor','limit'}
    assert params['limit']['schema']=={'type':'integer','minimum':1,'maximum':100,'default':50}
    read=ops['/native-sessions/{nativeSessionId}/messages']['get']
    assert {p['name'] for p in read['parameters']}=={'nativeSessionId','sourceRevision','before','limit'}
    assert read['responses']['200']['x-dataSchema']['$ref'].endswith('/NativeMessagePage')
    raw=json.loads((P/'fixtures/contracts/local-native.page.json').read_text(encoding='utf-8'))
    parsed=models.LocalNativeSessionPage.model_validate(raw)
    assert parsed.model_dump(mode='json',by_alias=True,exclude_none=True)==raw
    raw['workerId']='fake_cloud_identity'
    with pytest.raises(ValidationError):models.LocalNativeSessionPage.model_validate(raw)


def test_patch_changes_no_existing_wire_schema_or_fixture():
    for file in ['remote.json','remote-sync.json','remote-native.json','remote-devices.json']:
        relative='schema/'+file
        old=subprocess.check_output(['git','show',f'{BASE}:packages/protocol/{relative}'],cwd=P).decode('utf-8')
        # This assertion audits the 0.9.1 patch release, not all later HTTP extensions.
        released=subprocess.check_output(['git','show',f'271c904:packages/protocol/{relative}'],cwd=P).decode('utf-8')
        assert released==old
        # Current frozen wire closures are checked by test_attachment_contract.py.
    assert models.PROTOCOL_VERSION==(P/'VERSION').read_text().strip()=='0.10.0'
    manifest=load('fixtures/contracts/manifest.json')['fixtures']
    assert manifest['local-native.page.json']=='LocalNativeSessionPage'
    assert set(load('schema/local-native.json')['$defs'])=={'LocalNativeSessionPage'}
