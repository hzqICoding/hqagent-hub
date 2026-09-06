from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any, Iterable

from protocol.generated.python import FileChange


_ABSOLUTE_WINDOWS_PATH = re.compile(r"(?i)([a-z]:[\\/][^\s\"'|;&<>]+)")
_WRITE_COMMAND = re.compile(
    r"(?i)(?:\bset-content\b|\badd-content\b|\bout-file\b|\bremove-item\b|"
    r"\bmove-item\b|\bcopy-item\b|\bnew-item\b|\bdel\b|\berase\b|"
    r"\brm\b|\bmv\b|\bcp\b|\btouch\b|\bmkdir\b|\bgit\s+(?:apply|clean|checkout|"
    r"reset|merge|cherry-pick)\b|(?<![<])>{1,2}(?![>]))"
)


class PathGuard:
    def __init__(self, worktree_path: str, allowed_paths: Iterable[str]) -> None:
        self.root = Path(worktree_path).resolve()
        self.patterns = tuple(self._normalise_pattern(item) for item in allowed_paths)

    @staticmethod
    def _normalise_pattern(pattern: str) -> str:
        value = pattern.replace("\\", "/").lstrip("./")
        return value or "__never_match__"

    def _relative(self, candidate: str) -> str | None:
        path = Path(candidate)
        if not path.is_absolute():
            path = self.root / path
        try:
            relative = path.resolve(strict=False).relative_to(self.root)
        except ValueError:
            return None
        return relative.as_posix()

    def allows(self, candidate: str) -> bool:
        relative = self._relative(candidate)
        if relative is None:
            return False
        for pattern in self.patterns:
            if pattern.endswith("/**"):
                prefix = pattern[:-3].rstrip("/")
                if relative == prefix or relative.startswith(prefix + "/"):
                    return True
            if fnmatch.fnmatchcase(relative, pattern):
                return True
        return False

    def violations(self, candidates: Iterable[str]) -> list[str]:
        return [item for item in candidates if not self.allows(item)]

    def inspect_tool_call(self, tool_name: str, tool_input: dict[str, Any]) -> list[str]:
        candidates = list(self._extract_paths(tool_input))
        violations = self.violations(candidates)
        if violations:
            return violations
        if tool_name.lower() in {"bash", "powershell", "shell", "exec_command"}:
            command = str(tool_input.get("command") or tool_input.get("cmd") or "")
            absolute_paths = _ABSOLUTE_WINDOWS_PATH.findall(command)
            violations = self.violations(absolute_paths)
            if violations:
                return violations
            if _WRITE_COMMAND.search(command) and not absolute_paths:
                return ["<unresolved shell write target>"]
        return []

    def validate_changes(self, changes: Iterable[FileChange] | None) -> list[str]:
        if not changes:
            return []
        return self.violations(change.path for change in changes)

    @classmethod
    def _extract_paths(cls, value: Any) -> Iterable[str]:
        if isinstance(value, dict):
            for key, item in value.items():
                lowered = key.lower()
                if lowered in {
                    "path",
                    "file_path",
                    "filepath",
                    "grantroot",
                    "target",
                    "renamedfrom",
                } and isinstance(item, str):
                    yield item
                else:
                    yield from cls._extract_paths(item)
        elif isinstance(value, list):
            for item in value:
                yield from cls._extract_paths(item)
