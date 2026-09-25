from __future__ import annotations

import asyncio
import json
from pathlib import Path
import subprocess

import pytest
from protocol.generated.python import (
    AdapterFailure, AgentResult, AgentSessionHandle, CreateTaskInput,
    SaveLocalSceneInput, TaskActionInput,
)
from adapters.events import AdapterEvent
from core.errors import HubError
from orchestrator.tests.fakes import FakeAdapter, FakeAdapterDirectory, agent, now
from runtime.review_evidence import MAX_EVIDENCE_BYTES
from security.worktrees import WorktreeManager
from storage.local_chat import LocalChatRepository
from tests.test_task_service_live import Workspaces, build_service, settle


class AcceptanceAdapter(FakeAdapter):
    def __init__(self, verdict='done', *, mutate=False, oversize=False, resumable=True, pause=False):
        super().__init__()
        self.verdict, self.mutate, self.oversize = verdict, mutate, oversize
        self.resumable, self.pause = resumable, pause
        self.specs, self.results = {}, {}
        self.developer_path = None
        self.service = None

    async def start(self, spec):
        self.started.append(spec)
        self.specs[spec.session_id] = spec
        if str(spec.role_id) == 'developer':
            self.developer_path = Path(spec.worktree_path) / 'counter.js'
            self.developer_path.write_text('x' * (MAX_EVIDENCE_BYTES + 1) if self.oversize else 'const limit = 10;\n', encoding='utf-8')
            self.results[spec.session_id] = AgentResult(status='done', summary='implementation',
                changedFiles=[{'path': 'counter.js', 'changeKind': 'added'}],
                tests=[{'name': 'counter', 'command': 'node --test', 'passed': True}])
        else:
            self.results[spec.session_id] = AgentResult(status='done', summary='ORIGINAL_PLAN_MARKER', changedFiles=[])
        return AgentSessionHandle(sessionId=spec.session_id, externalSessionId='native-' + spec.session_id,
            adapterId='test-adapter', startedAt=now(), supportsResume=self.resumable,
            workingDirectory=spec.worktree_path)

    async def resume(self, request):
        self.resumed.append(request)
        self.specs[request.session_id] = request.task_spec
        if self.mutate:
            target = self.developer_path.with_name('late.txt') if self.mutate == 'extra' else self.developer_path
            target.write_text('changed during acceptance', encoding='utf-8')
        if self.verdict == 'parse_error':
            self.results[request.session_id] = AdapterFailure(kind='agent_error', message='malformed final result', retryable=False)
        else:
            self.results[request.session_id] = AgentResult(status=self.verdict, summary='审核结论', changedFiles=[])

    async def collect_result(self, session_id):
        spec = self.specs[session_id]
        if self.pause and str(spec.role_id) == 'developer':
            state = self.service._task_spec(spec.task_id)
            state['pauseRequested'] = True
            self.service.state.put('task_spec:' + spec.task_id, state)
            self.pause = False
        return self.results[session_id]

    async def stream_events(self, session_id):
        if str(self.specs[session_id].role_id) == 'developer':
            yield AdapterEvent.create('command/completed', 'agent.tool_call', {
                'toolName': 'commandExecution', 'argumentsExcerpt': 'node --test',
                'exitCode': 0, 'resultSummary': 'tests 1 pass 1 fail 0', 'failed': False,
            })


