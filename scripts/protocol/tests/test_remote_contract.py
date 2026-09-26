"""R1 wire/generator conformance; no services, sockets or model calls."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from protocol.generated.python import models

ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = ROOT / 'packages/protocol'
REMOTE = json.loads((PROTOCOL / 'schema/remote.json').read_text(encoding='utf-8'))['$defs']
MANIFEST = json.loads((PROTOCOL / 'fixtures/contracts/manifest.json').read_text(encoding='utf-8'))['fixtures']
CASES = [(file, name) for file, name in MANIFEST.items() if file.startswith('remote.')]


def load(name):
    spec = importlib.util.spec_from_file_location('protocol_' + name, ROOT / 'scripts/protocol' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load('validate')
generator = load('generate')


def fixture(name):
    file = next(file for file, kind in CASES if kind == name)
    return json.loads((PROTOCOL / 'fixtures/contracts' / file).read_text(encoding='utf-8'))


@pytest.mark.parametrize('file,name', CASES)
def test_each_remote_fixture_schema_generated_round_trip(file, name):
    value = json.loads((PROTOCOL / 'fixtures/contracts' / file).read_text(encoding='utf-8'))
    index, registries = validator.load_index()
    validator.errors.clear()
    validator.validate_value(value, index[name], index, registries, file)
    assert validator.errors == []
    parsed = getattr(models, name).model_validate(value)
    assert parsed.model_dump(mode='json', by_alias=True, exclude_none=True) == value


def test_coverage_and_identity_decisions():
    assert set(REMOTE) <= {kind for _, kind in CASES}
    forbidden = {'attemptId', 'retryOfRunId', 'taskId', 'ownerId', 'userId', 'accountId', 'tenantId',
                 'apiKey', 'api_key', 'modelCredentials', 'authProfileRef', 'deviceSecret', 'deviceCredential'}
    for definition in REMOTE.values():
        assert not forbidden.intersection(definition.get('properties', {}))
    assert 'executionTaskId' in REMOTE['RemoteResultRef']['properties']
    common = json.loads((PROTOCOL / 'schema/common.json').read_text(encoding='utf-8'))['$defs']
    assert common['TaskStatus']['enum'] == ['draft','queued','running','waiting_approval','paused','succeeded','failed','cancelled','unknown']
    assert common['NodeStatus']['enum'] == ['pending','resolving','running','waiting_approval','succeeded','failed','skipped','cancelled']
    local = json.loads((PROTOCOL / 'schema/local-chat.json').read_text(encoding='utf-8'))['$defs']
    assert local['LocalRunView']['properties']['status']['$ref'] == 'common.json#/$defs/TaskStatus'
    assert 'taskId' in local['LocalRunView']['properties']


@pytest.mark.parametrize('kind', ['RemotePauseCommand','RemoteResumeCommand','RemoteCancelCommand','RemoteRetryCommand','RemoteApprovalDecisionCommand','RemoteCommandWithdrawalCommand'])
def test_controls_never_allocate_an_execution_sequence(kind):
    value = fixture(kind)
    assert 'conversationSeq' not in value
    value['conversationSeq'] = 2
    with pytest.raises(ValidationError):
        models.RemoteCommandEnvelope.model_validate(value)


@pytest.mark.parametrize('kind,field,value', [
    ('RemoteRunSubmitCommand','conversationSeq',True),
    ('RemoteRunSubmitCommand','conversationSeq',0),
    ('RemoteRunSubmitCommand','conversationSeq',9007199254740992),
    ('RemoteWorkerHello','workerId',None),
    ('RemoteWorkerHello','workerId',''),
    ('RemoteWorkerHello','ownerId','another-owner'),
    ('RemotePairingChallenge','deviceSecret','never-expose'),
    ('RemoteResultRef','attemptId','invented'),
    ('RemoteResultRef','retryOfRunId','invented'),
    ('RemoteResultRef','taskId','ambiguous'),
    ('RemoteControlUnconfirmed','executionMayStillBeRunning',False),
    ('RemoteControlConfirmed','orphanProcessIds',[123]),
    ('RemoteControlUnconfirmed','orphanProcessIds',['123']),
    ('RemoteControlUnconfirmed','orphanProcessIds',[True]),
    ('RemoteAnonymousSession','authenticated',0),
    ('RemoteRunView','status','recovery_required'),
    ('RemoteRunView','status','cancel_requested'),
])
def test_invalid_wire_values_are_rejected(kind, field, value):
    raw = fixture(kind)
    raw[field] = value
    with pytest.raises(ValidationError):
        getattr(models, kind).model_validate(raw)


def test_control_states_and_execution_state_are_distinct():
    raw = fixture('RemoteControlObserved')
    assert raw['controlResult']['outcome'] == 'unconfirmed'
    assert raw['executionStatus'] == 'paused'
    assert models.RemoteControlObserved.model_validate(raw).execution_status == models.TaskStatus.PAUSED
    raw = fixture('RemoteCommandCompleted')
    raw['controlResult'] = fixture('RemoteControlUnconfirmed')
    with pytest.raises(ValidationError):
        models.RemoteCommandCompleted.model_validate(raw)


def test_null_ack_is_required_and_survives_exclude_none():
    raw = fixture('RemoteWorkerHello')
    assert raw['lastServerAck'] is None
    assert models.RemoteWorkerHello.model_validate(raw).model_dump(mode='json', by_alias=True, exclude_none=True)['lastServerAck'] is None
    del raw['lastServerAck']
    with pytest.raises(ValidationError):
        models.RemoteWorkerHello.model_validate(raw)


def test_private_sequence_coverage_cannot_reach_browser():
    tombstone = fixture('RemoteOmittedEvents')
    models.RemoteWorkerOutboundFrame.model_validate(tombstone)
    browser = fixture('RemoteBrowserWorkerEvent')
    browser['payload'] = tombstone
    with pytest.raises(ValidationError):
        models.RemoteBrowserWorkerEvent.model_validate(browser)


def test_withdrawal_before_original_has_target_order_without_new_sequence():
    value = fixture('RemoteCommandWithdrawalCommand')
    assert 'conversationSeq' not in value
    assert value['payload']['targetConversationSeq'] >= 1
    del value['payload']['targetConversationSeq']
    with pytest.raises(ValidationError):
        models.RemoteCommandWithdrawalCommand.model_validate(value)


def test_discriminated_root_has_legacy_validation_interface():
    value = fixture('RemoteCancelCommand')
    parsed = models.RemoteServerOutboundFrame.model_validate(value)
    assert parsed.root.type == 'run.cancel'
    assert parsed.model_dump(mode='json', by_alias=True, exclude_none=True) == value


def test_rest_scope_and_references():
    api = yaml.safe_load((PROTOCOL / 'openapi/remote-hub.v2.yaml').read_text(encoding='utf-8'))
    index, _ = validator.load_index()
    for path, methods in api['paths'].items():
        for method, operation in methods.items():
            params = {p['name'] for p in operation.get('parameters', [])}
            assert not params.intersection({'ownerId','userId','accountId','tenantId','token'})
            if method != 'get':
                assert 'Idempotency-Key' in params
                if operation.get('security') == [{'remoteSession': []}]:
                    assert 'X-CSRF-Token' in params
    def refs(node):
        if isinstance(node,dict):
            if '$ref' in node:
                assert node['$ref'].split('/')[-1] in index
            for child in node.values():refs(child)
        elif isinstance(node,list):
            for child in node:refs(child)
    refs(api)
    assert api['x-worker-websocket']['security'] == [{'workerDevice': []}]
    assert api['x-worker-websocket']['maxFrameBytes'] == 262144
    # An account password input is never a response or a reachable nested response type.
    def reachable(name):
        found = {name}
        for dep in generator.deps_of({'properties': REMOTE.get(name,{}).get('properties',{}),
                                       'oneOf':REMOTE.get(name,{}).get('oneOf',[])}):
            if dep in REMOTE:found |= reachable(dep)
        return found
    for methods in api['paths'].values():
        for op in methods.values():
            for response in op['responses'].values():
                data = response.get('x-dataSchema',{})
                if '$ref' in data:
                    assert 'RemoteLoginInput' not in reachable(data['$ref'].split('/')[-1])


def test_union_generator_does_not_silently_emit_empty_go_type():
    index = generator.load_schemas()
    index['RemoteCommandEnvelope']['def']['x-go'] = True
    with pytest.raises(SystemExit, match='oneOf'):
        generator.emit_go(index, generator.load_registries(), '0.6.0')


def test_oneof_and_bounds_validator_rejects_bad_shape():
    index, registries = validator.load_index()
    raw = fixture('RemoteRunSubmitCommand')
    raw['payload']['text'] = 'x' * 32001
    validator.errors.clear()
    validator.validate_value(raw,index['RemoteCommandEnvelope'],index,registries,'negative')
    assert validator.errors
    validator.errors.clear()
    validator.validate_value([],{'type':'array','items':{'type':'integer'},'minItems':1},index,registries,'negative')
    assert validator.errors
    malformed = {'oneOf':[{'type':'object','properties':{},'additionalProperties':False},{'type':'null'}]}
    validator.errors.clear()
    validator.check_structure({'Unsupported':malformed},registries)
    assert validator.errors


def test_withdrawal_observation_does_not_fabricate_run_identity():
    raw = fixture('RemoteControlObserved')
    raw.pop('resultRef')
    raw.pop('executionStatus')
    parsed = models.RemoteControlObserved.model_validate(raw)
    dumped = parsed.model_dump(mode='json', by_alias=True, exclude_none=True)
    assert 'resultRef' not in dumped and 'executionStatus' not in dumped
    assert dumped['controlResult']['outcome'] == 'unconfirmed'


def test_installed_protocol_includes_remote_semantics():
    from importlib.resources import files
    assert files('protocol').joinpath('remote/R1-contract.md').is_file()
