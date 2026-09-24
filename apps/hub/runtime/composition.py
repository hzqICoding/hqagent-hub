"""Composition Root：把 W2 / W3 的实现装配成 W1 的 Port。

放在 runtime/ 而不是 api/ 或 core/，是因为这里是**唯一**知道所有包存在的地方。
core 和 api 只认 core.ports 里的 Protocol，反过来 adapters / orchestrator /
security 也不知道 Hub 长什么样。装配点集中在一处，谁没接上一眼就能看出来。

分两步：`build_ports()` 先给出不需要数据库的部分，`bind_ports()` 在
`create_application()` 建好 Database 之后补齐其余。这是仓库里已有的模式
（见 tests/conftest.py 的 DeferredTaskPort），不另发明一套。

还没具备条件的 Port 继续留 UnavailablePort，并**说明差什么**——
`BootstrapView.features` 会把这些原因发给前端，前端据此禁用入口并显示原因，
而不是渲染成「功能可用但没数据」（W4 任务书明确要求）。
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.errors import FeatureUnavailable
from core.ports import HubPorts, UnavailablePort


class _DeferredTeamProfilePort:
    """占位到 Database 就绪为止。绑定前调用一律 FeatureUnavailable，不假装可用。"""

    def __init__(self) -> None:
        self._delegate: Any | None = None

    def bind(self, delegate: Any) -> None:
        self._delegate = delegate

    @property
    def available(self) -> bool:
        return self._delegate is not None and self._delegate.available

    @property
    def unavailable_reason(self) -> str | None:
        if self._delegate is None:
            return "Team Profile 存储尚未初始化"
        return self._delegate.unavailable_reason

    def __getattr__(self, name: str) -> Any:
        delegate = self.__dict__.get("_delegate")
        if delegate is None:
            async def unavailable(*_args: Any, **_kwargs: Any) -> Any:
                raise FeatureUnavailable("teamProfiles", "Team Profile 存储尚未初始化")

            return unavailable
        return getattr(delegate, name)


def build_ports() -> HubPorts:
    """装配不依赖数据库的 Port，其余留待 bind_ports 补齐。"""
    ports = HubPorts.unavailable_defaults()
    ports = replace(ports, agents=_build_agent_port())
    if ports.agents.available:
        ports = replace(ports, team_profiles=_DeferredTeamProfilePort())
    return ports


async def bind_ports(application: Any, ports: HubPorts) -> None:
    """Database 就绪后补齐剩余 Port，并做首次启动的默认数据种子。"""
    port = ports.team_profiles
    if not isinstance(port, _DeferredTeamProfilePort):
        return
    _bind_workspaces(application, ports)
    service = _build_team_profile_service(application.database, ports.agents)
    if service is None:
        return
    port.bind(service)
    await _seed_defaults(application.database, ports)
    _bind_orchestration(application, ports, service)


def _build_agent_port():
    """W2 的 AdapterManager 直接就是 AgentPort 的实现。

    导入放在函数里而不是模块顶层：Adapter 会去探测本机 CLI，
    导入失败不该让整个 Hub 起不来——探测不到 Agent 是可恢复状态，
    Hub 起不来不是。
    """
    try:
        from adapters.builtins import builtin_runtimes
        from adapters.manager import AdapterManager
    except ImportError as error:  # pragma: no cover - 打包漏文件时才会走到
        return UnavailablePort("agents", f"Agent 适配层未随产物打包：{error}")

    return AdapterManager(builtin_runtimes().instantiate())


def _build_team_profile_service(database: Any, agents: Any):
    """W3 的 TeamResolver + W1 侧的薄仓储。

    依赖 agents：解析要拿本机实际探测到的 Agent 做能力匹配。
    """
    try:
        from orchestrator.catalog import BuiltinCatalog
        from orchestrator.role_resolver import RoleResolver
        from orchestrator.team_resolver import TeamResolver
        from runtime.services import TeamProfileService
        from storage.team_profiles import TeamProfileRepository
    except ImportError:  # pragma: no cover - 打包漏文件时才会走到
        return None

    catalog = BuiltinCatalog.load()
    return TeamProfileService(
        TeamProfileRepository(database),
        TeamResolver(catalog, RoleResolver(catalog)),
        agents,
    )


async def _seed_defaults(database: Any, ports: HubPorts) -> None:
    """首次启动时按探测结果生成默认 Team Profile。

    放在这里而不是仓储层：这是**启动策略**，不是存储行为。
    仓储不该知道「首次启动要不要造点东西出来」。
    """
    from runtime.services import seed_default_profile
    from storage.team_profiles import TeamProfileRepository

    try:
        agents = await ports.agents.list_agents()
    except Exception:  # noqa: BLE001 - 探测失败不该阻断启动
        return
    seed_default_profile(TeamProfileRepository(database), list(agents))


def _bind_orchestration(application: Any, ports: HubPorts, profiles: Any) -> None:
    """接 tasks / sessions / approvals 三个 Port。

    这三个是一组：任务推进要发事件、要开会话、要走审批，拆开接会出现
    「任务能建但审批发不出去」这种半通状态。要么整组通，要么整组留占位。
    """
    from dataclasses import replace as _replace

    try:
        from orchestrator.catalog import BuiltinCatalog
        from orchestrator.role_resolver import RoleResolver
        from orchestrator.runtime import WorkflowRuntime
        from orchestrator.sessions import SessionManager
        from runtime.repositories import (
            AdapterDirectory,
            ApprovalRepository,
            EventSink,
            SessionRepository,
        )
        from runtime.tasks import ApprovalService, SessionService, TaskService
        from security.approvals import ApprovalCoordinator
        from security.permissions import PermissionEngine
        from security.worktrees import WorktreeManager
        from storage.tasks import TaskRepository
    except ImportError:  # pragma: no cover - 打包漏文件时才会走到
        return

    database = application.database
    catalog = BuiltinCatalog.load()
    directory = AdapterDirectory(ports.agents)
    events = EventSink(database, application.events)
    session_repository = SessionRepository(database)
    approval_repository = ApprovalRepository(database)

    session_manager = SessionManager(session_repository, directory)
    workflow = WorkflowRuntime(
        RoleResolver(catalog),
        PermissionEngine(catalog),
        session_manager,
        directory,
        events,
    )
    coordinator = ApprovalCoordinator(approval_repository, events, directory)

    ports_tasks = TaskService(
        TaskRepository(database),
        workflow,
        directory,
        profiles,
        events,
        ports.workspaces,
        WorktreeManager(application.paths.worktrees),
        approval_coordinator=coordinator,
    )
    # HubPorts 是 slots dataclass，就地改字段而不是 replace——
    # api 层持有的是同一个 ports 引用，replace 出来的新对象它看不见。
    ports.tasks = ports_tasks
    ports.sessions = SessionService(session_repository, session_manager)
    ports.approvals = ApprovalService(approval_repository, coordinator)


def _bind_workspaces(application: Any, ports: HubPorts) -> None:
    """接 workspaces Port。

    独立于 agents：就算一个 Agent 都探测不到，用户也应该能先把项目目录加进来。
    """
    try:
        from runtime.workspaces import WorkspaceService
        from storage.workspaces import WorkspaceRepository
    except ImportError:  # pragma: no cover - 打包漏文件时才会走到
        return
    ports.workspaces = WorkspaceService(WorkspaceRepository(application.database))
