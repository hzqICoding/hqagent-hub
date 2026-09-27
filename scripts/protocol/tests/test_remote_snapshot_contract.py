"""D45 snapshot compatibility; server-side filtering is P1's responsibility."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import subprocess

import pytest
from pydantic import ValidationError
from protocol.generated.python import models


ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = ROOT / 'packages/protocol'
FIXTURES = PROTOCOL / 'fixtures/contracts'
BASE = 'dd12a2e0dba162078339d7d7c81306926da3af5e'
WITHOUT = 'remote.RemoteConversationSnapshot.json'
WITH = 'remote.RemoteConversationSnapshot.with-approvals.json'


def fixture(name=WITH):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def before(path):
    return subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT).decode('utf-8')


@pytest.mark.parametrize('name', [WITHOUT, WITH])
def test_snapshot_fixture_round_trip(name):
    raw = fixture(name)
    parsed = models.RemoteConversationSnapshot.model_validate(raw)
    assert parsed.model_dump(mode='json', by_alias=True, exclude_none=True) == raw


def test_old_server_missing_approvals_remains_omitted_and_consumers_can_use_empty_list():
    raw = fixture(WITHOUT)
    assert 'approvals' not in raw
    parsed = models.RemoteConversationSnapshot.model_validate(raw)
    assert 'approvals' not in parsed.model_fields_set
    assert (parsed.approvals or []) == []
    assert 'approvals' not in parsed.model_dump(mode='json', by_alias=True, exclude_none=True)


@pytest.mark.parametrize('size', [0, 100])
def test_bounded_approval_set_preserves_empty_and_full_arrays(size):
    raw = fixture()
    template = raw['approvals'][0]
    raw['approvals'] = [dict(deepcopy(template), approvalId=f'approval_{i}') for i in range(size)]
    raw['hasMore'] = size == 100
    parsed = models.RemoteConversationSnapshot.model_validate(raw)
    assert len(parsed.approvals) == size
    assert parsed.model_dump(mode='json', by_alias=True, exclude_none=True) == raw


@pytest.mark.parametrize('invalid', [None, {}, 'pending', [None], [{}]])
def test_optional_approvals_still_requires_a_typed_array_when_present(invalid):
    raw = fixture()
    raw['approvals'] = invalid
    with pytest.raises(ValidationError):
        models.RemoteConversationSnapshot.model_validate(raw)


def test_101_approvals_are_rejected_even_when_has_more_is_true():
    raw = fixture()
    raw['approvals'] *= 101
    raw['hasMore'] = True
    with pytest.raises(ValidationError):
        models.RemoteConversationSnapshot.model_validate(raw)


def test_pending_fixture_includes_remotely_rejectable_high_risk_approval():
    raw = fixture()
    by_run = {run['runId']: run for run in raw['runs']}
    for approval in raw['approvals']:
        assert approval['status'] == 'pending'
        assert datetime.fromisoformat(approval['expiresAt']) > datetime.fromisoformat(raw['observedAt'])
        assert datetime.fromisoformat(approval['requestedAt']) <= datetime.fromisoformat(raw['observedAt'])
        assert by_run[approval['resultRef']['runId']]['conversationId'] == raw['conversation']['conversationId']
        assert approval['action'] == 'git_push'
        assert approval['remoteApprovalAllowed'] is False
        assert approval['denialCode'] == 'REMOTE_APPROVAL_FORBIDDEN'


def test_only_one_optional_browser_property_changes_and_all_wire_defs_stay_identical():
    original = json.loads(before('packages/protocol/schema/remote.json'))
    # Historical D45 delta; live snapshot/legacy-wire scope is checked by test_remote_sync_contract.
    current = json.loads(subprocess.check_output(['git', 'show', '500bf1f:packages/protocol/schema/remote.json'], cwd=ROOT))
    prop = current['$defs']['RemoteConversationSnapshot']['properties'].pop('approvals')
    assert prop == {
        'type': 'array', 'items': {'$ref': 'remote.json#/$defs/RemoteApprovalView'},
        'maxItems': 100,
        'description': 'Pending, unexpired approvals for this conversation; omitted means []. Truncation sets hasMore.',
    }
    assert current == original
    assert 'approvals' not in current['$defs']['RemoteConversationSnapshot']['required']
    for path in ['openapi/remote-hub.v2.yaml', 'events/event-dictionary.md', 'registry/error-codes.yaml']:
        assert subprocess.check_output(['git', 'show', '500bf1f:packages/protocol/' + path], cwd=ROOT).decode('utf-8') == before('packages/protocol/' + path)
