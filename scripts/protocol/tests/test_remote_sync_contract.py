"""Live 0.7.0 conformance. Historical release-shape tests stay pinned to their releases."""
from copy import deepcopy
from datetime import datetime
from itertools import permutations
import hashlib
import json
from pathlib import Path
import subprocess

import pytest
import yaml
from pydantic import TypeAdapter, ValidationError
from protocol.generated.python import models

ROOT = Path(__file__).resolve().parents[3]
P = ROOT / 'packages/protocol'
F = P / 'fixtures/contracts'
BASE = '8d2058f43f7bd94028b4d3fd1fd2bac65e6b1992'
REMOTE = json.loads((P / 'schema/remote.json').read_text(encoding='utf-8'))['$defs']
SYNC = json.loads((P / 'schema/remote-sync.json').read_text(encoding='utf-8'))['$defs']
MANIFEST = json.loads((F / 'manifest.json').read_text(encoding='utf-8'))['fixtures']
CASES = [(file, name) for file, name in MANIFEST.items() if file.startswith('r15.')]

def before(path):
    return subprocess.check_output(['git', 'show', f'{BASE}:packages/protocol/{path}'], cwd=ROOT).decode('utf-8')

def fixture(name):
    file = next(file for file, kind in MANIFEST.items() if kind == name)
    return json.loads((F / file).read_text(encoding='utf-8'))

@pytest.mark.parametrize('file,name', CASES)
def test_all_new_fixtures_generated_round_trip_and_frame_byte_limit(file, name):
    raw = json.loads((F / file).read_text(encoding='utf-8'))
    adapter = TypeAdapter(getattr(models, name))
    parsed = adapter.validate_python(raw)
    assert adapter.dump_python(parsed, mode='json', by_alias=True, exclude_none=True) == raw
    if isinstance(raw, dict) and 'wireRevision' in raw:
        assert len(json.dumps(raw, ensure_ascii=False).encode('utf-8')) <= 262144

def test_new_type_fixture_coverage_and_version():
    assert set(SYNC) == {name for _, name in CASES}
    assert models.PROTOCOL_VERSION == (P / 'VERSION').read_text().strip() == '0.7.0'

def test_revision_one_shapes_are_exact_except_approved_error_reference_freeze():
    old = json.loads(before('schema/remote.json'))['$defs']
    frames = [name for name, d in old.items() if 'wireRevision' in d.get('properties', {})]
    assert len(frames) == 27
    for name in frames:
        expected = deepcopy(old[name])
        for field, value in expected['properties'].items():
            if value.get('$ref') == 'remote.json#/$defs/RemoteError':
                expected['properties'][field] = {'$ref': 'remote-sync.json#/$defs/RemoteWire1Error'}
            if value.get('$ref') == 'remote.json#/$defs/RemoteApprovalView':
                expected['properties'][field] = {'$ref': 'remote-sync.json#/$defs/RemoteWire1ApprovalView'}
        assert REMOTE[name] == expected
        v2 = SYNC['RemoteV2' + name.removeprefix('Remote')]
        assert v2['properties']['wireRevision'] == v2['properties']['wireRevision'] | {'type': 'integer', 'const': 2}
    old_codes = [e['code'] for e in yaml.safe_load(before('registry/error-codes.yaml'))['errors']]
    assert SYNC['RemoteWire1ErrorCode']['enum'] == old_codes
    for old_name, new_name, code_field in [('RemoteError', 'RemoteWire1Error', 'code'), ('RemoteApprovalView', 'RemoteWire1ApprovalView', 'denialCode')]:
        expected = deepcopy(old[old_name])
        expected['properties'][code_field] = {'$ref': 'remote-sync.json#/$defs/RemoteWire1ErrorCode'}
        assert SYNC[new_name] == expected
    assert REMOTE['RemoteConversationSnapshot'] == old['RemoteConversationSnapshot']

def test_all_legacy_fixtures_are_byte_equivalent_as_text_and_still_validate():
    old_manifest = json.loads(before('fixtures/contracts/manifest.json'))['fixtures']
    for file, name in old_manifest.items():
        text = (F / file).read_text(encoding='utf-8')
        assert text == before('fixtures/contracts/' + file)
        raw = json.loads(text)
        assert getattr(models, name).model_validate(raw).model_dump(mode='json', by_alias=True, exclude_none=True) == raw

