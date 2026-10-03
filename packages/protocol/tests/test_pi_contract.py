"""PI protocol only: synthetic inputs, no model, CLI or user configuration access."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import subprocess

import pytest
from pydantic import TypeAdapter, ValidationError
import yaml
from protocol.generated.python import models

P = Path(__file__).resolve().parents[1]
F = P / 'fixtures/contracts'
BASE = '6ba7583'
M = json.loads((F / 'manifest.json').read_text(encoding='utf-8'))['fixtures']
D = json.loads((P / 'schema/remote-pi.json').read_text(encoding='utf-8'))['$defs']
ALL = {n: (f.name, d) for f in (P / 'schema').glob('*.json')
       for n, d in json.loads(f.read_text(encoding='utf-8'))['$defs'].items()}


def sample(name):
    return json.loads((F / ('pi.' + name + '.json')).read_text(encoding='utf-8'))


def refs(value):
    if isinstance(value, dict):
        if '$ref' in value:
            yield value['$ref']
        for v in value.values():
            yield from refs(v)
    elif isinstance(value, list):
        for v in value:
            yield from refs(v)


@lru_cache(None)
def baseline(file):
    return subprocess.check_output(['git', 'show', f'{BASE}:packages/protocol/{file}'], cwd=P).decode('utf-8')


@pytest.mark.parametrize('file,kind', [(f, n) for f, n in M.items() if f.startswith('pi.')])
def test_pi_synthetic_fixture_roundtrip(file, kind):
    raw = json.loads((F / file).read_text(encoding='utf-8'))
    adapter = TypeAdapter(getattr(models, kind))
    assert adapter.dump_python(adapter.validate_python(raw), mode='json', by_alias=True, exclude_none=True) == raw


def test_all_new_types_have_fixture_and_version_is_independent():
    assert set(D) <= {n for f, n in M.items() if f.startswith('pi.')}
    assert models.PROTOCOL_VERSION == (P / 'VERSION').read_text().strip() == '0.11.0'
    for d in D.values():
        if 'wireRevision' in d.get('properties', {}):
            assert d['properties']['wireRevision'] == {'type': 'integer', 'const': 5}


def test_old_four_wire_transitive_closures_are_exactly_unchanged():
    pending = [('remote.json', f'Remote{s}OutboundFrame') for s in ['Worker', 'Server']]
    for v, f in [(2, 'remote-sync.json'), (3, 'remote-native.json'), (4, 'remote-attachments.json')]:
        pending += [(f, f'RemoteV{v}{s}OutboundFrame') for s in ['Worker', 'Server']]
    seen = set()
    while pending:
        f, name = pending.pop()
        if (f, name) in seen:
            continue
        seen.add((f, name))
        old = json.loads(baseline('schema/' + f))['$defs'][name]
        assert ALL[name] == (f, old), (f, name)
        for r in refs(old):
            target, pointer = r.split('#', 1)
            pending.append((target or f, pointer.split('/')[-1]))
    assert ALL['NativeAgentType'][1]['enum'] == ['claude', 'codex']
    assert D['RuntimeNativeAgentType']['enum'] == ['claude', 'codex', 'pi']


def test_legacy_fixtures_not_rewritten():
    old = json.loads(baseline('fixtures/contracts/manifest.json'))['fixtures']
    for file, kind in old.items():
        assert M[file] == kind
        assert (F / file).read_text(encoding='utf-8') == baseline('fixtures/contracts/' + file)


@pytest.mark.parametrize('side', ['Worker', 'Server'])
def test_revision5_union_has_every_frame_and_rejects_downgrade(side):
    root = f'RemoteV5{side}OutboundFrame'
    adapter = TypeAdapter(getattr(models, root))
    pending, seen = [root], set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        d = D[name]
        if 'oneOf' in d:
            pending += [r['$ref'].split('/')[-1] for r in d['oneOf']]
        else:
            raw = sample(name)
            adapter.validate_python(raw)
            raw['wireRevision'] = 4
            with pytest.raises(ValidationError):
                adapter.validate_python(raw)
    old = json.loads(baseline('schema/remote-attachments.json'))['$defs']
    old_types = {v['properties']['type']['const'] for n, v in old.items()
                 if n.startswith('RemoteV4') and 'wireRevision' in v.get('properties', {})}
    new_types = {v['properties']['type']['const'] for v in D.values() if 'wireRevision' in v.get('properties', {})}
    assert old_types == new_types


@pytest.mark.parametrize('code', ['PI_GUARD_UNAVAILABLE', 'PI_UNCONTROLLED_EXTENSIONS', 'PI_TOOL_CALL_BLOCKED'])
def test_new_errors_only_enter_revision5(code):
    for n in ['RemoteWorkerHelloRejected', 'RemoteV2WorkerHelloRejected', 'RemoteV3WorkerHelloRejected', 'RemoteV4WorkerHelloRejected']:
        file = next(f for f, kind in M.items() if kind == n)
        raw = json.loads((F / file).read_text(encoding='utf-8'))
        raw['error']['code'] = code
        with pytest.raises(ValidationError):
            getattr(models, n).model_validate(raw)
    raw = sample('RemoteV5WorkerHelloRejected')
    raw['error']['code'] = code
    models.RemoteV5WorkerHelloRejected.model_validate(raw)


@pytest.mark.parametrize('kind', ['RemoteV3NativeIndexUpserted', 'RemoteV4NativeIndexUpserted'])
def test_pi_enum_cannot_leak_to_old_native_frames(kind):
    file = next(f for f, n in M.items() if n == kind)
    raw = json.loads((F / file).read_text(encoding='utf-8'))
    raw['payload']['agentType'] = 'pi'
    with pytest.raises(ValidationError):
        getattr(models, kind).model_validate(raw)
    models.RemoteV5NativeIndexUpserted.model_validate(sample('RemoteV5NativeIndexUpserted'))


@pytest.mark.parametrize('selector', ['1aicode/deepseek/deepseek-v4-pro', '1aicode/deepseek/deepseek-v4-flash', '1aicode/deepseek/deepseek-v4-flash-vision-exp'])
def test_one_exact_model_selector_across_existing_ports(selector):
    models.PiModelSelection.model_validate({'modelId': selector})
    provider, model = selector.split('/', 1)
    assert provider == '1aicode' and model.startswith('deepseek/')
    raw = json.loads((F / 'pi.image-job-input.json').read_text(encoding='utf-8'))
    raw['modelId'] = selector
    models.StartLocalImageVerificationInput.model_validate(raw)
    raw = json.loads((F / 'pi.image-target.json').read_text(encoding='utf-8'))
    raw['modelId'] = selector
    models.LocalImageVerificationTarget.model_validate(raw)
    models.LocalAgentModel.model_validate({'id': selector, 'name': 'Synthetic model', 'efforts': [], 'isDefault': False})


@pytest.mark.parametrize('selector', ['pi', '/model', 'provider/', 'https://channel/model', 'provider//model', 'provider/../model', 'C:/secret', 'provider/model?key=secret', 'provider/model#key', 'provider\\model'])
def test_invalid_pi_selectors_are_rejected(selector):
    with pytest.raises(ValidationError):
        models.PiModelSelection.model_validate({'modelId': selector})


def test_unverified_vision_is_not_supported():
    raw = sample('RuntimeNativeImageCapability')
    assert raw['imageInput']['support'] == 'unknown'
    assert raw['imageInput']['runtimeImplemented'] is False and raw['imageInput']['verified'] is False
    assert raw['transport'] == 'pi-rpc-images-v1'
    assert set(sample('PiGuardDecision')) >= {'requestId', 'toolCallId', 'argumentsSha256', 'policyRevision', 'expiresAt'}


def test_internal_guard_never_reachable_from_public_or_wire_roots():
    internal = {'PiGuardCheckInput', 'PiGuardHandshake', 'PiGuardDecision'}
    roots = ['RemoteV5WorkerOutboundFrame', 'RemoteV5ServerOutboundFrame', 'AgentView', 'RemoteConversationView', 'RuntimeNativeSessionIndex']
    seen = set()
    while roots:
        n = roots.pop()
        if n in seen:
            continue
        seen.add(n)
        assert n not in internal
        roots += [r.split('/')[-1] for r in refs(ALL[n][1])]
    assert not {'path', 'source', 'argumentsJson', 'apiKey', 'url'} & set(D['RuntimeGuardView']['properties'])


@pytest.mark.parametrize('field', ['extensionSource', 'extensionPath', 'apiKey', 'providerUrl', 'argumentsJson'])
def test_safe_guard_diagnostic_rejects_private_fields(field):
    raw = sample('RuntimeGuardView');raw[field] = 'synthetic'
    with pytest.raises(ValidationError):
        models.RuntimeGuardView.model_validate(raw)


def test_phase2_profile_and_unsupported_evidence_are_frozen():
    profile = sample('PiNativeFormatProfile')
    assert profile == {'readerId': 'pi.jsonl.v3.tree', 'sessionVersion': 3, 'structure': 'tree', 'branchSelection': 'last_persisted_entry'}
    assert sample('RuntimeNativeFormatView')['unsupportedReason'] == 'reader_not_implemented'
    for field, val in [('sessionVersion', 4), ('branchSelection', 'latest_timestamp'), ('structure', 'flat')]:
        raw = deepcopy(profile);raw[field] = val
        with pytest.raises(ValidationError):
            models.PiNativeFormatProfile.model_validate(raw)


def test_explicit_http_opt_in_no_new_routes_and_no_cloud_paid_verification():
    for file in ['local-hub.v1.yaml', 'local-chat.v2.yaml', 'remote-hub.v2.yaml']:
        api = yaml.safe_load((P / 'openapi' / file).read_text(encoding='utf-8'))
        old = yaml.safe_load(baseline('openapi/' + file))
        assert set(api['paths']) == set(old['paths'])
        assert api['x-pi-client-compatibility']['feature'] == 'pi-v1'
        for path, item in api['paths'].items():
            for method, op in item.items():
                if method not in {'get', 'post', 'patch', 'put', 'delete'}:
                    continue
                assert op.get('security') == old['paths'][path][method].get('security')
                if '/worker/' in path or path.endswith('/openapi.json'):
                    continue
                h = [p for p in op['parameters'] if p.get('name') == 'X-HQ-Client-Features']
                assert len(h) == 1 and h[0]['required'] is False and h[0]['schema']['enum'] == ['pi-v1']
        if file == 'remote-hub.v2.yaml':
            assert set(api['x-worker-websocket']['revisions']) == {1, 2, 3, 4, 5}
            assert not any('image-verification' in path for path in api['paths'])


def test_existing_adapter_port_and_core_execution_are_not_forked():
    for file in ['adapter-port.json', 'common.json']:
        assert json.loads((P / 'schema' / file).read_text(encoding='utf-8')) == json.loads(baseline('schema/' + file))
