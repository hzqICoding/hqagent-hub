import json
from pathlib import Path

import pytest
import yaml

from conftest import FakeWorker, check_http
from test_commands_events import admit_run
from server.app import ROUTES, create_app
from server.common import Fault, stamp, uid
from server.repository import Repository, UnitOfWork


def approval_event(worker, action="git_push", allowed=True, risk="low"):
    payload = dict(approvalId=uid(), resultRef=dict(runId="run", executionTaskId="task-run"), action=action,
                   targetSummary="workspace action", riskLevel=risk, status="pending", requestedAt=stamp(worker.env.clock()),
                   expiresAt=stamp(worker.env.clock() + 120), remoteApprovalAllowed=allowed, workerPolicyRevision=1)
    assert worker.emit(worker.event("approval.state_changed", conversationId=worker.conv, payload=payload))["type"] == "worker.events_ack"
    return payload


@pytest.mark.parametrize("action,allowed,risk", [(a, True, "low") for a in ("git_push", "deploy", "delete", "db_migrate", "shell")] + [("network", False, "low"), ("network", True, "high")])
def test_forbidden_approval_but_rejection_allowed(env, paired, action, allowed, risk):
    with paired.connect():
        admit_run(paired)
        approval = approval_event(paired, action, allowed, risk)
        path = "/approvals/" + approval["approvalId"]
        assert env.alice.get(path).status_code == 200
        assert env.bob.get(path).json()["error"]["code"] == "NOT_FOUND"
        assert env.bob.post(path + "/decisions", dict(decision="reject")).status_code == 404
        result = env.alice.post(path + "/decisions", dict(decision="approve"))
        assert result.status_code == 403 and result.json()["error"]["code"] == "REMOTE_APPROVAL_FORBIDDEN"
        rejection = env.alice.post(path + "/decisions", dict(decision="reject"))
        assert rejection.status_code == 202
        frame = paired.receive()
        assert frame["type"] == "approval.decide" and frame["payload"]["decision"] == "reject"
        assert "conversationSeq" not in frame
        assert frame["expiresAt"] <= approval["expiresAt"]
        assert env.alice.post(path + "/decisions", dict(decision="reject")).json()["data"] == rejection.json()["data"]


def test_worker_declared_policy_and_safe_approval_consumption(env, paired):
    with paired.connect():
        admit_run(paired)
        paired.catalog(capabilityRevision=2, remotelyBlockedActions=["network"])
        approval = approval_event(paired, "network")
        path = "/approvals/" + approval["approvalId"] + "/decisions"
        assert env.alice.post(path, dict(decision="approve")).status_code == 403
        paired.catalog(capabilityRevision=3, remotelyBlockedActions=[])
        result = env.alice.post(path, dict(decision="approve"))
        assert result.status_code == 202
        command = paired.receive()
        accepted = paired.event("command.accepted", conversationId=paired.conv, commandId=command["commandId"], receivedAt=stamp(env.clock()), status="accepted")
        assert paired.emit(accepted)["type"] == "worker.events_ack"
        done = paired.event("command.completed", conversationId=paired.conv, commandId=command["commandId"], resultStatus="approval_consumed", resultRef=approval["resultRef"])
        assert paired.emit(done)["type"] == "worker.events_ack"
        assert env.alice.get("/commands/" + command["commandId"]).json()["data"]["resultStatus"] == "approval_consumed"


@pytest.mark.parametrize("action,evidence,still_running", [("pause", "node_boundary_paused", True), ("resume", "supervisor_resumed", True), ("cancel", "adapter_confirmed", False)])
def test_control_confirmed_only_from_worker(env, paired, action, evidence, still_running):
    with paired.connect():
        admit_run(paired)
        result = env.alice.post("/runs/run/commands", dict(action=action))
        assert result.status_code == 202
        frame = paired.receive()
        assert frame["type"] == "run." + action and "conversationSeq" not in frame
        assert paired.emit(paired.event("command.accepted", conversationId=paired.conv, commandId=frame["commandId"], receivedAt=stamp(env.clock()), status="accepted"))["type"] == "worker.events_ack"
        assert env.alice.get("/commands/" + frame["commandId"]).json()["data"]["status"] == "accepted"
        control = dict(outcome="confirmed", executionMayStillBeRunning=still_running, orphanProcessIds=[], reason="structured observation", evidence=evidence, observedAt=stamp(env.clock()))
        done = paired.event("command.completed", conversationId=paired.conv, commandId=frame["commandId"], resultStatus="confirmed", resultRef=dict(runId="run", executionTaskId="task-run"), controlResult=control)
        assert paired.emit(done)["type"] == "worker.events_ack"
        view = env.alice.get("/commands/" + frame["commandId"]).json()["data"]
        assert view["controlResult"] == control and view["status"] == "completed"
        assert env.alice.get("/runs/run").json()["data"]["status"] == "running"  # no fabricated run state