@pytest.mark.parametrize('name,field', [('RemoteWorkerHelloRejected','error'), ('RemoteCommandFailed','error'), ('RemoteApprovalEvent','payload')])
def test_new_error_codes_are_rejected_on_v1_but_accepted_on_v2(name, field):
    raw = fixture(name)
    key = 'denialCode' if field == 'payload' else 'code'
    raw[field][key] = 'REMOTE_CONVERSATION_BUSY'
    with pytest.raises(ValidationError):
        getattr(models, name).model_validate(raw)
    upgraded = fixture('RemoteV2' + name.removeprefix('Remote'))
    upgraded[field][key] = 'REMOTE_CONVERSATION_BUSY'
    getattr(models, 'RemoteV2' + name.removeprefix('Remote')).model_validate(upgraded)
    models.RemoteError.model_validate({'code':'REMOTE_CONVERSATION_BUSY','message':'busy','retryable':True})

@pytest.mark.parametrize('revision', [True, 1.0, '2', 1, 3])
def test_v2_is_strict_and_does_not_accept_other_revision_values(revision):
    value = fixture('RemoteV2WorkerHello')
    value['wireRevision'] = revision
    with pytest.raises(ValidationError):
        models.RemoteV2WorkerOutboundFrame.model_validate(value)

def test_v1_rejects_v2_and_handshake_advertises_both_without_package_equality():
    raw = fixture('RemoteV2WorkerHello')
    raw['protocolVersion'] = '0.8.0'
    models.RemoteV2WorkerOutboundFrame.model_validate(raw)
    with pytest.raises(ValidationError):
        models.RemoteWorkerOutboundFrame.model_validate(raw)
    assert fixture('RemoteV2WorkerHelloRejected')['supportedWireRevisions'] == [1, 2]

@pytest.mark.parametrize('name', [n for n, d in SYNC.items() if n.endswith('Command') and 'commandId' in d.get('properties',{})])
def test_each_command_has_30_second_delivery_boundary_and_local_target(name):
    raw = fixture(name)
    assert (datetime.fromisoformat(raw['deliverBy']) - datetime.fromisoformat(raw['createdAt'])).total_seconds() == 30
    assert ('conversationSeq' in raw) == (raw['type'] == 'run.submit')
    for field in ['deliverBy', 'localConversationId']:
        invalid = deepcopy(raw); invalid.pop(field)
        with pytest.raises(ValidationError):
            getattr(models, name).model_validate(invalid)
    models.RemoteV2CommandEnvelope.model_validate(raw)

def test_full_unicode_message_can_be_split_without_truncation():
    text = '差分🙂\n' * 12000
    pieces = [text[i:i+16000] for i in range(0,len(text),16000)]
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    raw = fixture('RemoteSyncMessageSegment')
    parsed = []
    for index, part in enumerate(pieces):
        value = dict(raw, text=part, segmentIndex=index, segmentCount=len(pieces), totalUtf8Bytes=len(text.encode('utf-8')), contentSha256=digest)
        parsed.append(models.RemoteSyncMessageSegment.model_validate(value).text)
    assert ''.join(parsed) == text and len(text) > 32000
    message = fixture('RemoteMessageView'); message['text'] = text
    assert models.RemoteMessageView.model_validate(message).text == text
    raw['text'] = 'x' * 16001
    with pytest.raises(ValidationError): models.RemoteSyncMessageSegment.model_validate(raw)

def test_busy_snapshot_supports_empty_set_and_bounded_complete_parts():
    raw = fixture('RemoteV2BusySnapshot')
    raw['conversationIds'] = []
    models.RemoteV2WorkerOutboundFrame.model_validate(raw)
    raw['conversationIds'] = [f'c{i}' for i in range(101)]
    with pytest.raises(ValidationError): models.RemoteV2BusySnapshot.model_validate(raw)
    for i in range(2):
        raw.update(partIndex=i, partCount=2, conversationIds=[f'c{i}'])
        models.RemoteV2BusySnapshot.model_validate(raw)
    raw.pop('connectionId')
    with pytest.raises(ValidationError): models.RemoteV2BusySnapshot.model_validate(raw)

def test_sync_events_have_persistent_sequence_and_generation_reset_boundary():
    for name in ['RemoteV2ConversationUpserted','RemoteV2MessageSegment','RemoteV2SyncedRunState','RemoteV2ConversationDeleted','RemoteV2SyncReset','RemoteV2BackfillProgress']:
        raw = fixture(name)
        assert {'workerStoreId','workerEpoch','eventId','seq','syncGeneration'} <= raw.keys()
        raw['seq'] = 0
        with pytest.raises(ValidationError): getattr(models,name).model_validate(raw)

