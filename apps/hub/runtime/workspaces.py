"""WorkspacePort 的实现：受管目录的增删查，以及裁决 D38 的能力判定。

Git 状态（是不是仓库、当前分支、干不干净）一律**读时现算**，不落库。
用户在 VS Code 里切个分支，库里的值立刻就是错的——而这个值要用来决定
「能不能派写任务」，错了就是安全问题。
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import time
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from protocol.generated.python import AddWorkspaceInput, WorkspaceView

from core.errors import HubError
from adapters.process import terminate_process_tree
from storage.workspaces import WorkspaceRecord, WorkspaceRepository

# 裁决 D38：非 Git 目录是合法工作区，但拿不到 worktree 隔离，只能派只读任务。
NOT_A_GIT_REPO_REASON = (
    "该目录不是 Git 仓库，无法为写任务创建独立 worktree。"
    "没有版本控制就无法做 allowed_paths 越界校验，也无法在 Agent 出错时回滚。"
    "可以点「初始化 Git」把它变成仓库，或只派只读任务。"
)
GIT_TIMEOUT_SECONDS = 2.0
WORKSPACE_QUERY_SECONDS = 3.0
GIT_STATE_UNKNOWN_REASON = "Git 状态暂时无法确认，请稍后重试；当前仅允许只读任务。"


async def _stop_git(process):
    """Reap the owned process tree without extending the query indefinitely."""
    try:
        await asyncio.wait_for(terminate_process_tree(process, timeout=0.3), 1)
    except TimeoutError:
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def _git(cwd: Path, *args: str) -> tuple[int, str]:
    """跑一条 git 命令，返回 (退出码, stdout)。

    不抛异常：调用方要区分「不是仓库」和「git 没装」，而这两种都会非零退出。
    """
    try:
        process = None
        async with asyncio.timeout(GIT_TIMEOUT_SECONDS):
            process = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=str(cwd),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                start_new_session=os.name != 'nt',
            )
            stdout, _ = await process.communicate()
    except FileNotFoundError:
        return 127, ""
    except TimeoutError:
        if process is not None:
            await _stop_git(process)
        return 124, ""
    except asyncio.CancelledError:
        if process is not None:
            await _stop_git(process)
        raise
    return process.returncode or 0, stdout.decode("utf-8", "replace").strip()


class WorkspaceService:
    """WorkspacePort 的实现。"""

    available = True
    unavailable_reason = None

    def __init__(self, repository: WorkspaceRepository) -> None:
        self.repository = repository
        self._views = {}

    async def cached_workspaces(self):
        """Bootstrap metadata snapshot. Git probes belong to background refresh."""
        result = []
        for record in self.repository.list():
            cached = self._views.get(record.id)
            if cached and time.monotonic() - cached[0] < 5 and cached[1].path == record.path and str(cached[1].vcs) == record.vcs:
                result.append(cached[1].model_copy(update={'name': record.name,
                    'default_profile_id': record.default_profile_id, 'last_opened_at': record.last_opened_at or cached[1].last_opened_at}))
            else:
                result.append(self._view(record, unknown=record.vcs == 'git'))
        return result

    # ---------- 查询 ----------

    async def list_workspaces(
        self, search: str | None = None, limit: int | None = None
    ) -> Sequence[WorkspaceView]:
        records = self.repository.list(search, limit)
        # One request budget, not N workspaces times N git timeouts. Return all
        # records and preserve the count even when live VCS facts are unknown.
        deadline = asyncio.get_running_loop().time() + WORKSPACE_QUERY_SECONDS
        return [await self._bounded_view(record, deadline - asyncio.get_running_loop().time()) for record in records]

    async def get_workspace(self, workspace_id: str) -> WorkspaceView:
        return await self._bounded_view(self.repository.get(workspace_id), WORKSPACE_QUERY_SECONDS)

    # ---------- 变更 ----------

    async def add_workspace(self, value: AddWorkspaceInput, *, commit=None) -> WorkspaceView:
        path = Path(value.path).expanduser()
        if not path.is_absolute():
            raise HubError("VALIDATION_FAILED", "工作区路径必须是绝对路径", detail={"path": value.path})
        if not path.is_dir():
            raise HubError("NOT_FOUND", "目录不存在", detail={"path": str(path)})

        resolved = str(path.resolve())
        existing = self.repository.find_by_path(resolved)
        if existing is not None:
            # 重复添加不报错，返回已有的那个并刷新打开时间——
            # 用户的意图是「我要用这个目录」，它已经在管了就是成功。
            existing.last_opened_at = _now()
            return await self._to_view(commit(existing) if commit else self.repository.save(existing))

        record = WorkspaceRecord(
            id=f"ws_{uuid.uuid4().hex[:12]}",
            path=resolved,
            name=value.name or path.name,
            # vcs 由 Hub 探测，不接受调用方声明——声明和事实不符时，
            # 写任务的隔离保护就成了摆设。
            vcs="git" if await self._is_git_repo(path) else "none",
            default_profile_id=value.default_profile_id,
            last_opened_at=_now(),
        )
        return await self._to_view(commit(record) if commit else self.repository.save(record))

    async def remove_workspace(self, workspace_id: str) -> None:
        self.repository.get(workspace_id)  # 不存在时抛 NOT_FOUND
        # 只解除管理关系，磁盘上一个字节都不动。
        self.repository.delete(workspace_id)

    async def init_git(self, workspace_id: str) -> WorkspaceView:
        """裁决 D38 的 C 项：一键把工作区变成 Git 仓库。"""
        record = self.repository.get(workspace_id)
        path = Path(record.path)
        if await self._is_git_repo(path):
            record.vcs = "git"
            return await self._to_view(self.repository.save(record))

        code, _ = await _git(path, "init")
        if code == 127:
            raise HubError(
                "FEATURE_UNAVAILABLE",
                "本机找不到 git 命令，无法初始化仓库",
                detail={"path": record.path},
            )
        if code != 0 or not await self._is_git_repo(path):
            raise HubError("INTERNAL", "git init 失败", detail={"path": record.path})

        record.vcs = "git"
        return await self._to_view(self.repository.save(record))

    async def init_memory(self, workspace_id: str) -> WorkspaceView:
        """建 .hqagent/ 共享记忆目录（施工方案 §5.5）。"""
        record = self.repository.get(workspace_id)
        (Path(record.path) / ".hqagent").mkdir(parents=True, exist_ok=True)
        return await self._to_view(record)

    # ---------- 内部 ----------

    @staticmethod
    async def _is_git_repo(path: Path) -> bool:
        code, out = await _git(path, "rev-parse", "--is-inside-work-tree")
        return code == 0 and out == "true"

    async def _to_view(self, record: WorkspaceRecord) -> WorkspaceView:
        path = Path(record.path)
        exists = path.is_dir()
        branch: str | None = None
        is_clean: bool | None = None
        vcs = record.vcs

        if exists and vcs == "git":
            # 每次都重新确认它还是不是仓库：用户可能把 .git 删了。
            code, inside = await _git(path, "rev-parse", "--is-inside-work-tree")
            if code in {124, 127}:
                return self._view(record, unknown=True)
            if code == 0 and inside == 'true':
                # 用 --show-current 而不是 rev-parse --abbrev-ref HEAD：
                # 刚 init 出来的仓库还没有第一个提交，后者会返回字面量 "HEAD"，
                # 界面上就成了「当前分支：HEAD」。
                code, branch = await _git(path, "branch", "--show-current")
                if code != 0:
                    return self._view(record, unknown=True)
                code, status = await _git(path, "status", "--porcelain")
                if code != 0:
                    return self._view(record, unknown=True)
                is_clean = not status
            else:
                vcs = "none"

        return self._view(record, exists=exists, vcs=vcs, branch=branch, is_clean=is_clean)

    async def _bounded_view(self, record, budget):
        if budget > 0:
            try:
                async with asyncio.timeout(budget):
                    value = await self._to_view(record)
                    self._views[record.id] = (time.monotonic(), value)
                    return value
            except TimeoutError:
                pass
        return self._view(record, unknown=True)

    @staticmethod
    def _view(record, *, exists=None, vcs=None, branch=None, is_clean=None, unknown=False):
        path = Path(record.path)
        exists = path.is_dir() if exists is None else exists
        vcs = record.vcs if vcs is None else vcs
        can_write = exists and vcs == "git" and not unknown
        if not exists:
            reason = "目录不存在或已被移动"
        elif unknown:
            reason = GIT_STATE_UNKNOWN_REASON
        elif vcs != "git":
            reason = NOT_A_GIT_REPO_REASON
        else:
            reason = None

        raw: dict[str, object] = {
            "id": record.id,
            "name": record.name,
            "path": record.path,
            "vcs": vcs,
            "lastOpenedAt": record.last_opened_at or _now(),
            "memoryDirPresent": exists and (path / ".hqagent").is_dir(),
            "capabilities": {
                "canRunWriteTasks": can_write,
                "reason": reason,
                "canInitGit": exists and vcs != "git" and not unknown,
            },
        }
        if record.default_profile_id:
            raw["defaultProfileId"] = record.default_profile_id
        if branch:
            raw["branch"] = branch
        if is_clean is not None:
            raw["isClean"] = is_clean
        return WorkspaceView.model_validate(raw)
