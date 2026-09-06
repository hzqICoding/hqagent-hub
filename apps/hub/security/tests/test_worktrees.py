from pathlib import Path

import pytest

from orchestrator.errors import InvalidTaskActionError
from security.paths import PathScope
from security.worktrees import WorktreeManager, WorktreeSpec


class FakeGitRunner:
    def __init__(self) -> None:
        self.calls = []

    def run(self, args, *, cwd: Path) -> str:
        self.calls.append((tuple(args), cwd))
        if args[:2] == ["diff", "--name-only"]:
            return "apps/hub/orchestrator/runtime.py\napps/hub/core/ports.py\n"
        if args[:2] == ["ls-files", "--others"]:
            return "apps/hub/security/new.py\n"
        return ""


def test_worktree_validation_checks_both_path_layers(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    worktree_root = tmp_path / "worktrees"
    worktree = worktree_root / "task"
    worktree.mkdir(parents=True)
    runner = FakeGitRunner()
    manager = WorktreeManager(worktree_root, runner)
    spec = WorktreeSpec(repository, worktree, "work/task", "a" * 40)
    scope = PathScope.build(
        ("apps/hub/orchestrator/**", "apps/hub/security/**"),
        ("apps/hub/**",),
    )

    validation = manager.validate(spec, scope)

    assert validation.changed_files == (
        "apps/hub/orchestrator/runtime.py",
        "apps/hub/core/ports.py",
        "apps/hub/security/new.py",
    )
    assert validation.violation_paths == ("apps/hub/core/ports.py",)


def test_create_rejects_worktree_outside_configured_root(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    manager = WorktreeManager(tmp_path / "allowed", FakeGitRunner())
    spec = WorktreeSpec(repository, tmp_path / "outside", "work/task", "b" * 40)

    with pytest.raises(InvalidTaskActionError):
        manager.create(spec)
