"""任务应用服务：TaskPort 的实现。

W3 交付了编排的**机制**——WorkflowPlan 管 DAG、WorkflowRuntime 管单个节点的
分派与收尾、TaskRecoveryService 管按事件流重建状态。但没有一层把它们和
「用户提交一个目标」连起来，因为那要落库、要驱动、要暴露 HTTP，全在 W1 的路径上。
这个文件就是那一层。

规则一律不放在这里：能力匹配在 role_resolver，权限在 permissions，
路径在 paths，会话隔离在 sessions。这里只做编排的推进和持久化。

默认工作流按施工方案 §6.6：实现 → 复核。不做「让 orchestrator 先拆解目标」——
那本身是一次 Agent 调用，属于 Phase 1.1 的编排增强，现在做会让最简单的
「派一个任务下去」也依赖一次额外的模型往返。
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from protocol.generated.python import (
    AdapterStreamEnd,
    AgentResult,
    CreateTaskInput,
    NodeStatus,
    PageResult,
    TaskActionInput,
    TaskDetailView,
    TaskNodeView,
    TaskStatus,
    TaskSummaryView,
)

from core.errors import HubError
from orchestrator.domain import ProfileSnapshot, ResolutionGap, RuntimeEventDraft
from orchestrator.errors import AdapterStartFailedError, InvalidTaskActionError, OrchestrationError
from orchestrator.runtime import NodeDispatchRequest
from security.worktrees import WorktreeSpec


def node_id_or_node(repository: Any, task_id: str, node_id: str) -> Any:
    return next((n for n in repository.list_nodes(task_id) if n.id == node_id), None)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# 施工方案 §6.6 的通用执行流程，取一期能闭环的最小形态。
# reviewer 依赖 implementer：D7 要求同一 Agent 承担两者时必须换会话，
# 这条链正是用来验证那个约束的。
DEFAULT_WORKFLOW: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("general_implementer", ()),
    ("reviewer", ("general_implementer",)),
)


class TaskService:
    """TaskPort 的实现。"""

    available = True
    unavailable_reason = None

    def __init__(
        self,
        repository: Any,
        runtime: Any,
        directory: Any,
        profiles: Any,
        events: Any,
        workspaces: Any,
        worktrees: Any = None,
    ) -> None:
        self.repository = repository
        self.runtime = runtime
        self.directory = directory
        self.profiles = profiles
        self.events = events
        self.workspaces = workspaces
        self.worktrees = worktrees
        self._pumps: dict[str, asyncio.Task[None]] = {}
        # DispatchOutcome 要留着：collect_result 和 cancel 收的是它整体，
        # 里面带着 path_scope、role_policy、session 等收尾时才用得上的东西。
        self._outcomes: dict[str, Any] = {}
        # WorktreeSpec 留着做收尾时的越界复核（git diff --name-only）
        self._worktree_specs: dict[str, Any] = {}

    # ---------- 查询 ----------

    async def list_tasks(self, query: dict[str, Any]) -> PageResult:
        items, total = self.repository.list(query)
        page = max(int(query.get("page") or 1), 1)
        page_size = min(max(int(query.get("pageSize") or 50), 1), 200)
        return PageResult.model_validate(
            {
                "items": [item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in items],
                "total": total,
                "page": page,
                "pageSize": page_size,
                "hasMore": page * page_size < total,
            }
        )

    async def get_task(self, task_id: str) -> TaskDetailView:
        summary = self.repository.get(task_id)
        nodes = self.repository.list_nodes(task_id)
        events = await self.events.load_task_events(task_id)
        raw = summary.model_dump(mode="json", by_alias=True, exclude_none=True)
        raw.update(
            {
                "nodes": [n.model_dump(mode="json", by_alias=True, exclude_none=True) for n in nodes],
                "artifacts": [],
                "events": [e.model_dump(mode="json", by_alias=True, exclude_none=True) for e in events],
                "lastEventSeq": events[-1].seq if events else 0,
            }
        )
        return TaskDetailView.model_validate(raw)

    # ---------- 创建与推进 ----------

    async def create_task(self, value: CreateTaskInput, idempotency_key: str | None) -> TaskDetailView:
        profile = await self._profile_for(value)
        workspace = await self._workspace_for(value.workspace_id)
        # 裁决 D38 的准入检查放在建任务**之前**：工作流里但凡有一个写角色
        # 这个工作区承接不了，这个任务就永远跑不完。先建再失败只会留下一堆
        # 半截任务，用户还要一个个去清。
        self._assert_workflow_supported(workspace)
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        now = _now()
        task = TaskSummaryView.model_validate(
            {
                "id": task_id,
                "objective": value.objective,
                "workspaceId": value.workspace_id,
                "workspaceName": workspace["name"],
                "profileId": profile.id,
                "profileName": profile.name,
                "status": TaskStatus.QUEUED.value,
                "source": str(value.source) if value.source else "desktop",
                "createdAt": now,
                "updatedAt": now,
                "parentTaskId": value.parent_task_id,
            }
        )
        self.repository.save(task)
        await self._emit(task_id, "task.created", {"taskId": task_id, "objective": value.objective})

        # 先把整条链的节点落库为 pending，用户立刻能看到「要做几步、分别是什么角色」，
        # 而不是等第一个节点跑完才知道后面还有什么。
        for role_id, _deps in DEFAULT_WORKFLOW:
            self.repository.save_node(
                TaskNodeView.model_validate(
                    {
                        "id": f"node_{uuid.uuid4().hex[:12]}",
                        "taskId": task_id,
                        "roleId": role_id,
                        "resolvedAgentId": "",
                        "resolvedAgentName": "",
                        "resolveSource": "manual",
                        "status": NodeStatus.PENDING.value,
                    }
                )
            )

        await self._advance(task_id, value, profile, workspace)
        return await self.get_task(task_id)

    async def act(self, task_id: str, value: TaskActionInput, idempotency_key: str | None) -> TaskDetailView:
        task = self.repository.get(task_id)
        action = str(value.action)

        if action == "cancel":
            await self._cancel(task_id)
        elif action == "pause":
            # 裁决 D26：pause 只作用于节点之间，不打断正在执行的 Agent。
            self.repository.save(
                task.model_copy(update={"status": TaskStatus.PAUSED, "updated_at": _now()})
            )
            await self._emit(task_id, "task.status_changed", {"taskId": task_id, "to": "paused"})
        elif action == "resume":
            self.repository.save(
                task.model_copy(update={"status": TaskStatus.QUEUED, "updated_at": _now()})
            )
            await self._emit(task_id, "task.status_changed", {"taskId": task_id, "to": "queued"})
        elif action == "append_instruction":
            # 裁决 D26：只在节点 idle 时可用，运行中必须拒绝。
            if str(task.status) == "running":
                raise HubError(
                    "TASK_ACTION_INVALID",
                    "任务正在执行中，无法追加指令。Adapter Port 没有向运行中会话发消息的入口（裁决 D26）",
                    detail={"taskId": task_id, "status": str(task.status)},
                )
            if not value.instruction:
                raise HubError("VALIDATION_FAILED", "append_instruction 必须带 instruction")
        elif action == "retry":
            self.repository.save(
                task.model_copy(update={"status": TaskStatus.QUEUED, "updated_at": _now()})
            )
        else:
            raise HubError("TASK_ACTION_INVALID", f"不支持的动作：{action}")

        return await self.get_task(task_id)

    # ---------- 内部 ----------

    async def _profile_for(self, value: CreateTaskInput) -> Any:
        if value.profile_id:
            return await self.profiles.get_profile(value.profile_id)
        for profile in await self.profiles.list_profiles():
            if profile.is_default:
                return profile
        raise HubError(
            "VALIDATION_FAILED",
            "没有可用的 Team Profile，请先在团队配置里创建一个",
        )

    async def _workspace_for(self, workspace_id: str) -> dict[str, Any]:
        for item in await self.workspaces.list_workspaces(None, None):
            if getattr(item, "id", None) == workspace_id:
                capabilities = getattr(item, "capabilities", None)
                return {
                    "name": getattr(item, "name", workspace_id),
                    "path": getattr(item, "path", None),
                    "vcs": str(getattr(item, "vcs", "none")),
                    "can_write": bool(getattr(capabilities, "can_run_write_tasks", False)),
                    "reason": getattr(capabilities, "reason", None),
                }
        raise HubError(
            "NOT_FOUND",
            f"工作区不存在：{workspace_id}。请先在工作区页面把项目目录加进来",
            detail={"workspaceId": workspace_id},
        )

    def _assert_workflow_supported(self, workspace: dict[str, Any]) -> None:
        """默认工作流里的写角色，这个工作区能不能承接。"""
        if workspace.get("can_write"):
            return
        blocked = [
            role_id
            for role_id, _deps in DEFAULT_WORKFLOW
            if not self.runtime.permissions.role_policy(role_id).read_only
        ]
        if not blocked:
            return
        raise HubError(
            "PATH_NOT_ALLOWED",
            workspace.get("reason") or "该工作区不支持写任务",
            detail={
                "blockedRoles": blocked,
                "vcs": workspace.get("vcs"),
                "canInitGit": workspace.get("vcs") == "none",
            },
        )

    def _assert_can_write(self, role_id: str, workspace: dict[str, Any]) -> None:
        """裁决 D38：非 Git 工作区不能派写任务。

        判定放在分派前而不是等 Adapter 的 preflight 拒绝：Adapter 那边只能说
        「没有 worktreePath」，说不清「因为这个目录不是 Git 仓库，你可以点一键初始化」。
        错误要在知道原因的那一层抛出。
        """
        if workspace.get("can_write"):
            return
        policy = self.runtime.permissions.role_policy(role_id)
        if policy.read_only:
            return
        raise HubError(
            "PATH_NOT_ALLOWED",
            workspace.get("reason") or "该工作区不支持写任务",
            detail={
                "roleId": role_id,
                "vcs": workspace.get("vcs"),
                "canInitGit": workspace.get("vcs") == "none",
            },
        )

    async def _advance(self, task_id: str, value: CreateTaskInput, profile: Any, workspace: dict[str, Any]) -> None:
        """分派下一个就绪节点。"""
        nodes = list(self.repository.list_nodes(task_id))
        done = {str(n.role_id) for n in nodes if str(n.status) == "succeeded"}
        for node, (role_id, deps) in zip(nodes, DEFAULT_WORKFLOW):
            if str(node.status) != "pending":
                continue
            if not set(deps).issubset(done):
                continue
            await self._dispatch_node(task_id, node, role_id, value, profile, workspace)
            return

    async def _dispatch_node(
        self,
        task_id: str,
        node: TaskNodeView,
        role_id: str,
        value: CreateTaskInput,
        profile: Any,
        workspace: dict[str, Any],
    ) -> None:
        self._assert_can_write(role_id, workspace)
        worktree = await self._prepare_worktree(task_id, node, role_id, workspace)
        implementation_agent_id, review_context_paths = self._review_context(task_id, role_id)
        candidates = await self.directory.list_candidates()
        snapshot = ProfileSnapshot.from_view(profile)
        request = NodeDispatchRequest(
            task_id=task_id,
            node_id=node.id,
            workspace_id=value.workspace_id,
            workspace_name=workspace["name"],
            role_id=role_id,
            objective=value.objective,
            agents=tuple(candidates),
            allowed_paths=tuple(value.allowed_paths) if value.allowed_paths else None,
            read_first=tuple(value.read_first or ()),
            acceptance=tuple(value.acceptance or ()),
            requires_approval=tuple(str(a) for a in value.requires_approval) if value.requires_approval else None,
            global_profile=snapshot if str(profile.scope) == "global" else None,
            workspace_profile=snapshot if str(profile.scope) == "workspace" else None,
            worktree_path=worktree["path"] if worktree else None,
            branch=(worktree["branch"] or None) if worktree else None,
            base_commit=(worktree["base_commit"] or None) if worktree else None,
            # D7：同一 Agent 承担实现与复核时必须换会话。W3 靠 implementation_agent_id
            # 判断要不要强制隔离，靠 review_context_paths 保证复核方真去读了 diff，
            # 而不是凭上一轮对话的记忆「复核」自己刚写的代码。
            implementation_agent_id=implementation_agent_id,
            review_context_paths=review_context_paths,
        )
        try:
            outcome = await self.runtime.dispatch(request)
        except AdapterStartFailedError as error:
            # Agent 起不来是可处理的状态，不是崩溃。把 AdapterFailureKind
            # 原样写到节点上——前端要靠它区分「没登录」和「缺能力」，
            # 这两种的用户动作完全不同（去登录 vs 换 Agent）。
            failure = error.failure
            await self._fail_node(
                task_id,
                node,
                f"{getattr(failure, 'kind', 'agent_error')}: {getattr(failure, 'message', error)}",
            )
            return
        except OrchestrationError as error:
            await self._fail_node(task_id, node, str(error))
            return

        if isinstance(outcome, ResolutionGap):
            # 解析不出 Agent 不是崩溃，是要用户处理的状态。如实写进节点，
            # 前端据此显示「缺什么能力」而不是一句「失败」。
            await self._fail_node(task_id, node, outcome.reason)
            return

        self.repository.save_node(
            node.model_copy(
                update={
                    "status": NodeStatus.RUNNING,
                    "resolved_agent_id": outcome.resolution.agent.instance_id,
                    "resolved_agent_name": outcome.resolution.agent.display_name,
                    "resolve_source": outcome.resolution.source,
                    "is_fallback": outcome.resolution.is_fallback,
                    "fallback_reason": outcome.resolution.fallback_reason,
                    "session_id": outcome.session.id,
                    "external_session_id": outcome.session.external_session_id,
                    "worktree_path": outcome.worktree_path,
                    "started_at": _now(),
                }
            )
        )
        task = self.repository.get(task_id)
        self.repository.save(
            task.model_copy(
                update={
                    "status": TaskStatus.RUNNING,
                    "current_role": role_id,
                    "current_agent": outcome.resolution.agent.display_name,
                    "updated_at": _now(),
                }
            )
        )
        self._start_pump(task_id, node.id, outcome, value, profile, workspace)

    async def _prepare_worktree(
        self,
        task_id: str,
        node: TaskNodeView,
        role_id: str,
        workspace: dict[str, Any],
    ) -> dict[str, str] | None:
        """为写节点开一个独立 worktree（施工方案 §3.1 第 8 条、§6.7）。

        只读角色不开：reviewer 读的就是实现节点产出的那份，另开一个空 worktree
        反而看不到要复核的东西。
        """
        if self.worktrees is None or not workspace.get("path"):
            return None
        if self.runtime.permissions.role_policy(role_id).read_only:
            # 只读角色不新开 worktree，而是**复用前序写节点的那个**。
            # reviewer 要复核的就是实现节点刚产出的改动，另开一个干净 worktree
            # 等于让它去看一份没人动过的代码——那就没什么可审的了。
            return self._inherit_worktree(task_id)

        repository = Path(workspace["path"])
        base_commit = await self._head_commit(repository)
        branch = f"hq/{task_id}/{role_id}"
        path = self.worktrees.worktree_root / f"{task_id}-{role_id}"
        spec = WorktreeSpec(
            repository_path=repository,
            worktree_path=path,
            branch=branch,
            base_commit=base_commit,
        )
        created = await asyncio.to_thread(self.worktrees.create, spec)
        self._worktree_specs[node.id] = spec
        return {"path": str(created), "branch": branch, "base_commit": base_commit}

    def _review_context(self, task_id: str, role_id: str) -> tuple[str | None, tuple[str, ...]]:
        """复核节点要知道「谁实现的」和「去读哪里」。"""
        if not self.runtime.permissions.role_policy(role_id).read_only:
            return None, ()
        for previous in reversed(list(self.repository.list_nodes(task_id))):
            if str(previous.status) != "succeeded" or not previous.resolved_agent_id:
                continue
            paths = tuple(previous.changed_files or ()) or (".",)
            return previous.resolved_agent_id, paths
        return None, ()

    def _inherit_worktree(self, task_id: str) -> dict[str, str] | None:
        for previous in reversed(list(self.repository.list_nodes(task_id))):
            if previous.worktree_path and str(previous.status) == "succeeded":
                return {
                    "path": previous.worktree_path,
                    "branch": previous.branch or "",
                    "base_commit": "",
                }
        return None

    @staticmethod
    async def _head_commit(repository: Path) -> str:
        """解析出明确的 SHA。

        WorktreeManager 拒绝 HEAD 这类会飘的引用——并行任务必须能说清
        「我是从哪个提交出发的」，否则改动归属就乱了。
        """
        process = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD",
            cwd=str(repository),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()
        sha = stdout.decode("utf-8", "replace").strip()
        if process.returncode != 0 or not sha:
            raise HubError(
                "PATH_NOT_ALLOWED",
                "该仓库还没有任何提交，无法为写任务创建 worktree。"
                "请先在项目里做一次初始提交（git commit），再派写任务。",
                detail={"repository": str(repository)},
            )
        return sha

    async def _fail_node(self, task_id: str, node: TaskNodeView | None, reason: str) -> None:
        if node is None:
            return
        self.repository.save_node(
            node.model_copy(
                update={
                    "status": NodeStatus.FAILED,
                    "error": reason,
                    "completed_at": _now(),
                }
            )
        )
        task = self.repository.get(task_id)
        self.repository.save(
            task.model_copy(
                update={
                    "status": TaskStatus.FAILED,
                    "updated_at": _now(),
                }
            )
        )
        await self._emit(
            task_id,
            "task.status_changed",
            {"taskId": task_id, "to": "failed", "reason": reason},
        )

    def _start_pump(
        self,
        task_id: str,
        node_id: str,
        outcome: Any,
        value: CreateTaskInput,
        profile: Any,
        workspace: dict[str, Any],
    ) -> None:
        """后台抽取 Adapter 事件流，结束后收结果并推进下一个节点。

        用 asyncio.Task 而不是同步等待：dispatch 要立刻返回给 HTTP 调用方，
        Agent 可能跑几分钟到几十分钟。任务句柄留在 _pumps 里，
        取消时才有东西可取消。
        """
        self._outcomes[node_id] = outcome

        async def pump() -> None:
            adapter = self.directory.adapter_for(outcome.resolution.agent.instance_id)
            try:
                async for item in adapter.stream_events(outcome.session.id):
                    # 必须用 isinstance 判：AdapterEvent 和 AdapterStreamEnd 都没有 seq
                    # （全局 seq 归 Hub 分配，裁决 D32），靠有没有 seq 区分会把
                    # 每一条事件都当成流结束。
                    if isinstance(item, AdapterStreamEnd):
                        await self.runtime.handle_stream_end(outcome, item)
                        break
                    await self._forward(outcome, item)
                await self._complete_node(task_id, node_id, value, profile, workspace)
            except asyncio.CancelledError:
                raise
            except AdapterStartFailedError as error:
                failure = error.failure
                await self._fail_node(
                    task_id,
                    node_id_or_node(self.repository, task_id, node_id),
                    f"{getattr(failure, 'kind', 'agent_error')}: {getattr(failure, 'message', error)}",
                )
            except Exception as error:  # noqa: BLE001 - 抽取失败必须落到节点上，不能静默
                node = next((n for n in self.repository.list_nodes(task_id) if n.id == node_id), None)
                if node is not None:
                    self.repository.save_node(
                        node.model_copy(
                            update={"status": NodeStatus.FAILED, "error": str(error), "completed_at": _now()}
                        )
                    )
                task = self.repository.get(task_id)
                self.repository.save(
                    task.model_copy(update={"status": TaskStatus.FAILED, "updated_at": _now()})
                )
            finally:
                self._pumps.pop(node_id, None)
                self._outcomes.pop(node_id, None)

        self._pumps[node_id] = asyncio.create_task(pump())

    async def _forward(self, outcome: Any, event: Any) -> None:
        """把 Adapter 的内部事件补齐成 HubEvent 写进事件表。

        裁决 D32：AdapterEvent 故意不带 eventId / seq，由 Hub 在这里补。
        Adapter 直接产出 HubEvent 会把全局序号的所有权弄乱。
        """
        payload = event.payload
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json", by_alias=True, exclude_none=True)
        await self.events.append(
            RuntimeEventDraft(
                type=event.unified_type,
                aggregate_type="task",
                aggregate_id=outcome.task_id,
                payload=payload,
                task_id=outcome.task_id,
                node_id=outcome.node_id,
                role_id=outcome.role_id,
                agent_instance_id=outcome.resolution.agent.instance_id,
                adapter_id=outcome.resolution.agent.adapter_id,
            )
        )

    async def _complete_node(
        self,
        task_id: str,
        node_id: str,
        value: CreateTaskInput,
        profile: Any,
        workspace: dict[str, Any],
    ) -> None:
        node = next((n for n in self.repository.list_nodes(task_id) if n.id == node_id), None)
        outcome = self._outcomes.get(node_id)
        if node is None or outcome is None:
            return
        # collect_result 内部会调 adapter.collect_result 并按 path_scope 做后置越界复核
        # （裁决 D22 的第二道关口），所以这里不要自己再取一次结果。
        completion = await self.runtime.collect_result(outcome)
        result = completion.result
        violations = tuple(getattr(completion, "violation_paths", ()) or ())
        self.repository.save_node(
            node.model_copy(
                update={
                    "status": NodeStatus.FAILED if violations else NodeStatus.SUCCEEDED,
                    "output_summary": getattr(result, "summary", None),
                    "changed_files": [str(c) for c in (getattr(result, "changed_files", None) or [])],
                    "violation_paths": list(violations),
                    "completed_at": _now(),
                }
            )
        )
        if violations:
            task = self.repository.get(task_id)
            self.repository.save(
                task.model_copy(update={"status": TaskStatus.FAILED, "updated_at": _now()})
            )
            return

        remaining = [n for n in self.repository.list_nodes(task_id) if str(n.status) == "pending"]
        if remaining:
            await self._advance(task_id, value, profile, workspace)
            return
        task = self.repository.get(task_id)
        self.repository.save(
            task.model_copy(update={"status": TaskStatus.SUCCEEDED, "updated_at": _now()})
        )

    async def _cancel(self, task_id: str) -> None:
        for node in self.repository.list_nodes(task_id):
            if str(node.status) != "running" or not node.session_id:
                continue
            pump = self._pumps.pop(node.id, None)
            if pump is not None:
                pump.cancel()
            outcome = self._outcomes.get(node.id)
            if outcome is None:
                continue
            try:
                await self.runtime.cancel(outcome, reason="用户取消任务")
            except InvalidTaskActionError:
                raise
        task = self.repository.get(task_id)
        self.repository.save(
            task.model_copy(update={"status": TaskStatus.CANCELLED, "updated_at": _now()})
        )

    async def _emit(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        await self.events.append(
            RuntimeEventDraft(
                type=event_type,
                aggregate_type="task",
                aggregate_id=task_id,
                payload=payload,
                task_id=task_id,
            )
        )


class SessionService:
    """SessionPort：列出与恢复会话。"""

    available = True
    unavailable_reason = None

    def __init__(self, repository: Any, manager: Any) -> None:
        self.repository = repository
        self.manager = manager

    async def list_sessions(self, query: dict[str, Any]) -> Sequence[Any]:
        return await self.repository.list(query)

    async def resume(self, session_id: str, value: Any) -> Any:
        session = await self.repository.get(session_id)
        if session is None:
            raise HubError("NOT_FOUND", f"Session 不存在：{session_id}")
        if not session.is_valid:
            raise HubError(
                "SESSION_NOT_RESUMABLE",
                "该会话不可恢复：Agent 未提供可用的外部会话 ID（裁决 D28）",
                detail={"sessionId": session_id},
            )
        return await self.manager.resume(session, getattr(value, "message", "") or "", None)


class ApprovalService:
    """ApprovalPort：列出与回应审批。"""

    available = True
    unavailable_reason = None

    def __init__(self, repository: Any, coordinator: Any) -> None:
        self.repository = repository
        self.coordinator = coordinator

    async def list_approvals(self, query: dict[str, Any]) -> Sequence[Any]:
        return await self.repository.list({k: v for k, v in query.items() if v})

    async def respond(self, approval_id: str, value: Any, idempotency_key: str | None) -> Any:
        return await self.coordinator.decide(approval_id, value)