def setup(tmp_path, **options):
    service, _, database = build_service(tmp_path)
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'README.md').write_text('isolated fixture', encoding='utf-8')
    for args in [ ['init', '-b', 'main'], ['add', 'README.md'],
                  ['-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'initial fixture'] ]:
        subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
    adapter = AcceptanceAdapter(**options)
    caps = ('architecture', 'coding', 'file_write', 'tool_approval', 'structured_output', 'review')
    directory = FakeAdapterDirectory((agent('planning', capabilities=caps), agent('coding', capabilities=caps)), adapter)
    service.directory = directory
    service.runtime.adapters = directory
    service.runtime.sessions.adapters = directory
    service.workspaces = Workspaces(root, can_write=True)
    service.worktrees = WorktreeManager(tmp_path / 'worktrees')
    adapter.service = service
    return service, adapter, database, root


def request():
    return CreateTaskInput(objective='counter with upper limit 10', workspaceId='workspace',
        workflowRoles=['planner', 'developer', 'reviewer'], reviewMode='original_planner',
        roleOverrides={'planner': 'planning', 'developer': 'coding', 'reviewer': 'coding'},
        roleExecutions={'reviewer': {'instructions': 'verify actual source and tests'}})


@pytest.mark.parametrize('verdict,expected_status,expected_verdict', [
    ('done', 'succeeded', 'passed'), ('failed', 'failed', 'changes_requested'),
    ('blocked', 'failed', 'insufficient_evidence'), ('parse_error', 'failed', None),
])
def test_original_planner_acceptance_uses_same_session_with_real_evidence(tmp_path, verdict, expected_status, expected_verdict):
    async def scenario():
        service, adapter, db, source = setup(tmp_path, verdict=verdict)
        try:
            task = await service.create_task(request(), 'acceptance')
            await settle(service)
            task = await service.get_task(task.id)
            assert str(task.status) == expected_status, task.failure_reason
            plan, dev, review = task.nodes
            assert [str(n.role_id) for n in task.nodes] == ['planner', 'developer', 'planner']
            assert len(adapter.started) == 2 and len(adapter.resumed) == 1
            assert review.session_id == plan.session_id != dev.session_id
            assert review.external_session_id == plan.external_session_id != dev.external_session_id
            assert review.worktree_path == plan.worktree_path == str(source)
            assert task.worktree_path == dev.worktree_path
            assert review.phase == 'acceptance' and review.review_verdict == expected_verdict
            assert review.review_source_node_id == plan.id and review.review_evidence_id
            resumed = adapter.resumed[0]
            assert resumed.task_spec.read_only and resumed.task_spec.allowed_paths == []
            assert 'ORIGINAL_PLAN_MARKER' in resumed.message
            assert 'const limit = 10;' in resumed.message
            assert 'tests 1 pass 1 fail 0' in resumed.message
            evidence = service._task_spec(task.id)['acceptanceEvidence'][review.id]
            assert evidence['observedCommands'][0]['exitCode'] == 0
            assert evidence['sourceWorktree'] == dev.worktree_path
            if verdict in ('done', 'failed', 'blocked'):
                assert str((await service.runtime.sessions.repository.get(plan.session_id)).status) == 'idle'
        finally:
            db.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('options,error,expected_resumes', [
    ({'mutate': True}, '发生变化', 1), ({'oversize': True}, '大小上限', 0),
    ({'mutate': 'extra'}, '发生变化', 1),
    ({'resumable': False}, 'idle', 0),
])
def test_bad_evidence_or_unavailable_session_blocks_without_new_reviewer(tmp_path, options, error, expected_resumes):
    async def scenario():
        service, adapter, db, _ = setup(tmp_path, **options)
        try:
            task = await service.create_task(request(), 'blocked-acceptance')
            await settle(service)
            task = await service.get_task(task.id)
            assert str(task.status) == 'failed'
            assert str(task.nodes[0].status) == str(task.nodes[1].status) == 'succeeded'
            assert error in task.nodes[2].error
            assert len(adapter.started) == 2 and len(adapter.resumed) == expected_resumes
        finally:
            db.close()
    asyncio.run(scenario())


def test_paused_after_development_can_restore_planner_from_persisted_state(tmp_path):
    async def scenario():
        service, adapter, db, _ = setup(tmp_path, pause=True)
        try:
            task = await service.create_task(request(), 'pause-before-acceptance')
            await settle(service)
            task = await service.get_task(task.id)
            assert str(task.status) == 'paused'
            original_id = task.nodes[0].session_id
            replacement = AcceptanceAdapter()
            replacement.developer_path = adapter.developer_path
            service.directory.adapter = replacement
            await service.act(task.id, TaskActionInput(action='resume'), 'resume-acceptance')
            await settle(service)
            completed = await service.get_task(task.id)
            assert str(completed.status) == 'succeeded', completed.failure_reason
            assert replacement.started == []
            assert replacement.resumed[0].session_id == original_id
            assert replacement.resumed[0].task_spec is not None
        finally:
            db.close()
    asyncio.run(scenario())


def test_scene_rejects_missing_planner_and_freezes_original_identity(tmp_path):
    service, _, db, _ = setup(tmp_path)
    try:
        repo = LocalChatRepository(db)
        scene = repo.scene('develop')
        roles = [r.model_copy(update={'enabled': True, 'agent_instance_id': 'planning' if r.role_id == 'planner' else 'coding'}) for r in scene.roles]
        roles[0] = roles[0].model_copy(update={'enabled': False})
        with pytest.raises(HubError, match='planner'):
            repo.save_scene('develop', SaveLocalSceneInput(roles=roles, expectedVersion=scene.version, reviewMode='original_planner'))
        roles[0] = roles[0].model_copy(update={'enabled': True})
        updated = repo.save_scene('develop', SaveLocalSceneInput(roles=roles, expectedVersion=scene.version, reviewMode='original_planner'))
        assert updated.roles[2].agent_instance_id == updated.roles[0].agent_instance_id == 'planning'
        assert str(updated.review_mode) == 'original_planner'
        assert scene.review_mode is None  # old snapshot object is not mutated
    finally:
        db.close()


def test_review_evidence_refuses_outside_and_binary_files(tmp_path):
    from runtime.review_evidence import _files
    source = tmp_path / 'source'
    source.mkdir()
    (tmp_path / 'outside.txt').write_text('not part of this checkout')
    with pytest.raises(HubError, match='越出'):
        _files(source, ['../outside.txt'])
    (source / 'binary.dat').write_bytes(b'\x00private-binary')
    with pytest.raises(HubError, match='二进制'):
        _files(source, ['binary.dat'])
