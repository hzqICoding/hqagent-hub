"""FZ-R1.1: only D42 wire versioning and D43 local-link additions."""
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
import subprocess

import pytest
from pydantic import ValidationError
import yaml
from protocol.generated.python import models

ROOT = Path(__file__).resolve().parents[3]
P = ROOT / 'packages/protocol'
BASE = '872a909'
MANIFEST = json.loads((P / 'fixtures/contracts/manifest.json').read_text(encoding='utf-8'))['fixtures']
LINK = json.loads((P / 'schema/remote-link.json').read_text(encoding='utf-8'))['$defs']
REMOTE = json.loads((P / 'schema/remote.json').read_text(encoding='utf-8'))['$defs']


def before(path):
    return subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT).decode('utf-8')


def frozen(path):
    return subprocess.check_output(["git", "show", f"500bf1f:{path}"], cwd=ROOT).decode("utf-8")


def value(name):
    filename = next(f for f,t in MANIFEST.items() if t == name)
    return json.loads((P / 'fixtures/contracts' / filename).read_text(encoding='utf-8'))


@pytest.mark.parametrize('file,kind', [(f,t) for f,t in MANIFEST.items() if f.startswith('remote-link.') or f == 'local-conversation.remote-authority.json'])
def test_new_fixtures_round_trip(file, kind):
    raw = json.loads((P / 'fixtures/contracts' / file).read_text(encoding='utf-8'))
    parsed = getattr(models, kind).model_validate(raw)
    assert parsed.model_dump(mode='json', by_alias=True, exclude_none=True) == raw


def test_every_new_type_has_a_fixture():
    assert set(LINK) <= set(MANIFEST.values())


def test_only_authorized_worker_frame_shapes_changed():
    # Historical FZ-R1.1 shape audit; live revision compatibility is covered by test_remote_sync_contract.
    REMOTE = json.loads(frozen("packages/protocol/schema/remote.json"))["$defs"]
    old = json.loads(before('packages/protocol/schema/remote.json'))['$defs']
    assert set(REMOTE) == set(old)
    count = 0
    for name, original in old.items():
        props = original.get('properties', {})
        if 'protocolVersion' not in props:
            current = deepcopy(REMOTE[name])
            if name == 'RemoteConversationSnapshot':
                # D45 permits exactly this browser-only addition, never a wire change.
                assert current['properties'].pop('approvals') == {
                    'type': 'array', 'items': {'$ref': 'remote.json#/$defs/RemoteApprovalView'},
                    'maxItems': 100,
                    'description': 'Pending, unexpired approvals for this conversation; omitted means []. Truncation sets hasMore.',
                }
            assert current == original
            continue
        count += 1
        current = REMOTE[name]
        assert current['properties']['wireRevision']['type'] == 'integer'
        assert current['properties']['wireRevision']['const'] == 1
        assert 'wireRevision' in current['required']
        if name == 'RemoteWorkerHello':
            assert 'const' not in current['properties']['protocolVersion']
            assert 'pattern' in current['properties']['protocolVersion']
        else:
            assert 'protocolVersion' not in current['properties']
        exempt = {'protocolVersion'}
        assert all(current['properties'][k] == v for k,v in props.items() if k not in exempt)
        added = {'wireRevision'} | ({'supportedWireRevisions'} if name == 'RemoteWorkerHelloRejected' else set())
        assert set(current['properties']) == (set(props) - ({'protocolVersion'} if name != 'RemoteWorkerHello' else set())) | added
        assert current.get('description') == original.get('description')
    assert count == 27


@pytest.mark.parametrize('package', ['0.6.0','0.6.1','0.7.0','3.2.1-rc.1+build.42'])
def test_wire_one_accepts_independent_diagnostic_package_versions(package):
    raw = value('RemoteWorkerHello')
    raw['protocolVersion'] = package
    raw['wireRevision'] = 1
    assert models.RemoteWorkerHello.model_validate(raw).protocol_version == package


@pytest.mark.parametrize('revision', [True, 1.0, '1', 0, 2])
def test_wire_revision_is_strict_integer_one(revision):
    raw = value('RemoteWorkerHello')
    raw['wireRevision'] = revision
    with pytest.raises(ValidationError):models.RemoteWorkerHello.model_validate(raw)


@pytest.mark.parametrize('package', ['0.06.1','latest','0.6','0.6.1-01'])
def test_diagnostic_version_is_semver(package):
    raw = value('RemoteWorkerHello');raw['protocolVersion'] = package
    with pytest.raises(ValidationError):models.RemoteWorkerHello.model_validate(raw)


def test_hello_rejection_advertises_supported_revisions():
    raw = value('RemoteWorkerHelloRejected')
    assert raw['error']['code'] == 'REMOTE_PROTOCOL_UNSUPPORTED'
    assert raw['supportedWireRevisions'] == [1]
    raw['supportedWireRevisions'] = []
    with pytest.raises(ValidationError):models.RemoteWorkerHelloRejected.model_validate(raw)
    raw.pop('supportedWireRevisions')
    with pytest.raises(ValidationError):models.RemoteWorkerHelloRejected.model_validate(raw)


