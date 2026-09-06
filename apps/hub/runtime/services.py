"""薄 Port 适配器：把 W2/W3 的实现接到 W1 的 core.ports Protocol 上。

W3 的 handoff 第 4 条点名要的就是这一层——「W1 当前 core.ports 是 API Handler
Port，没有面向 W3 的事务化 Repository Port，集成时需由 W1 在其路径提供薄适配器，
复用现有 Database/EventStore；不要在 W3 再建 SQLite 或第二套事件表」。

这里只做形状转换和装配，不放业务规则。任何判断逻辑都应该在 orchestrator /
security 里，否则规则会分裂成两处。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from protocol.generated.python import (
    AgentView,
    ResolveTeamProfileInput,
    ResolvedTeamView,
    SaveTeamProfileInput,
    TeamProfileView,
)

from core.errors import HubError
from core.ports import AgentPort
from orchestrator.domain import AgentCandidate
from orchestrator.team_resolver import TeamResolver
from storage.team_profiles import TeamProfileRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TeamProfileService:
    """TeamProfilePort 的实现：仓储 + W3 的 TeamResolver。"""

    available = True
    unavailable_reason = None

    def __init__(
        self,
        repository: TeamProfileRepository,
        resolver: TeamResolver,
        agents: AgentPort,
    ) -> None:
        self.repository = repository
        self.resolver = resolver
        self.agents = agents

    async def list_profiles(self) -> list[TeamProfileView]:
        return self.repository.list()

    async def get_profile(self, profile_id: str) -> TeamProfileView:
        return self.repository.get(profile_id)

    async def save_profile(self, profile_id: str, value: SaveTeamProfileInput) -> TeamProfileView:
        # 路由参数是权威的 id。请求体里的 id 只在创建时用来自带 id，
        # 与路由不一致时按路由走并明确报错，不静默覆盖——静默覆盖会让
        # 「我明明改了 A 结果 B 变了」这类问题无从查起。
        body_id = getattr(value, "id", None)
        if body_id and body_id != profile_id:
            raise HubError(
                "VALIDATION_FAILED",
                "请求体里的 profile id 与路由不一致",
                detail={"routeId": profile_id, "bodyId": body_id},
            )
        raw = value.model_dump(mode="json", by_alias=True, exclude_none=True)
        raw["id"] = profile_id
        raw.setdefault("isDefault", False)
        raw["updatedAt"] = _now()
        return self.repository.save(TeamProfileView.model_validate(raw))

    async def resolve(self, value: ResolveTeamProfileInput) -> ResolvedTeamView:
        profile = self.repository.get(value.profile_id)
        agents = await self.agents.list_agents()
        candidates = [AgentCandidate.from_view(item) for item in agents if isinstance(item, AgentView)]
        global_profile = None
        if str(profile.scope) == "workspace":
            global_profile = self.repository.default_global()
        return self.resolver.resolve(
            profile,
            candidates,
            global_profile=global_profile,
            workspace_id=value.workspace_id,
        )


def seed_default_profile(repository: TeamProfileRepository, agents: list[Any]) -> TeamProfileView | None:
    """首次启动时按探测到的 Agent 生成一份默认全局 Profile。

    没有这个的话，前端 /teams 页永远是空列表——用户看不出「还没配」和
    「配了但坏了」的区别，也没有任何入口能开始用。

    只在库里一条 Profile 都没有时执行；探测不到 Agent 就不生成，
    宁可让用户看到空列表加提示，也不要造一份指向不存在实例的配置。
    """
    if repository.list():
        return None
    ready = [a for a in agents if str(getattr(a, "status", "")) == "ready"]
    if not ready:
        return None

    from orchestrator.catalog import BuiltinCatalog

    catalog = BuiltinCatalog.load()
    primary = ready[0]
    fallbacks = [a.id for a in ready[1:]]
    bindings = {
        role_id: {
            "roleId": role_id,
            "roleName": definition.display_name,
            "primaryAgentId": primary.id,
            "fallbackAgentIds": fallbacks,
        }
        for role_id, definition in catalog.roles.items()
    }
    return repository.save(
        TeamProfileView.model_validate(
            {
                "id": f"profile_{uuid.uuid4().hex[:12]}",
                "name": "默认团队",
                "description": "首次启动时按本机探测到的 Agent 自动生成，可随时修改",
                "scope": "global",
                "isDefault": True,
                "roleBindings": bindings,
                "updatedAt": _now(),
            }
        )
    )