def test_unknown_cancel_remains_accepted_and_invalid_completed_rejected(env, paired):
    with paired.connect():
        admit_run(paired)
        env.alice.post("/runs/run/commands", dict(action="cancel"))
        command = paired.receive()
        paired.emit(paired.event("command.accepted", conversationId=paired.conv, commandId=command["commandId"], receivedAt=stamp(env.clock()), status="accepted"))
        control = dict(outcome="unconfirmed", executionMayStillBeRunning=True, orphanProcessIds=[], reason="unknown", evidence="missing_execution_handle", observedAt=stamp(env.clock()))
        observed = paired.event("command.control_result", conversationId=paired.conv, commandId=command["commandId"], controlResult=control, executionStatus="paused", resultRef=dict(runId="run", executionTaskId="task-run"))
        assert paired.emit(observed)["type"] == "worker.events_ack"
        view = env.alice.get("/commands/" + command["commandId"]).json()["data"]
        assert view["status"] == "accepted" and view["controlResult"] == control
        invalid = paired.event("command.completed", conversationId=paired.conv, commandId=command["commandId"], resultStatus="confirmed", resultRef=dict(runId="run", executionTaskId="task-run"))
        assert paired.emit(invalid)["error"]["code"] == "REMOTE_EVENT_CONFLICT"
        assert env.alice.get("/commands/" + command["commandId"]).json()["data"]["status"] == "accepted"


def test_retry_only_completes_with_persisted_new_reference(env, paired):
    with paired.connect():
        admit_run(paired)
        assert env.bob.post("/runs/run/commands", dict(action="retry")).status_code == 404
        env.alice.post("/runs/run/commands", dict(action="retry", nodeId="node"))
        command = paired.receive()
        paired.emit(paired.event("command.accepted", conversationId=paired.conv, commandId=command["commandId"], receivedAt=stamp(env.clock()), status="accepted"))
        done = paired.event("command.completed", conversationId=paired.conv, commandId=command["commandId"], resultStatus="retry_enqueued", resultRef=dict(runId="new-run", executionTaskId="new-task"))
        assert paired.emit(done)["type"] == "worker.events_ack"
        assert env.alice.get("/runs/new-run").status_code == 404  # reference != execution projection


def test_atomic_command_rollback_preserves_sequence(env, paired, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise RuntimeError("private-exception-marker")
    original = env.service.outbox
    monkeypatch.setattr(env.service, "outbox", broken)
    result = env.alice.post("/conversations/" + paired.conv + "/messages", dict(clientMessageId=uid(), text="attempt", sessionMode="new"))
    assert result.status_code == 500
    assert "private-exception-marker" not in result.text + caplog.text
    monkeypatch.setattr(env.service, "outbox", original)
    assert env.alice.get("/conversations/" + paired.conv + "/commands").json()["data"]["items"] == []
    assert paired.send(paired.conv)["conversationSeq"] == 1


def test_event_projection_browser_outbox_atomic_rollback(env, paired, monkeypatch):
    with paired.connect():
        receipt = paired.send(paired.conv)
        frame = paired.receive()
        event = paired.event("command.accepted", commandId=receipt["commandId"], conversationId=paired.conv, receivedAt=frame["createdAt"], status="accepted")
        def broken(*args, **kwargs):
            raise RuntimeError("simulated transaction abort")
        with env.service.repo.transaction() as tx:
            owner = env.service.security.session(tx, env.alice.cookie)["owner"]
        with monkeypatch.context() as scoped:
            scoped.setattr(UnitOfWork, "browser_add", broken)
            with pytest.raises(RuntimeError):
                with env.service.repo.transaction() as tx:
                    env.app.state.transport.events.accept(tx, owner, event)
        with env.service.repo.transaction() as tx:
            assert tx.event_id(owner, event["eventId"]) is None
            assert tx.get(owner, "command", receipt["commandId"])["status"] == "queued"
            assert tx.get(owner, "event-position", paired.worker + ":" + paired.store)["seq"] == 1
        assert paired.emit(event)["position"]["seq"] == 2


def test_backup_migration_and_restart_retain_queue(env, paired, tmp_path):
    receipt = paired.send(paired.conv)
    backup = tmp_path / "consistent.sqlite3"
    env.service.repo.backup(backup)
    other = Repository(backup)
    try:
        other.migrate()
        with other.transaction() as tx:
            owner = env.service.security.session(tx, env.alice.cookie)["owner"]
            assert tx.get(owner, "command", receipt["commandId"])["status"] == "queued"
            assert tx.get(owner, "outbox", "command:" + receipt["commandId"])["done"] is False
    finally:
        other.close()


def test_http_binding_completeness():
    root = Path(__file__).resolve().parents[3]
    spec = yaml.safe_load((root / "packages/protocol/openapi/remote-hub.v2.yaml").read_text(encoding="utf-8"))
    expected = {(method.upper(), path): op for path, methods in spec["paths"].items() for method, op in methods.items()}
    actual = {(method, "/api/v2" + path): (im, om, str(status)) for method, path, _, im, om, status in ROUTES}
    assert actual.keys() == expected.keys()
    for route, (im, om, status) in actual.items():
        op = expected[route]
        assert op["responses"][status]["x-dataSchema"]["$ref"].endswith("/" + om)
        if im:
            assert op["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/" + im)