def test_redaction_covers_only_deleted_content_not_execution_facts():
    raw = fixture('RemoteV2ContentRedaction')
    assert 'seq' not in raw and raw['slots'][0]['seq'] < raw['deletionSeq']
    models.RemoteV2WorkerOutboundFrame.model_validate(raw)
    for kind in ['command.accepted','command.received','command.completed','command.control_result','command.delivery_granted','sync.busy.snapshot']:
        bad=deepcopy(raw); bad['slots'][0]['originalType']=kind
        with pytest.raises(ValidationError): models.RemoteV2ContentRedaction.model_validate(bad)
    bad=deepcopy(raw);bad['slots']*=101
    with pytest.raises(ValidationError): models.RemoteV2ContentRedaction.model_validate(bad)

def test_frozen_scalar_boundary_api_preserves_enum_wire_shape():
    value=models.RemoteWire1ErrorCode.model_validate('REMOTE_PROTOCOL_UNSUPPORTED')
    assert value.model_dump(mode='json',by_alias=True,exclude_none=True)=='REMOTE_PROTOCOL_UNSUPPORTED'
    with pytest.raises(ValidationError): models.RemoteWire1ErrorCode.model_validate('REMOTE_CONVERSATION_BUSY')

def test_local_settings_auth_and_visibility_recovery_routes():
    for suffix, auth in [('v1','bearerAuth'),('v2','localSession')]:
        file = 'local-hub.v1.yaml' if suffix == 'v1' else 'local-chat.v2.yaml'
        api = yaml.safe_load((P/'openapi'/file).read_text(encoding='utf-8'))
        ops = api['paths'][f'/api/{suffix}/remote/sync-settings']
        for method in ['get','put']:
            assert ops[method]['security'] == [{auth:[]}]
            assert ops[method]['responses']['200']['x-dataSchema']['$ref'].endswith('/RemoteSyncSettingsView')
        assert any(p['name']=='Idempotency-Key' and p['required'] for p in ops['put']['parameters'])
        listing=api['paths'][f'/api/{suffix}/conversations']['get']
        assert any(p['name']=='includeHidden' and p['schema']['default'] is False for p in listing['parameters'])
        update=api['paths'][f'/api/{suffix}/conversations/{{conversationId}}']['patch']
        assert update['security']==[{auth:[]}]
    assert fixture('RemoteSyncSettingsView')['mirrorEnabled'] is True
    data=fixture('LocalConversationView') if 'LocalConversationView' in MANIFEST.values() else None
    if data:
        for visibility in ['both','pc_only','mobile_only']:
            models.LocalConversationView.model_validate(dict(data,visibility=visibility,busy=False))

def test_browser_routes_reference_real_types_and_worker_owned_writes():
    api=yaml.safe_load((P/'openapi/remote-hub.v2.yaml').read_text(encoding='utf-8'))
    assert '202' in api['paths']['/api/v2/conversations']['post']['responses']
    assert '201' not in api['paths']['/api/v2/conversations']['post']['responses']
    assert 'patch' in api['paths']['/api/v2/conversations/{conversationId}']
    params=api['paths']['/api/v2/conversations']['get']['parameters']
    assert {'workerId','workspaceId'} <= {p['name'] for p in params}
    get=api['paths']['/api/v2/conversations/{conversationId}/messages']['get']
    assert 'before' in {p['name'] for p in get['parameters']}
    assert get['responses']['200']['x-dataSchema']['$ref'].endswith('/RemoteSyncMessagePage')
    def walk(node):
        if isinstance(node,dict):
            if '$ref' in node and node['$ref'].startswith('../schema/'):
                file, pointer=node['$ref'].split('#')
                target=json.loads((P/'openapi'/file).read_text(encoding='utf-8'))
                for part in pointer.strip('/').split('/'): target=target[part]
            for value in node.values(): walk(value)
        elif isinstance(node,list):
            for value in node: walk(value)
    walk(api)

def test_delivery_reference_state_machine_never_executes_after_server_timeout_failure():
    # Normative protocol trace model, not an assertion that P1/P2 already implement the gate.
    # All interleavings include delayed receipts, grant delivery, expiry, and unrelated ACK.
    for order in permutations(['received','decide','grant_arrives','timeout','ack']):
        received=False; granted=False; failed=False; executed=False; expired=False
        for event in order:
            if event=='received': received=True
            elif event=='decide' and received and not expired and not failed: granted=True
            elif event=='grant_arrives' and granted and not expired: executed=True
            elif event=='timeout':
                expired=True
                if not granted: failed=True
            # ACK has no transition granting execution, including after an expired receipt.
            assert not (failed and executed)
    assert fixture('RemoteV2DeliveryGrant')['commandDigest'] == fixture('RemoteV2CommandReceived')['commandDigest']
    assert 'command.received' != fixture('RemoteV2CommandAccepted')['type']
