from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from protocol.generated.python import AgentResult, Blocker, FileChange, TestOutcome

from .catalog import BuiltinCatalog
from .errors import InvalidTaskActionError


@dataclass(frozen=True, slots=True)
class WorkflowNodeSpec:
    node_id: str
    role_id: str
    objective: str
    depends_on: tuple[str, ...] = ()


class WorkflowPlan:
    """A provider-neutral DAG. Nodes can only name roles and dependencies."""

    def __init__(self, nodes: Iterable[WorkflowNodeSpec], catalog: BuiltinCatalog) -> None:
        ordered = tuple(nodes)
        if not ordered:
            raise InvalidTaskActionError("工作流至少需要一个节点")
        self.nodes = {node.node_id: node for node in ordered}
        if len(self.nodes) != len(ordered):
            raise InvalidTaskActionError("工作流 nodeId 重复")
        for node in ordered:
            catalog.role(node.role_id)
            missing = set(node.depends_on) - self.nodes.keys()
            if missing:
                raise InvalidTaskActionError(
                    "工作流依赖不存在",
                    nodeId=node.node_id,
                    missingDependencies=sorted(missing),
                )
            if node.node_id in node.depends_on:
                raise InvalidTaskActionError("节点不能依赖自身", nodeId=node.node_id)
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                raise InvalidTaskActionError("工作流存在循环依赖", nodeId=node_id)
            visiting.add(node_id)
            for dependency in self.nodes[node_id].depends_on:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in self.nodes:
            visit(node_id)


@dataclass(slots=True)
class WorkflowProgress:
    plan: WorkflowPlan
    node_statuses: dict[str, str] = field(default_factory=dict)
    results: dict[str, AgentResult] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for node_id in self.plan.nodes:
            self.node_statuses.setdefault(node_id, "pending")

    def ready_nodes(self) -> tuple[WorkflowNodeSpec, ...]:
        self._skip_blocked_descendants()
        result = []
        for node_id, node in self.plan.nodes.items():
            if self.node_statuses[node_id] != "pending":
                continue
            if all(self.node_statuses[dependency] == "succeeded" for dependency in node.depends_on):
                result.append(node)
        return tuple(result)

    def start(self, node_id: str) -> None:
        ready = {node.node_id for node in self.ready_nodes()}
        if node_id not in ready:
            raise InvalidTaskActionError("节点依赖未满足，不能分派", nodeId=node_id)
        self.node_statuses[node_id] = "running"

    def complete(self, node_id: str, result: AgentResult) -> None:
        if self.node_statuses.get(node_id) != "running":
            raise InvalidTaskActionError("只有运行中的节点可以完成", nodeId=node_id)
        self.results[node_id] = result
        self.node_statuses[node_id] = "succeeded" if result.status == "done" else "failed"
        self._skip_blocked_descendants()

    def retry(self, node_id: str) -> None:
        if self.node_statuses.get(node_id) not in {"failed", "cancelled"}:
            raise InvalidTaskActionError("只有失败或取消的节点可以重试", nodeId=node_id)
        self.node_statuses[node_id] = "pending"
        self.results.pop(node_id, None)
        reset = {node_id}
        changed = True
        while changed:
            changed = False
            for dependent_id, node in self.plan.nodes.items():
                if dependent_id in reset:
                    continue
                if any(dependency in reset for dependency in node.depends_on):
                    reset.add(dependent_id)
                    changed = True
        for dependent_id in reset - {node_id}:
            if self.node_statuses[dependent_id] == "skipped":
                self.node_statuses[dependent_id] = "pending"

    @property
    def finished(self) -> bool:
        return all(
            status in {"succeeded", "failed", "skipped", "cancelled"}
            for status in self.node_statuses.values()
        )

    def aggregate_result(self) -> AgentResult:
        if not self.finished:
            raise InvalidTaskActionError("工作流尚未结束，不能聚合结果")
        failed_nodes = [
            node_id for node_id, status in self.node_statuses.items() if status in {"failed", "cancelled"}
        ]
        changes: dict[str, FileChange] = {}
        tests: dict[tuple[str, str], TestOutcome] = {}
        blockers: list[Blocker] = []
        artifacts: list[str] = []
        questions: list[str] = []
        summaries: list[str] = []
        commit: str | None = None
        branch: str | None = None
        for node_id in self.plan.nodes:
            result = self.results.get(node_id)
            if result is None:
                continue
            summaries.append(f"[{node_id}] {result.summary}")
            for change in result.changed_files or []:
                changes[change.path] = change
            for test in result.tests or []:
                tests[(test.name, test.command)] = test
            blockers.extend(result.blockers or [])
            for artifact in result.artifacts or []:
                if artifact not in artifacts:
                    artifacts.append(artifact)
            for question in result.questions or []:
                if question not in questions:
                    questions.append(question)
            commit = result.commit or commit
            branch = result.branch or branch
        status = "failed" if failed_nodes else "done"
        summary = "\n".join(summaries) or (
            f"工作流失败节点：{', '.join(failed_nodes)}" if failed_nodes else "工作流完成"
        )
        return AgentResult.model_validate(
            {
                "status": status,
                "summary": summary,
                "changedFiles": [
                    value.model_dump(mode="json", by_alias=True, exclude_none=True)
                    for value in changes.values()
                ],
                "tests": [
                    value.model_dump(mode="json", by_alias=True, exclude_none=True)
                    for value in tests.values()
                ],
                "commit": commit,
                "branch": branch,
                "artifacts": artifacts,
                "blockers": [
                    value.model_dump(mode="json", by_alias=True, exclude_none=True)
                    for value in blockers
                ],
                "questions": questions,
            }
        )

    def _skip_blocked_descendants(self) -> None:
        changed = True
        while changed:
            changed = False
            for node_id, node in self.plan.nodes.items():
                if self.node_statuses[node_id] != "pending":
                    continue
                dependency_states = [self.node_statuses[item] for item in node.depends_on]
                if any(state in {"failed", "skipped", "cancelled"} for state in dependency_states):
                    self.node_statuses[node_id] = "skipped"
                    changed = True