@pytest.mark.parametrize('kind', list(LINK))
@pytest.mark.parametrize('key', ['deviceSecret','authorization','hubToken'])
def test_link_types_cannot_expose_or_accept_secrets(kind,key):
    raw = value(kind);raw[key] = 'must-not-be-here'
    with pytest.raises(ValidationError):getattr(models,kind).model_validate(raw)


def test_link_state_fields_are_not_interchangeable():
    raw=value('RemoteLinkPairingView');raw.pop('pairCode')
    with pytest.raises(ValidationError):models.RemoteLinkView.model_validate(raw)
    raw=value('RemoteLinkUnpairedView');raw['pairCode']='ABCD2345'
    with pytest.raises(ValidationError):models.RemoteLinkView.model_validate(raw)
    paired=models.RemoteLinkView.model_validate(value('RemoteLinkPairedView'))
    assert paired.root.last_connected_at is None
    assert paired.model_dump(mode='json',by_alias=True,exclude_none=True)['lastConnectedAt'] is None
    raw=value('RemoteLinkRevokedView');raw['connectionStatus']='online'
    with pytest.raises(ValidationError):models.RemoteLinkView.model_validate(raw)
    assert models.RemoteLinkView.model_validate(value('RemoteLinkFrozenView')).root.connection_status == 'online'


@pytest.mark.parametrize('origin', ['https://hub.example.invalid','https://localhost:8443/','https://127.0.0.1:65535','https://[::1]:8443','http://127.0.0.1:8080','http://localhost'])
def test_allowed_origin_shapes(origin):
    raw=value('RemoteLinkPairingInput');raw['serverOrigin']=origin
    assert models.RemoteLinkPairingInput.model_validate(raw).server_origin == origin


@pytest.mark.parametrize('origin', ['http://example.com','http://localhost.evil.test','http://127.0.0.2','http://[::1]','https://user:password@host.test','https://host.test/path','https://host.test?token=x','https://host.test#frag','https://host.test:65536','https://host.test:0','file:///tmp/test'])
def test_invalid_origins_are_rejected(origin):
    raw=value('RemoteLinkPairingInput');raw['serverOrigin']=origin
    with pytest.raises(ValidationError):models.RemoteLinkPairingInput.model_validate(raw)


def test_local_api_additions_preserve_existing_auth_and_remote_http():
    assert frozen('packages/protocol/openapi/remote-hub.v2.yaml') == before('packages/protocol/openapi/remote-hub.v2.yaml')
    old=yaml.safe_load(before('packages/protocol/openapi/local-hub.v1.yaml'))
    current=yaml.safe_load(frozen('packages/protocol/openapi/local-hub.v1.yaml'))
    for path,operations in old['paths'].items():assert current['paths'][path] == operations
    assert current['security'] == old['security'] == [{'bearerAuth':[]}]
    assert current['components'] == old['components']
    operations=[('/api/v1/remote/link','get'),('/api/v1/remote/pairing','post'),('/api/v1/remote/pairing','delete'),('/api/v1/remote/unlink','post')]
    for path,method in operations:
        op=current['paths'][path][method]
        assert 'security' not in op
        assert op['responses']['200']['x-dataSchema']['$ref'].endswith('/RemoteLinkView')
        if method!='get':assert any(p['name']=='Idempotency-Key' and p['required'] for p in op['parameters'])


def test_authority_is_additive_and_legacy_objects_round_trip():
    old=json.loads(before('packages/protocol/schema/local-chat.json'))
    now=json.loads(frozen('packages/protocol/schema/local-chat.json'))
    original=old['$defs']['LocalConversationView'];new=now['$defs']['LocalConversationView']
    assert new['required'] == original['required'] and 'authority' not in new['required']
    assert new['properties']['authority']['enum'] == ['local','remote']
    copy=json.loads(json.dumps(now));copy['$defs']['LocalConversationView']['properties'].pop('authority')
    assert copy == old
    raw=json.loads((P/'fixtures/contracts/local-conversation.archived.json').read_text(encoding='utf-8'))
    assert models.LocalConversationView.model_validate(raw).model_dump(mode='json',by_alias=True,exclude_none=True) == raw


def test_local_event_uses_existing_hub_envelope_and_typed_payload():
    raw=json.loads((P/'fixtures/contracts/remote-link.changed-event.json').read_text(encoding='utf-8'))
    assert raw['type']=='remote.link.changed' and raw['aggregateType']=='system'
    assert raw['protocolVersion']=='0.6.1' and 'wireRevision' not in raw
    models.HubEvent.model_validate(raw)
    models.RemoteLinkView.model_validate(raw['payload'])
    assert '`remote.link.changed`' in (P/'events/event-dictionary.md').read_text(encoding='utf-8')
