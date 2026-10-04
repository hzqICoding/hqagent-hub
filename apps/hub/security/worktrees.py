from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from orchestrator.errors import InvalidTaskActionError

from .paths import PathScope


_SAFE_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_SAFE_COMMIT = re.compile(r"^[A-Fa-f0-9]{7,64}$")


class GitRunner(Protocol):
    def run(self, args: Sequence[str], *, cwd: Path) -> str: ...


class SubprocessGitRunner:
    def run(self, args: Sequence[str], *, cwd: Path) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=30,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return completed.stdout


@dataclass(frozen=True, slots=True)
class WorktreeSpec:
    repository_path: Path
    worktree_path: Path
    branch: str
    base_commit: str


@dataclass(frozen=True, slots=True)
class WorktreeValidation:
    changed_files: tuple[str, ...]
    violation_paths: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.violation_paths


class WorktreeManager:
    def __init__(self, worktree_root: Path, runner: GitRunner | None = None) -> None:
        self.worktree_root = worktree_root.resolve()
        self.runner = runner or SubprocessGitRunner()

    def create(self, spec: WorktreeSpec) -> Path:
        repository = spec.repository_path.resolve()
        worktree = spec.worktree_path.resolve()
        if not repository.is_dir():
            raise InvalidTaskActionError("Git 仓库目录不存在", path=str(repository))
        try:
            worktree.relative_to(self.worktree_root)
        except ValueError as exc:
            raise InvalidTaskActionError(
                "worktree 路径超出配置根目录",
                path=str(worktree),
                root=str(self.worktree_root),
            ) from exc
        if worktree.exists():
            raise InvalidTaskActionError("worktree 目标已存在", path=str(worktree))
        if not _SAFE_BRANCH.fullmatch(spec.branch) or ".." in spec.branch or "//" in spec.branch:
            raise InvalidTaskActionError("分支名不安全", branch=spec.branch)
        if not _SAFE_COMMIT.fullmatch(spec.base_commit):
            raise InvalidTaskActionError("baseCommit 必须是明确 Git SHA", baseCommit=spec.base_commit)

        self.runner.run(
            ["worktree", "add", "-b", spec.branch, str(worktree), spec.base_commit],
            cwd=repository,
        )
        return worktree

    def changed_files(self, spec: WorktreeSpec) -> tuple[str, ...]:
        worktree = spec.worktree_path.resolve()
        tracked = self.runner.run(
            ["diff", "--name-only", "--relative", spec.base_commit, "--"],
            cwd=worktree,
        )
        untracked = self.runner.run(
            ["ls-files", "--others", "--exclude-standard"],
            cwd=worktree,
        )
        result: list[str] = []
        for line in [*tracked.splitlines(), *untracked.splitlines()]:
            path = line.strip().replace("\\", "/")
            if path and path not in result:
                result.append(path)
        return tuple(result)

    def validate(self, spec: WorktreeSpec, scope: PathScope) -> WorktreeValidation:
        changed = self.changed_files(spec)
        result = scope.validate(changed)
        return WorktreeValidation(changed, result.violation_paths)
