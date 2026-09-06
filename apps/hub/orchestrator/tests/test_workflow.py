import pytest
from protocol.generated.python import AgentResult

from orchestrator.catalog import BuiltinCatalog
from orchestrator.errors import InvalidTaskActionError
from orchestrator.workflow import WorkflowNodeSpec, WorkflowPlan, WorkflowProgress


def build_plan() -> WorkflowPlan:
    return WorkflowPlan(
        (
            WorkflowNodeSpec("plan", "architect", "design"),
            WorkflowNodeSpec("code", "general_implementer", "implement", ("plan",)),
            WorkflowNodeSpec("review", "reviewer", "review", ("code",)),
            WorkflowNodeSpec("test", "tester", "test", ("code",)),
            WorkflowNodeSpec("integrate", "integrator", "integrate", ("review", "test")),
        ),
        BuiltinCatalog.load(),
    )


def result(status: str, summary: str, path: str | None = None) -> AgentResult:
    return AgentResult.model_validate(
        {
            "status": status,
            "summary": summary,
            "changedFiles": (
                [{"path": path, "changeKind": "modified"}] if path else []
            ),
        }
    )


def test_workflow_advances_by_role_dependencies_and_aggregates_results() -> None:
    progress = WorkflowProgress(build_plan())
    assert [node.role_id for node in progress.ready_nodes()] == ["architect"]

    progress.start("plan")
    progress.complete("plan", result("done", "plan complete"))
    progress.start("code")
    progress.complete("code", result("done", "code complete", "apps/hub/orchestrator/runtime.py"))
    assert {node.role_id for node in progress.ready_nodes()} == {"reviewer", "tester"}
    progress.start("review")
    progress.complete("review", result("done", "review complete"))
    progress.start("test")
    progress.complete("test", result("done", "tests pass"))
    progress.start("integrate")
    progress.complete("integrate", result("done", "integrated"))

    aggregate = progress.aggregate_result()
    assert aggregate.status == "done"
    assert aggregate.changed_files[0].path == "apps/hub/orchestrator/runtime.py"
    assert "[review] review complete" in aggregate.summary


def test_failed_node_skips_dependants_until_retry() -> None:
    progress = WorkflowProgress(build_plan())
    progress.start("plan")
    progress.complete("plan", result("done", "plan complete"))
    progress.start("code")
    progress.complete("code", result("failed", "compile failed"))

    assert progress.node_statuses["review"] == "skipped"
    assert progress.node_statuses["test"] == "skipped"
    assert progress.node_statuses["integrate"] == "skipped"
    assert progress.finished is True
    assert progress.aggregate_result().status == "failed"

    progress.retry("code")
    assert progress.node_statuses["review"] == "pending"
    assert progress.node_statuses["test"] == "pending"


def test_workflow_rejects_cycles_and_unknown_roles() -> None:
    catalog = BuiltinCatalog.load()
    with pytest.raises(InvalidTaskActionError):
        WorkflowPlan(
            (
                WorkflowNodeSpec("a", "architect", "a", ("b",)),
                WorkflowNodeSpec("b", "reviewer", "b", ("a",)),
            ),
            catalog,
        )
    with pytest.raises(KeyError):
        WorkflowPlan((WorkflowNodeSpec("a", "vendor-specific-agent", "a"),), catalog)
