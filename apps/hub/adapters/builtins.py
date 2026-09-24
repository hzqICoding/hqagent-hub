"""Trusted built-in registry. External manifests never import arbitrary code."""
from __future__ import annotations

from collections.abc import Callable

from adapters.base import AgentAdapter


class BuiltinRuntimeRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], AgentAdapter]] = {}

    def register(self, runtime_id: str, factory: Callable[[], AgentAdapter]) -> None:
        if not runtime_id or runtime_id in self._factories:
            raise ValueError(f"Runtime registration conflict: {runtime_id}")
        self._factories[runtime_id] = factory

    def instantiate(self) -> list[AgentAdapter]:
        result = []
        for runtime_id, factory in self._factories.items():
            adapter = factory()
            if adapter.adapter_id != runtime_id:
                raise ValueError("Runtime factory identity mismatch")
            result.append(adapter)
        return result


def builtin_runtimes() -> BuiltinRuntimeRegistry:
    from adapters.claude_adapter import ClaudeAdapter
    from adapters.codex_adapter import CodexAdapter
    registry = BuiltinRuntimeRegistry()
    registry.register("claude", ClaudeAdapter)
    registry.register("codex", CodexAdapter)
    return registry
