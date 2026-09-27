"""Local real-process smoke; never contacts a remote host or invokes a model."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from http.cookies import SimpleCookie

import httpx
from websockets.sync.client import connect
from protocol.generated import python as dto

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server.common import stamp, uid


def main():
    data = ROOT / ".tmp" / ("smoke-" + uid())
    data.mkdir(parents=True)
    origin = "https://smoke.invalid"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = dict(os.environ, HQREMOTE_DATA_DIR=str(data), HQREMOTE_ORIGIN=origin,
               HQREMOTE_HOST="127.0.0.1", HQREMOTE_PORT=str(port), PYTHONDONTWRITEBYTECODE="1")
    password = secrets.token_urlsafe(32)
    created = subprocess.run([sys.executable, "-m", "server.cli", "create-account", "--login", "smoke", "--display-name", "Smoke", "--password-stdin"],
                             input=password + "\n", text=True, capture_output=True, cwd=ROOT, env=env, timeout=15)
    assert created.returncode == 0, "CLI account initialization failed"
    print(created.stdout.strip())
    process = subprocess.Popen([sys.executable, "-m", "server"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    secret, store, epoch = secrets.token_urlsafe(32), uid(), uid()
    try:
        headers = {"Origin": origin, "X-Forwarded-Proto": "https"}
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", headers=headers, timeout=5, trust_env=False) as client:
            def request(method, path, body=None, model=None, extra=None):
                result = client.request(method, "/api/v2" + path, json=body, headers={"Idempotency-Key": uid(), **(extra or {})})
                dto.ApiEnvelope.model_validate(result.json())
                assert result.status_code < 300, "Smoke HTTP step failed"
                if model:
                    getattr(dto, model).model_validate(result.json()["data"])
                return result
            for attempt in range(80):
                try:
                    if client.get("/api/v2/auth/session").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                assert process.poll() is None, "uvicorn exited during startup"
                time.sleep(0.1)
            else:
                raise AssertionError("uvicorn did not start")
            print("uvicorn listening on loopback: PASS")
            login = request("POST", "/auth/login", dict(loginName="smoke", password=password), "RemoteAuthenticatedSession")
            cookie = SimpleCookie(login.headers["set-cookie"])["__Host-hqremote"].value
            client.headers.update({"Cookie": "__Host-hqremote=" + cookie, "X-CSRF-Token": login.json()["data"]["csrfToken"]})
            print("browser login and secure session: PASS")
            challenge = request("POST", "/worker/pairing-requests", dict(deviceName="Smoke Worker", workerStoreId=store, platform="linux", architecture="x86_64"), "RemotePairingChallenge", {"Authorization": "Bearer " + secret}).json()["data"]
            request("POST", "/pairings/preview", dict(pairCode=challenge["pairCode"]), "RemotePairingPreview")
            request("POST", "/pairings/" + challenge["pairRequestId"] + "/confirm", dict(pairCode=challenge["pairCode"]), "RemoteDeviceView")
            print("pairing preview and confirmation: PASS")
            worker = challenge["workerId"]
            def hello():
                return dict(type="worker.hello", wireRevision=1, protocolVersion=dto.PROTOCOL_VERSION, workerId=worker, workerStoreId=store, workerEpoch=epoch, platform="linux", architecture="x86_64", capabilityRevision=1, lastServerAck=None)
            def receive(ws):
                value = json.loads(ws.recv(timeout=5))
                dto.RemoteServerOutboundFrame.model_validate(value)
                return value
            def send(ws, value):
                dto.RemoteWorkerOutboundFrame.model_validate(value)
                ws.send(json.dumps(value))
            ws_headers = {"Authorization": "Bearer " + secret, "X-Forwarded-Proto": "https"}
            with connect(f"ws://127.0.0.1:{port}/ws/v2/worker", additional_headers=ws_headers, proxy=None) as ws:
                send(ws, hello())
                assert receive(ws)["commandDelivery"] == "ready"
                catalog = dict(workerId=worker, workerStoreId=store, capabilityRevision=1, observedAt=stamp(time.time()), workspaces=[dict(workspaceId="workspace", name="Smoke", displayPath="/workspace", vcs="git", canWrite=True)], scenes=[dict(sceneId="scene", name="Smoke", version=1, readOnly=False)], remotelyBlockedActions=[])
                send(ws, dict(type="capability.changed", wireRevision=1, eventId=uid(), workerId=worker, workerStoreId=store, workerEpoch=epoch, seq=1, occurredAt=stamp(time.time()), payload=catalog))
                assert receive(ws)["position"]["seq"] == 1
            conv = request("POST", "/conversations", dict(targetWorkerId=worker, workerStoreId=store, title="Smoke", workspaceId="workspace", sceneId="scene", sceneVersion=1), "RemoteConversationView").json()["data"]["conversationId"]
            queued = request("POST", "/conversations/" + conv + "/messages", dict(clientMessageId=uid(), text="Smoke communication only", sessionMode="new"), "RemoteQueuedReceipt").json()["data"]
            assert queued["deliveryState"] == "queued_offline"
            with connect(f"ws://127.0.0.1:{port}/ws/v2/worker", additional_headers=ws_headers, proxy=None) as ws:
                send(ws, hello())
                assert receive(ws)["commandDelivery"] == "ready"
                command = receive(ws)
                assert command["commandId"] == queued["commandId"] and command["conversationSeq"] == 1
                send(ws, dict(type="command.accepted", wireRevision=1, eventId=uid(), workerId=worker, workerStoreId=store, workerEpoch=epoch, seq=2, occurredAt=stamp(time.time()), commandId=command["commandId"], conversationId=conv, receivedAt=stamp(time.time()), status="accepted"))
                assert receive(ws)["position"]["seq"] == 2
            request("GET", "/conversations/" + conv + "/snapshot", model="RemoteConversationSnapshot")
            assert request("GET", "/commands/" + queued["commandId"], model="RemoteCommandView").json()["data"]["status"] == "accepted"
            print("fake Worker revision 1, offline queue, reconnect and durable ack: PASS")
            backup = subprocess.run([sys.executable, "-m", "server.cli", "backup", str(data / "backup.sqlite3")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)
            assert backup.returncode == 0
            print(backup.stdout.strip())
            assert password not in created.stdout + created.stderr + backup.stdout + backup.stderr
    finally:
        process.terminate()
        logs, _ = process.communicate(timeout=10)
        for sensitive in (password, secret, locals().get("cookie", "no-cookie-marker")):
            assert sensitive not in logs
        if "challenge" in locals():
            assert challenge["pairCode"] not in logs
    print("server output credential redaction: PASS")
    print("SMOKE PASS")


if __name__ == "__main__":
    main()
