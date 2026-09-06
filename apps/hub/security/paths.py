from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable


_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


def normalize_repo_path(value: str) -> str:
    path = value.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if not path or path.startswith("/") or _DRIVE_PREFIX.match(path):
        raise ValueError(f"路径必须是仓库内相对路径：{value}")
    parts = PurePosixPath(path).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"路径包含不安全片段：{value}")
    return "/".join(parts)


def normalize_glob(value: str) -> str:
    pattern = value.strip().replace("\\", "/")
    while pattern.startswith("./"):
        pattern = pattern[2:]
    if pattern == "**":
        return pattern
    if not pattern or pattern.startswith("/") or _DRIVE_PREFIX.match(pattern):
        raise ValueError(f"glob 必须是仓库内相对路径：{value}")
    if any(part == ".." for part in pattern.split("/")):
        raise ValueError(f"glob 包含不安全片段：{value}")
    return pattern.rstrip("/")


def _glob_regex(pattern: str) -> re.Pattern[str]:
    pattern = normalize_glob(pattern)
    pieces: list[str] = ["^"]
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 2
                if index < len(pattern) and pattern[index] == "/":
                    pieces.append("(?:.*/)?")
                    index += 1
                else:
                    pieces.append(".*")
                continue
            pieces.append("[^/]*")
        elif character == "?":
            pieces.append("[^/]")
        else:
            pieces.append(re.escape(character))
        index += 1
    pieces.append("$")
    return re.compile("".join(pieces), re.IGNORECASE)


def matches_glob(path: str, pattern: str) -> bool:
    return bool(_glob_regex(pattern).match(normalize_repo_path(path)))


def _static_prefix(pattern: str) -> str:
    normalized = normalize_glob(pattern)
    wildcard_indexes = [
        index for index in (normalized.find("*"), normalized.find("?")) if index >= 0
    ]
    if not wildcard_indexes:
        return normalized
    prefix = normalized[: min(wildcard_indexes)]
    return prefix.rsplit("/", 1)[0] if "/" in prefix else ""


def pattern_is_subset(candidate: str, container: str) -> bool:
    candidate = normalize_glob(candidate)
    container = normalize_glob(container)
    if candidate == container or container == "**":
        return True
    if "*" not in candidate and "?" not in candidate:
        return matches_glob(candidate, container)
    if container.endswith("/**"):
        container_root = container[:-3].rstrip("/")
        candidate_prefix = _static_prefix(candidate)
        return candidate_prefix == container_root or candidate_prefix.startswith(container_root + "/")
    return False


def intersect_patterns(first: Iterable[str], second: Iterable[str]) -> tuple[str, ...]:
    """Return a conservative glob representation of two whitelist layers.

    If an overlap cannot be represented by one of the original globs, it is
    omitted. Post-run validation still checks both original layers.
    """

    result: list[str] = []
    left = tuple(normalize_glob(item) for item in first)
    right = tuple(normalize_glob(item) for item in second)
    for first_pattern in left:
        for second_pattern in right:
            if pattern_is_subset(first_pattern, second_pattern):
                narrower = first_pattern
            elif pattern_is_subset(second_pattern, first_pattern):
                narrower = second_pattern
            else:
                continue
            if narrower not in result:
                result.append(narrower)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class PathValidationResult:
    allowed_paths: tuple[str, ...]
    violation_paths: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.violation_paths


@dataclass(frozen=True, slots=True)
class PathScope:
    role_patterns: tuple[str, ...]
    task_patterns: tuple[str, ...]

    @classmethod
    def build(cls, role_patterns: Iterable[str], task_patterns: Iterable[str]) -> "PathScope":
        return cls(
            role_patterns=tuple(normalize_glob(item) for item in role_patterns),
            task_patterns=tuple(normalize_glob(item) for item in task_patterns),
        )

    @property
    def adapter_patterns(self) -> tuple[str, ...]:
        return intersect_patterns(self.role_patterns, self.task_patterns)

    def allows(self, path: str) -> bool:
        normalized = normalize_repo_path(path)
        return bool(self.role_patterns and self.task_patterns) and any(
            matches_glob(normalized, pattern) for pattern in self.role_patterns
        ) and any(matches_glob(normalized, pattern) for pattern in self.task_patterns)

    def validate(self, paths: Iterable[str]) -> PathValidationResult:
        allowed: list[str] = []
        violations: list[str] = []
        for raw_path in paths:
            try:
                path = normalize_repo_path(raw_path)
            except ValueError:
                path = raw_path.replace("\\", "/")
                violations.append(path)
                continue
            target = allowed if self.allows(path) else violations
            if path not in target:
                target.append(path)
        return PathValidationResult(tuple(allowed), tuple(violations))
