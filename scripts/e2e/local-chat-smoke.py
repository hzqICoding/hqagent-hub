"""Explicit live CLI smoke. Uses an isolated scratch directory, never a user repo.

Run with the backend venv: python scripts/e2e/local-chat-smoke.py --runtime codex
This invokes the selected real Agent and can consume its normal model allowance.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/hub"))

import httpx
from api.app import create_application
from core.security import generate_startup_token
from runtime.composition import bind_ports, build_ports
from runtime.paths import HubPaths


async def run(runtime: str, timeout: float, model: str | None = None, effort: str | None = None) -> dict:
    scratch = Path(tempfile.mkdtemp(prefix="hqagent-live-"))
    workspace = scratch / "workspace"
    workspace.mkdir()
    marker = "HQAGENT_LOCAL_SMOKE_OK"
    (workspace / "README.md").write_text(marker + "\n", encoding="utf-8")
    ports = build_ports()
    hub = create_application(paths=HubPaths.resolve(scratch / "state"), token=generate_startup_token(), ports=ports,
        allowed_hosts={"127.0.0.1"}, allowed_origins={"http://127.0.0.1:8123"}, environment="test")
    await bind_ports(hub, ports)
    code = hub.local_auth.issue_code()
    print(f"scratch={scratch}", flush=True)
    async with hub.app.router.lifespan_context(hub.app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=hub.app), base_url="http://127.0.0.1:8123",
                                     headers={"Origin": "http://127.0.0.1:8123"}) as client:
            async def request(method, path, *, body=None, key=None):
                response = await client.request(method, "/api/v2" + path, json=body,
                    headers={"Idempotency-Key": key} if key else {})
                if response.status_code >= 400:
                    raise RuntimeError(f"{path}: {response.status_code}: {response.text[:700]}")
                return response.json()["data"]
            await request("POST", "/auth/local-session", body={"code": code})
            agents = await request("GET", "/agents")
            selected = next((a for a in agents if a["adapterId"] == runtime and a["status"] == "ready"), None)
            if selected is None:
                return {"passed": False, "reason": f"{runtime} is not ready", "scratch": str(scratch)}
            scene = next(s for s in await request("GET", "/scenes") if s["id"] == "analyze")
            scene["roles"][0]["agentInstanceId"] = selected["id"]
            if model:
                scene["roles"][0]["modelId"] = model
            if effort:
                scene["roles"][0]["reasoningEffort"] = effort
            await request("PUT", "/scenes/analyze", body={"roles": scene["roles"], "expectedVersion": scene["version"]})
            ws = await request("POST", "/workspaces", body={"path": str(workspace), "name": "Live isolated smoke"})
            conv = await request("POST", "/conversations", body={"title": "Live read-only smoke", "workspaceId": ws["id"], "sceneId": "analyze"}, key="smoke-conversation")
            body = {"clientMessageId": "smoke-message", "text": "Read README.md in the current directory. Return its exact marker in the result summary. Do not change any files.", "sessionMode": "new"}
            receipt = await request("POST", f"/conversations/{conv['id']}/messages", body=body, key="smoke-message")
            replay = await request("POST", f"/conversations/{conv['id']}/messages", body=body, key="smoke-message")
            assert receipt["runId"] == replay["runId"] and replay["duplicate"]
            deadline, last = time.monotonic() + timeout, None
            while time.monotonic() < deadline:
                detail = await request("GET", f"/runs/{receipt['runId']}")
                if detail["status"] != last:
                    last = detail["status"]
                    print(f"run={receipt['runId']} status={last}", flush=True)
                if detail["status"] in {"succeeded", "failed", "cancelled"}:
                    messages = await request("GET", f"/conversations/{conv['id']}/messages")
                    summary = "\n".join(m["text"] for m in messages if m["role"] == "assistant")
                    if not summary:
                        await asyncio.sleep(0.3)
                        continue
                    return {"passed": last == "succeeded" and marker in summary,
                            "runtime": runtime, "status": last, "duplicateSuppressed": replay["duplicate"],
                            "readOnlyPreserved": (workspace / "README.md").read_text(encoding="utf-8") == marker + "\n",
                            "summary": summary[:1500], "scratch": str(scratch)}
                await asyncio.sleep(0.3)
            await request("POST", f"/runs/{receipt['runId']}/commands", body={"action": "cancel"}, key="smoke-cancel")
            return {"passed": False, "reason": "timeout; cancellation requested", "scratch": str(scratch)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", choices=["codex", "claude"], required=True)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--model")
    parser.add_argument("--effort")
    options = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    result = asyncio.run(run(options.runtime, options.timeout, options.model, options.effort))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
