"""Browser projection contract; no server business code or model calls."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import subprocess
from typing import Union

import pytest
from pydantic import TypeAdapter, ValidationError
import yaml
from protocol.generated.python import models

P = Path(__file__).resolve().parents[1]
F = P / 'fixtures/contracts'
BASE = '119a931'
LEGACY = '6ba7583'  # deployed 0.10.1 contract


@lru_cache(None)
def at(commit, file):
    return json.loads(subprocess.check_output(['git', 'show', f'{commit}:packages/protocol/{file}'], cwd=P).decode('utf-8'))


def sample(name):
    return json.loads((F / name).read_text(encoding='utf-8'))


def refs(value):
    if isinstance(value, dict):
        if '$ref' in value:
            yield value['$ref']
        for v in value.values():
            yield from refs(v)
    elif isinstance(value, list):
        for v in value:
            yield from refs(v)


def legacy_adapter():
    # Exactly the seven alternatives accepted by 0.10.1; none is the new variant.
    names = [r['$ref'].split('/')[-1] for r in at(LEGACY, 'schema/remote.json')['$defs']['RemoteBrowserEvent']['oneOf']]
    return TypeAdapter(Union[tuple(getattr(models, n) for n in names)])


def test_only_http_union_extended_no_wire_codec_changes():
    old = at(BASE, 'schema/remote.json')['$defs']['RemoteBrowserEvent']
    now = json.loads((P / 'schema/remote.json').read_text(encoding='utf-8'))['$defs']['RemoteBrowserEvent']
    expected = deepcopy(old)
    expected['oneOf'].append({'$ref': 'browser-pi.json#/$defs/RemoteBrowserPiApprovalEvent'})
    assert now == expected
    pending = [('remote.json', f'Remote{s}OutboundFrame') for s in ['Worker', 'Server']]
    for revision, file in [(2, 'remote-sync.json'), (3, 'remote-native.json'), (4, 'remote-attachments.json'), (5, 'remote-pi.json')]:
        pending += [(file, f'RemoteV{revision}{s}OutboundFrame') for s in ['Worker', 'Server']]
    seen = set()
    while pending:
        file, name = pending.pop()
        if (file, name) in seen:
            continue
        seen.add((file, name))
        old = at(BASE, 'schema/' + file)['$defs'][name]
        current = json.loads((P / 'schema' / file).read_text(encoding='utf-8'))['$defs'][name]
        assert old == current, (file, name)
        for r in refs(old):
            target, pointer = r.split('#', 1)
            pending.append((target or file, pointer.split('/')[-1]))


def test_legacy_approval_decoder_is_identical_to_0101():
    pending = [('remote-sync.json', 'RemoteV2ApprovalEvent')]
    seen = set()
    while pending:
        file, name = pending.pop()
        if (file, name) in seen:
            continue
        seen.add((file, name))
        old = at(LEGACY, 'schema/' + file)['$defs'][name]
        now = json.loads((P / 'schema' / file).read_text(encoding='utf-8'))['$defs'][name]
        assert old == now
        for r in refs(old):
            target, pointer = r.split('#', 1)
            pending.append((target or file, pointer.split('/')[-1]))


@pytest.mark.parametrize('status', ['pending', 'approved', 'rejected', 'expired'])
def test_non_pi_approval_reaches_old_store_branch_in_every_state(status):
    name = 'pi.RemoteBrowserLegacyApprovalEvent.json' if status == 'pending' else f'pi.browser-legacy-approval-{status}.json'
    raw = sample(name)
    legacy_adapter().validate_python(raw)
    models.RemoteBrowserEvent.model_validate(raw)
    assert raw['type'] == 'worker.event'
    assert raw['payload']['type'] == 'approval.state_changed'
    assert raw['payload']['payload']['status'] == status
    assert raw['payload']['wireRevision'] == 2
    assert raw['payload']['payload']['remoteApprovalAllowed'] is False
    assert 'sourceWireRevision' not in raw and 'agentType' not in raw


def test_pi_new_variant_is_accepted_only_by_new_decoder():
    raw = sample('pi.RemoteBrowserPiApprovalEvent.json')
    models.RemoteBrowserPiApprovalEvent.model_validate(raw)
    models.RemoteBrowserEvent.model_validate(raw)
    assert raw['payload']['payload']['denialCode'] == 'PI_TOOL_CALL_BLOCKED'
    with pytest.raises(ValidationError):
        legacy_adapter().validate_python(raw)
    # Reject unrelated revision5 events, even for an opted-in browser wrapper.
    raw['payload'] = sample('pi.RemoteV5ProgressEvent.json')
    with pytest.raises(ValidationError):
        models.RemoteBrowserPiApprovalEvent.model_validate(raw)


def test_projection_preserves_authority_and_does_not_mutate_source_fact():
    source = sample('pi.RemoteV5ApprovalEvent.json')
    before = deepcopy(source)
    projected = deepcopy(source)
    projected['wireRevision'] = 2
    projected['conversationId'] = 'public_conversation_synthetic'
    projected['payload']['approvalId'] = 'public_approval_synthetic'
    projected['payload']['resultRef'] = {'runId': 'public_run_synthetic'}
    raw = sample('pi.RemoteBrowserLegacyApprovalEvent.json')
    raw['payload'] = projected
    legacy_adapter().validate_python(raw)
    assert source == before and source['wireRevision'] == 5
    for key in ['eventId', 'workerId', 'workerStoreId', 'workerEpoch', 'seq', 'occurredAt']:
        assert projected[key] == source[key]
    for key in ['action', 'riskLevel', 'status', 'expiresAt', 'requestedAt', 'remoteApprovalAllowed', 'workerPolicyRevision']:
        assert projected['payload'][key] == source['payload'][key]
    with pytest.raises(ValidationError):
        models.RemoteV5ApprovalEvent.model_validate(projected)


def test_denial_fallback_is_explicit_and_never_enables_approval():
    source = sample('pi.RemoteV5ApprovalEvent.json')
    # R3 error can occur on a non-PI native conversation; it is outside wire2.
    source['payload']['denialCode'] = 'NATIVE_SESSION_ACTIVE'
    models.RemoteV5ApprovalEvent.model_validate(source)
    payload = deepcopy(source);payload['wireRevision'] = 2
    with pytest.raises(ValidationError):
        models.RemoteV2ApprovalEvent.model_validate(payload)
    payload['payload']['denialCode'] = 'REMOTE_APPROVAL_FORBIDDEN'
    models.RemoteV2ApprovalEvent.model_validate(payload)
    assert payload['payload']['remoteApprovalAllowed'] is False
    assert source['payload']['denialCode'] == 'NATIVE_SESSION_ACTIVE'


def test_filtered_page_discloses_no_pi_record_or_skip_count():
    raw = sample('pi.browser-filtered-page.json')
    models.RemoteBrowserEventPage.model_validate(raw)
    assert raw['items'] == [] and raw['hasMore'] is False
    assert raw['nextServerCursor']
    for field in ['hiddenCount', 'skippedTypes', 'piPresent', 'rawPosition']:
        bad = deepcopy(raw);bad[field] = 1
        with pytest.raises(ValidationError):
            models.RemoteBrowserEventPage.model_validate(bad)


def test_both_new_named_types_have_contract_fixtures():
    defs = json.loads((P / 'schema/browser-pi.json').read_text(encoding='utf-8'))['$defs']
    manifest = sample('manifest.json')['fixtures']
    assert set(defs) == {'RemoteBrowserLegacyApprovalEvent', 'RemoteBrowserPiApprovalEvent'}
    assert set(defs) <= {kind for name, kind in manifest.items() if name.startswith('pi.')}
    for name, kind in manifest.items():
        if kind in defs:
            raw = sample(name);adapter = TypeAdapter(getattr(models, kind))
            assert adapter.dump_python(adapter.validate_python(raw), mode='json', by_alias=True, exclude_none=True) == raw


def test_openapi_exposes_projection_without_new_cloud_ticket_route():
    api = yaml.safe_load((P / 'openapi/remote-hub.v2.yaml').read_text(encoding='utf-8'))
    assert api['info']['version'] == models.PROTOCOL_VERSION == '0.11.1'
    assert set(api['x-worker-websocket']['revisions']) == {1, 2, 3, 4, 5}
    assert not any('ticket' in path for path in api['paths'])
    assert api['x-browser-approval-projection']['piOptIn'].endswith('/RemoteBrowserPiApprovalEvent')
    assert api['paths']['/api/v2/events']['get']['responses']['200']['x-dataSchema']['$ref'].endswith('/RemoteBrowserEventPage')
