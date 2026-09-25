import asyncio

from protocol.generated.python import AdapterFailure, ApprovalDispatch

from adapters.codex_adapter import CodexAdapter
from adapters.session_registry import PendingApproval
from adapters.tests.test_contract_rules import FakeConnection, state_for


def dispatch(identifier, external='0'):
    return ApprovalDispatch(approvalId=identifier, externalRequestId=external, decision='approve',
                            decidedAt='2026-09-25T00:00:00Z')


def pair(tmp_path, *, old_resolved=False):
    adapter = CodexAdapter()
    old = state_for(tmp_path, session_id='old-session')
    current = state_for(tmp_path, session_id='current-session')
    for state, identifier in [(old, 'approval-old'), (current, 'approval-current')]:
        state.connection = FakeConnection()
        state.approvals[identifier] = PendingApproval(approval_id=identifier, external_request_id='0',
            request_id=0, method='item/commandExecution/requestApproval', resolved=old_resolved if state is old else False)
        adapter.registry.add(state)
    return adapter, old, current


def test_same_native_rpc_id_in_two_connections_only_dispatches_exact_hub_approval(tmp_path):
    async def scenario():
        adapter, old, current = pair(tmp_path)
        assert await adapter.approve(dispatch('approval-current')) is None
        assert old.connection.responses == []
        assert not old.approvals['approval-old'].resolved
        assert current.connection.responses == [(0, {'decision': 'accept'})]
        assert current.approvals['approval-current'].resolved
    asyncio.run(scenario())


def test_resolved_old_request_does_not_block_new_request_with_reused_rpc_id(tmp_path):
    async def scenario():
        adapter, old, current = pair(tmp_path, old_resolved=True)
        assert await adapter.approve(dispatch('approval-current')) is None
        assert old.connection.responses == []
        assert current.connection.responses == [(0, {'decision': 'accept'})]
    asyncio.run(scenario())


def test_unknown_approval_never_falls_back_to_numeric_rpc_id(tmp_path):
    async def scenario():
        adapter, old, current = pair(tmp_path)
        result = await adapter.approve(dispatch('approval-unknown'))
        assert isinstance(result, AdapterFailure)
        assert old.connection.responses == current.connection.responses == []
    asyncio.run(scenario())


def test_mismatched_native_id_is_rejected_without_consuming_pending_request(tmp_path):
    async def scenario():
        adapter, old, current = pair(tmp_path)
        assert isinstance(await adapter.approve(dispatch('approval-current', 'wrong')), AdapterFailure)
        assert old.connection.responses == current.connection.responses == []
        assert not current.approvals['approval-current'].resolved
    asyncio.run(scenario())
