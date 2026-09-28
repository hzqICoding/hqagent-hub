from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from protocol.generated.python import RemoteLinkPairingInput, TaskStatus
from core.errors import HubError
from runtime.remote.link import PairingHTTP
from runtime.remote.security import safe_text
from remote_support import System, FakeRemoteServer, command_events, until


def test_plain_failed_label_is_not_stop_evidence(tmp_path):
    async def scenario():
        system = System(tmp_path, hold=True)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                await server.send(system.command("running"))
                await until(lambda: len(system.adapter.started) == 1)
                row = system.repo.inbox("running")
                record = system.chat.repository.run_record(row["run_id"])
                task = system.tasks.repository.get(record["task_id"])
                system.tasks.repository.save(task.model_copy(update={"status": TaskStatus.FAILED}))
                await server.send(system.command("cancel-label", kind="run.cancel", payload={"runId": row["run_id"]}))
                await until(lambda: command_events(server, "cancel-label", "command.control_result"))
                result = command_events(server, "cancel-label", "command.control_result")[-1]["controlResult"]
                assert result["outcome"] == "unconfirmed"
                assert result["executionMayStillBeRunning"] is True
                assert not command_events(server, "cancel-label", "command.completed")
                assert system.adapter.cancels == []  # Original terminal-cancel semantics preserved.
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_pairing_unknown_response_reuses_secret_and_durable_intent(tmp_path):
    async def scenario():
        system = System(tmp_path)
        calls = []
        try:
            def timeout(request):
                calls.append((request.headers["authorization"], request.headers["idempotency-key"]))
                raise httpx.ReadTimeout("contains secret value but must not be reflected", request=request)
            system.link.http = PairingHTTP(system.link.vault, transport=httpx.MockTransport(timeout))
            request = RemoteLinkPairingInput(serverOrigin="https://remote.invalid", deviceName="test")
            for _ in range(2):
                with pytest.raises(HubError) as error:
                    await system.link.pair(request, "uncertain")
                assert error.value.code == "REMOTE_SERVER_UNREACHABLE"
                assert "contains secret value" not in str(error.value)
            assert len(calls) == 2 and calls[0] == calls[1]
            assert system.repo.get("link")["intent"]["requestKey"] == calls[0][1]
            assert system.repo.get("link")["view"]["lastErrorCode"] == "REMOTE_SERVER_UNREACHABLE"
            with pytest.raises(HubError) as busy:
                await system.link.pair(request, "new-id")
            assert busy.value.code == "REMOTE_PAIRING_IN_PROGRESS"
        finally:
            await system.close()
    asyncio.run(scenario())


def test_persisted_high_water_survives_ack_pruning_and_reopen(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server)
                await system.bridge.receive(system.command("one"))
                identity = system.repo.get("identity")
                position = {"workerStoreId": identity["store"], "seq": identity["high"]}
                system.repo.ack(position)
                assert system.repo.frames() == []
                system.repo.boot()
                system.repo.ack(position)
                assert system.repo.get("identity")["high"] == identity["high"]
                assert system.repo.get("identity")["ack"] == position["seq"]
                with pytest.raises(HubError) as ahead:
                    system.repo.ack({**position, "seq": position["seq"] + 1})
                assert ahead.value.code == "REMOTE_ACK_CONFLICT"
        finally:
            await system.close()
    asyncio.run(scenario())


def test_remote_scene_profile_and_parent_remain_usable_from_local_computer(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                await server.send(system.command("remote"))
                await until(lambda: command_events(server, "remote", "command.completed"))
                row = system.repo.inbox("remote")
                record = system.chat.repository.run_record(row["run_id"])
                for index, reference in enumerate(({"parentTaskId": record["task_id"]}, {"profileId": "local-profile:" + row["run_id"]})):
                    response = await system.local.post("/api/v1/tasks", json={"objective": "continue locally", "workspaceId": "workspace",
                        "profileId": "local-profile:" + row["run_id"], "workflowRoles": ["planner"], **reference}, headers={"Idempotency-Key": f"local-reference-{index}"})
                    assert response.status_code == 200, response.text
                    await until(lambda: str(system.tasks.repository.get(response.json()["data"]["id"]).status) == "succeeded")
                assert len(system.adapter.started) == 3
        finally:
            await system.close()
    asyncio.run(scenario())


def test_worker_redacts_authorization_environment_and_private_reasoning():
    value = "Authorization: Bearer arbitrary-header-value\nAPI_KEY=private-env-value\n<think>private-reasoning</think>\n" + \
            "-----BEGIN PRIVATE KEY-----\nprivate-key-body\n-----END PRIVATE KEY-----\npublic result"
    clean = safe_text(value)
    for private in ("arbitrary-header-value", "private-env-value", "private-reasoning", "private-key-body"):
        assert private not in clean
    assert "public result" in clean


def test_oversized_answer_reports_limit_without_losing_actual_terminal_event(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            system.adapter.result = system.adapter.result.model_copy(update={"summary": "x" * 32001})
            async with FakeRemoteServer() as server:
                await system.pair(server, start=True)
                await server.send(system.command("large-answer"))
                await until(lambda: command_events(server, "large-answer", "command.completed"))
                await until(lambda: any(f["type"] == "message.appended" for f in server.frames))
                notice = next(f["payload"] for f in server.frames if f["type"] == "message.appended")
                assert notice["role"] == "system" and "REMOTE_FRAME_TOO_LARGE" in notice["text"]
                assert command_events(server, "large-answer", "command.completed")[-1]["resultStatus"] == "succeeded"
                messages = system.chat.repository.messages("conversation-remote")
                assert len(messages[-1].text) > 32000
                assert system.repo.get("link")["view"]["state"] == "paired"
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())
