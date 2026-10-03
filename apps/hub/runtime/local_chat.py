"""Local conversations enqueue immutable scene snapshots into the real TaskPort."""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
import json
import logging
import time
from typing import Any

from protocol.generated.python import (
    CreateLocalConversationInput, CreateTaskInput, LocalRunView, LocalSceneView,
    SaveTeamProfileInput, SendLocalMessageInput, TaskActionInput,
    UpdateLocalConversationInput,
)
from core.errors import HubError
from storage.local_chat import LocalChatRepository, TERMINAL, now, uid


class LocalChatService:
    def __init__(self, repository: LocalChatRepository, ports: Any, *, poll_seconds: float = 0.25) -> None:
        self.repository = repository
        self.ports = ports
        self.poll_seconds = poll_seconds
        self._jobs: dict[str, asyncio.Task] = {}
        self._supervisor: asyncio.Task | None = None
        self._closed = False
        self._wake = asyncio.Event()
        self._slots = asyncio.Semaphore(3)
        self._last_approval_check = 0.0
        self._conversation_locks: dict[str, asyncio.Lock] = {}
        self.remote_dispatch_guard = None
        from runtime.conversation_deletion import ConversationDeletion
        self.deletions = ConversationDeletion(self)

    async def start(self) -> None:
        self._closed = False
        await self.deletions.recover()
        if getattr(self, 'attachments', None):
            await self.attachments.recover()
        if self._supervisor is None:
            self._supervisor = asyncio.create_task(self._supervise())

    async def stop(self) -> None:
        self._closed = True
        self._wake.set()
        tasks = [*self._jobs.values()]
        if self._supervisor:
            tasks.append(self._supervisor)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._jobs.clear()
        self._supervisor = None

    async def create_conversation(self, value: CreateLocalConversationInput, key: str):
        workspaces = await self.ports.workspaces.list_workspaces(None, None)
        if value.workspace_id not in {w.id for w in workspaces}:
            raise HubError("NOT_FOUND", "请先登记并选择本机项目目录")
        return self.repository.create_conversation(value, key)

    async def delete_conversation(self, conversation_id: str, expected_version: int, key: str):
        return await self.deletions.delete(conversation_id, expected_version, key)

    async def guard_task_operation(self, task_id: str, operation, *, profile_id=None):
        """Direct Task/session controls share every owning conversation boundary."""
        with self.repository.database.locked_connection() as db:
            conversations, seen, profiles, ancestor = set(), set(), {profile_id} if profile_id else set(), task_id
            while ancestor and ancestor not in seen:
                seen.add(ancestor)
                conversations.update(row[0] for row in db.execute(
                    'SELECT conversation_id FROM local_runs WHERE task_id=?', (ancestor,)))
                task = db.execute('SELECT profile_id,payload_json FROM tasks WHERE task_id=?', (ancestor,)).fetchone()
                if not task:
                    break
                profiles.add(task[0])
                ancestor = json.loads(task[1]).get('parentTaskId')
            for profile in profiles:
                if profile and profile.startswith('local-profile:'):
                    conversations.update(row[0] for row in db.execute(
                        'SELECT conversation_id FROM local_runs WHERE run_id=?', (profile[len('local-profile:'):],)))
        async with AsyncExitStack() as stack:
            for conversation in sorted(conversations):
                await stack.enter_async_context(self._conversation_lock(conversation))
            self.repository.assert_local_task(task_id)
            for profile in profiles:
                self.repository.assert_local_profile(profile)
            for conversation in conversations:
                self.repository.assert_not_deleted(conversation)
            return await operation()

    def _conversation_lock(self, conversation_id: str) -> asyncio.Lock:
        return self._conversation_locks.setdefault(conversation_id, asyncio.Lock())

    async def conversations(self, *, include_hidden=False, workspace_id=None):
        return self.repository.conversations(include_hidden=include_hidden, workspace_id=workspace_id)

    async def update_conversation(self, conversation_id: str,
                                  value: UpdateLocalConversationInput, key: str):
        self.repository.assert_local_authority(conversation_id)
        async def update():
            if value.archived is True:
                await self._refresh_unfinished_runs(conversation_id)
            return self.repository.update_conversation(conversation_id, value, key)

        if "archived" in value.model_fields_set:
            async with self._conversation_lock(conversation_id):
                return await update()
        return await update()

    def send(self, conversation_id: str, value: SendLocalMessageInput, key: str):
        receipt = self.repository.enqueue(conversation_id, value, key)
        self._wake.set()
        return receipt

    async def run(self, run_id: str) -> LocalRunView:
        record = self.repository.run_record(run_id)
        task = None
        if record["task_id"]:
            task = await self.ports.tasks.get_task(record["task_id"])
            status = str(task.status)
            if status != record["status"]:
                record = {**record, "status": status, "error": getattr(task, "failure_reason", None)}
        return self.repository.view(record, task)

    async def control(self, run_id: str, value: TaskActionInput, key: str):
        self.repository.assert_local_authority(self.repository.run_record(run_id)["conversation_id"])
        return await self.consume_remote_control(run_id, value, key)

    async def consume_remote_control(self, run_id: str, value: TaskActionInput, key: str):
        """Internal control bridge. Remote inbox admission precedes this call."""
        if not key:
            raise HubError("VALIDATION_FAILED", "必须提供Idempotency-Key")
        record = self.repository.run_record(run_id)
        async with self._conversation_lock(record["conversation_id"]):
            self.repository.assert_not_deleted(record['conversation_id'])
            if str(value.action) in {"append_instruction", "resume", "retry"}:
                self.repository.assert_execution_allowed(record["conversation_id"])
            return await self._control(record, value, key)

    def wake_remote_queue(self) -> None:
        """Wake only after the inbox / run / receipt transaction commits."""
        self._wake.set()

    async def _control(self, record: dict, value: TaskActionInput, key: str):
        run_id = record["run_id"]
        attachments = getattr(self, 'attachments', None)
        if str(value.action) == 'cancel' and attachments and await attachments.cancel(run_id):
            return await self.run(run_id)
        if str(value.action) == 'retry' and attachments and not record['task_id']:
            preparation = attachments.repo.preparation(run_id)
            if preparation and preparation['state'] == 'failed':
                # No Task ever existed before preparation failed. An explicit
                # retry admits a new LocalRun/first Task; never auto-replays it.
                return await self.run(attachments.retry_preparation(record, key))
        if str(value.action) == "append_instruction":
            if not value.instruction:
                raise HubError("VALIDATION_FAILED", "追加内容不能为空")
            receipt = self.send(record["conversation_id"], SendLocalMessageInput.model_validate({
                "clientMessageId": key, "text": value.instruction, "sessionMode": "continue",
            }), key)
            return await self.run(receipt.run_id)
        if not record["task_id"]:
            if str(value.action) != "cancel" or record["status"] not in {"queued", "running", "cancelled"}:
                raise HubError("TASK_ACTION_INVALID", "该轮尚未派发，只能请求取消")
            def cancel(tx):
                current = self.repository.run_record(run_id)
                if current["status"] in {"queued", "cancelled"}:
                    self.repository.complete_run(run_id, "cancelled", "本轮在派发前取消。", transaction=tx)
                else:
                    self.repository.request_cancel(run_id, tx)
                return {"runId": run_id}
            self.repository.command(f"run-control:{run_id}", key, value.model_dump(mode="json"), cancel)
            return await self.run(run_id)
        task = await self.ports.tasks.act(record["task_id"], value, key)
        if task.id != record["task_id"]:
            # A terminal retry is a new execution, preserving the previous run.
            def retry(tx):
                existing = tx.connection.execute("SELECT run_id FROM local_runs WHERE task_id=?", (task.id,)).fetchone()
                if existing:
                    return {"runId": existing[0]}
                new_id, message_id, stamp = uid("run"), uid("message"), now()
                seq = tx.connection.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM local_messages WHERE conversation_id=?", (record["conversation_id"],)).fetchone()[0]
                tx.connection.execute("INSERT INTO local_messages VALUES(?,?,?,?,?,?,?)", (message_id, record["conversation_id"], seq, "user", "重试上一轮任务", new_id, stamp))
                tx.connection.execute("INSERT INTO local_runs VALUES(?,?,?,?,?,?,?,?,?,?)", (new_id, record["conversation_id"], message_id, task.id, record["scene_json"], "new", str(task.status), None, stamp, stamp))
                return {"runId": new_id}
            response, _ = self.repository.command(f"retry:{run_id}", key, value.model_dump(mode="json"), retry)
            self._wake.set()
            return await self.run(response["runId"])
        if str(task.status) in TERMINAL:
            self.repository.complete_run(run_id, str(task.status), self._result_text(task), error=getattr(task, "failure_reason", None))
        else:
            self.repository.update_run(run_id, str(task.status), error=getattr(task, "failure_reason", None))
        self._wake.set()
        return await self.run(run_id)

    async def _refresh_unfinished_runs(self, conversation_id: str) -> None:
        for record in self.repository.unfinished_runs(conversation_id):
            if not record["task_id"]:
                continue
            try:
                task = await self.ports.tasks.get_task(record["task_id"])
            except Exception:
                # The durable local status remains unfinished, so archive still fails safely.
                continue
            status = str(task.status)
            if status != record["status"]:
                if status in TERMINAL:
                    self.repository.complete_run(
                        record["run_id"], status, self._result_text(task),
                        error=getattr(task, "failure_reason", None),
                    )
                else:
                    self.repository.update_run(
                        record["run_id"], status,
                        error=getattr(task, "failure_reason", None),
                    )

    async def _supervise(self) -> None:
        while not self._closed:
            if time.monotonic() - self._last_approval_check >= 5:
                self._last_approval_check = time.monotonic()
                if hasattr(type(self.ports.tasks), "expire_approvals"):
                    try:
                        await self.ports.tasks.expire_approvals()
                    except Exception:
                        logging.getLogger(__name__).error("工具审批过期检查失败，需要检查本机任务状态", exc_info=True)
            for conversation in self.repository.conversations(include_hidden=True, observe_native=False):
                job = self._jobs.get(conversation.id)
                if job and not job.done():
                    continue
                if job:
                    # Retrieve failures; the loop stays alive for unrelated conversations.
                    try:
                        job.result()
                    except (Exception, asyncio.CancelledError):
                        pass
                record = self.repository.next_run(conversation.id)
                if record is not None and record["status"] != "paused":
                    self._jobs[conversation.id] = asyncio.create_task(self._drive(record))
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), self.poll_seconds)
            except TimeoutError:
                pass

    async def _drive(self, record: dict) -> None:
        async with self._slots:
            await self._execute(record)

    async def _execute(self, record: dict) -> None:
        run_id = record["run_id"]
        try:
            task_id = record["task_id"]
            if task_id is None:
                if self.remote_dispatch_guard is not None and not self.remote_dispatch_guard(record):
                    return
                # Claim synchronously before the first await, so queued cancellation
                # cannot race with a side effect that has already started dispatch.
                current = self.repository.run_record(run_id)
                if current["status"] == "cancelled":
                    return
                self.repository.update_run(run_id, "running")
                attachments = getattr(self, 'attachments', None)
                inputs = await attachments.prepare(record) if attachments else []
                spec = await self._task_input(record)
                task = await attachments.start_task(record, inputs, spec) if attachments else await self.ports.tasks.create_task(spec, f"local-run:{run_id}")
                task_id = task.id
                self.repository.update_run(run_id, "running", task_id=task_id)
                if self.repository.cancel_requested(run_id) and str(task.status) not in TERMINAL:
                    await self.ports.tasks.act(task_id, TaskActionInput(action="cancel"), f"local-cancel-dispatch:{run_id}")
            while not self._closed:
                task = await self.ports.tasks.get_task(task_id)
                status = str(task.status)
                if status in TERMINAL:
                    self.repository.complete_run(run_id, status, self._result_text(task), error=getattr(task, "failure_reason", None))
                    return
                self.repository.update_run(run_id, status, error=getattr(task, "failure_reason", None))
                if status == "paused":
                    return
                await asyncio.sleep(self.poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            message = getattr(error, "message", None) or str(error) or type(error).__name__
            self.repository.complete_run(run_id, "failed", f"本轮未完成：{message}", error=message,
                error_code=error.code if isinstance(error, HubError) else None)

    def _context_needs_recovery(self, record: dict | None) -> bool:
        if record is None:
            return False
        if record['status'] not in TERMINAL:
            return True
        busy = self.repository.busy_state
        if busy is None:
            return False
        # Real execution evidence is authoritative even without pairing. Older
        # ports without a structured observer keep their existing session checks.
        observable = getattr(type(self.ports.tasks), 'activity_observation', None)
        if not record['task_id'] or busy.enabled() or observable is not None:
            return bool(busy.observe(record)['recoveryRequired'])
        return False

    async def _task_input(self, record: dict) -> CreateTaskInput:
        if json.loads(record["scene_json"]).get("conversationKind") == "native":
            spec = await self.native.task_input(record)
            self.repository.record_session_mode(record, 'continue', 'native_bound_session')
            return spec
        scene = LocalSceneView.model_validate_json(record["scene_json"])
        conversation = self.repository.conversation(record["conversation_id"])
        roles = [r for r in scene.roles if r.enabled]
        profile_id = f"local-profile:{record['run_id']}"
        from runtime.execution_selection import scene_execution
        profile, overrides, options = scene_execution(scene, profile_id)
        await self.ports.team_profiles.save_profile(profile_id, profile)
        resume_sessions = {}
        if record["session_mode"] == "continue":
            prior, old = self.repository.continuation_history(record)
            if self._context_needs_recovery(prior):
                raise HubError("SESSION_NOT_RESUMABLE", "上一轮仍需本机恢复核对，不能跳过它续接更早上下文")
            if old is not None:
                if self._context_needs_recovery(old):
                    raise HubError('SESSION_NOT_RESUMABLE', '上一轮执行仍需本机恢复核对，不能开启新的执行')
                old_scene = LocalSceneView.model_validate_json(old["scene_json"])
                if str(scene.review_mode or "independent") != str(old_scene.review_mode or "independent"):
                    raise HubError("SESSION_NOT_RESUMABLE", "验收方式已变化，请点右上角 + 开启新话题")
                old_roles = {r.role_id: r for r in old_scene.roles if r.enabled}
                if set(old_roles) != {r.role_id for r in roles}:
                    raise HubError('SESSION_NOT_RESUMABLE', '角色或模型配置已变化，请点右上角 + 开启新话题')
                detail = await self.ports.tasks.get_task(old["task_id"])
                sessions = await self.ports.sessions.list_sessions({"taskId": old["task_id"]})
                session_map = {s.id: s for s in sessions}
                for role in roles:
                    if role.role_id not in old_roles or role.model_dump() != old_roles[role.role_id].model_dump():
                        raise HubError("SESSION_NOT_RESUMABLE", "角色或模型配置已变化，请点右上角 + 开启新话题")
                    if str(scene.review_mode) == "original_planner" and role.role_id == "reviewer":
                        # Acceptance resolves the current planning node's exact session.
                        continue
                    node = next((n for n in reversed(detail.nodes) if str(n.role_id) == role.role_id), None)
                    session = session_map.get(node.session_id) if node else None
                    if session is None or not session.is_valid or str(session.status) != "idle":
                        if session is not None and str(session.status) == "closed":
                            raise HubError("SESSION_NOT_RESUMABLE", f"角色{role.role_id}的上一轮会话已关闭，不能原生续接；请点右上角 + 开启新话题，并附上需要继续处理的上一轮结果")
                        raise HubError("SESSION_NOT_RESUMABLE", f"角色{role.role_id}没有可恢复会话，请点右上角 + 开启新话题")
                    resume_sessions[role.role_id] = session.id
        spec = CreateTaskInput.model_validate({
            "objective": self.repository.run_text(record["run_id"]), "workspaceId": conversation.workspace_id,
            "profileId": profile_id, "source": "desktop", "workflowRoles": [r.role_id for r in roles],
            "roleOverrides": overrides,
            "roleExecutions": options,
            "resumeSessions": resume_sessions or None,
            "reviewMode": scene.review_mode or "independent",
        })
        self.repository.record_session_mode(record, 'continue' if resume_sessions else 'new',
            'existing_execution' if resume_sessions else 'no_prior_execution' if record['session_mode'] == 'continue' else 'explicit_new')
        return spec

    @staticmethod
    def _result_text(task: Any) -> str:
        sections = []
        for node in task.nodes:
            if node.output_summary:
                label = "原规划者验收" if str(node.phase) == "acceptance" and str(node.role_id) == "planner" else str(node.role_id)
                sections.append(f"### {label}\n\n{node.output_summary}")
            if node.error:
                sections.append(f"{node.role_id}：{node.error}")
        if task.result and task.result.summary and not sections:
            sections.append(task.result.summary)
        reason = getattr(task, "failure_reason", None)
        if reason and reason not in "\n".join(sections):
            sections.append(reason)
        return "\n\n".join(sections) or f"本轮状态：{task.status}"
