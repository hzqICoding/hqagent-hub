from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from protocol.generated.python import PickLocalDirectoryInput, PickLocalDirectoryView

from api.app import create_application
from core.errors import HubError
from runtime.directory_picker import LocalDirectoryPicker
from runtime.paths import HubPaths


def test_picker_api_requires_cookie_and_trusted_origin(tmp_path, monkeypatch):
    pick = AsyncMock(return_value=PickLocalDirectoryView(cancelled=True))
    monkeypatch.setattr(LocalDirectoryPicker, "pick", pick)
    hub = create_application(paths=HubPaths.resolve(tmp_path), token="private-test-token",
                             allowed_hosts={"testserver"}, allowed_origins={"http://testserver"}, environment="test")
    code = hub.local_auth.issue_code("picker-test-code")
    with TestClient(hub.app) as client:
        headers = {"Origin": "http://testserver"}
        assert client.post("/api/v2/workspaces/pick", json={}, headers=headers).status_code == 401
        assert pick.await_count == 0
        client.post("/api/v2/auth/local-session", json={"code": code}, headers=headers)
        assert client.post("/api/v2/workspaces/pick", json={}, headers={"Origin": "https://other.example"}).status_code == 403
        assert client.post("/api/v2/workspaces/pick", json={}).status_code == 403
        assert pick.await_count == 0
        response = client.post("/api/v2/workspaces/pick", json={}, headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["cancelled"] is True
        assert pick.await_count == 1


def test_duplicate_dialogs_and_invalid_initial_path_are_rejected(monkeypatch):
    async def scenario():
        picker = LocalDirectoryPicker()
        entered, release = asyncio.Event(), asyncio.Event()

        async def launch(initial):
            entered.set()
            await release.wait()
            return PickLocalDirectoryView(cancelled=True)

        monkeypatch.setattr(picker, "_launch", launch)
        with pytest.raises(HubError, match="绝对路径"):
            await picker.pick(PickLocalDirectoryInput(initialPath="relative/path"))
        first = asyncio.create_task(picker.pick(PickLocalDirectoryInput()))
        await entered.wait()
        with pytest.raises(HubError, match="窗口已打开"):
            await picker.pick(PickLocalDirectoryInput())
        release.set()
        assert (await first).cancelled
        assert (await picker.pick(PickLocalDirectoryInput())).cancelled

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["selected", "cancelled", "timeout", "invalid", "crashed"])
def test_dialog_process_results_and_timeout_cleanup(tmp_path, monkeypatch, outcome):
    class Child:
        returncode = None
        killed = False

        async def communicate(self):
            if outcome == "timeout":
                await asyncio.sleep(60)
            self.returncode = 1 if outcome == "crashed" else 0
            payload = {"cancelled": outcome == "cancelled"}
            if outcome != "cancelled":
                payload["selectedPath"] = str(tmp_path) if outcome == "selected" else "relative"
            return json.dumps(payload).encode(), b""

        def kill(self):
            self.killed = True
            self.returncode = -9

        async def wait(self):
            return self.returncode

    child = Child()
    start = AsyncMock(return_value=child)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", start)
    picker = LocalDirectoryPicker(timeout=0.01)
    if outcome in {"timeout", "invalid", "crashed"}:
        with pytest.raises(HubError, match="手动输入目录"):
            asyncio.run(picker.pick(PickLocalDirectoryInput()))
    else:
        result = asyncio.run(picker.pick(PickLocalDirectoryInput()))
        assert result.cancelled == (outcome == "cancelled")
        if outcome == "selected":
            assert result.selected_path == str(tmp_path.resolve())
    assert child.killed == (outcome == "timeout")
    assert "--pick-directory" in start.call_args.args
