"""Local real-process smoke; never contacts a remote host or invokes a model."""
import json
import hashlib
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
from server.common import digest, stamp, uid
from smoke_native import native_smoke


def main():
    data = ROOT / ".tmp" / ("smoke-" + uid())
    data.mkdir(parents=True)
    origin = "https://smoke.invalid"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = dict(os.environ, HQREMOTE_DATA_DIR=str(data), HQREMOTE_ORIGIN=origin,
               HQREMOTE_HOST="127.0.0.1", HQREMOTE_PORT=str(port), HQREMOTE_RATE_LIMIT='1000', PYTHONDONTWRITEBYTECODE="1")
    password = secrets.token_urlsafe(32)
    created = subprocess.run([sys.executable, "-m", "server.cli", "create-account", "--login", "smoke", "--display-name", "Smoke", "--password-stdin"],
                             input=password + "\n", text=True, capture_output=True, cwd=ROOT, env=env, timeout=15)
    assert created.returncode == 0, "CLI account initialization failed"
    print(created.stdout.strip())
    # Completion logs can exceed a Windows pipe buffer. Drain to an ignored
    # local file rather than blocking the server until the end of the smoke.
    log_path = data / 'server.log'
    log_output = log_path.open('w', encoding='utf-8')
    process = subprocess.Popen([sys.executable, "-m", "server"], cwd=ROOT, env=env, stdout=log_output, stderr=subprocess.STDOUT, text=True)
    secret, store, epoch = secrets.token_urlsafe(32), uid(), uid()
    try:
        headers = {"Origin": origin, "X-Forwarded-Proto": "https"}
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", headers=headers, timeout=5, trust_env=False) as client:
            def request(method, path, body=None, model=None, extra=None):
                result = client.request(method, "/api/v2" + path, json=body, headers={"Idempotency-Key": uid(), **(extra or {})})
                dto.ApiEnvelope.model_validate(result.json())
                assert result.headers['X-Request-Id'] == result.json()['requestId']
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
            challenge = request("POST", "/worker/pairing-requests", dict(deviceName="Smoke Worker", workerStoreId=store, platform="linux", architecture="x86_64"), "RemotePairingChallenge", {"Authorization": "Bearer " + secret, "Cookie": ""}).json()["data"]
            request("POST", "/pairings/preview", dict(pairCode=challenge["pairCode"]), "RemotePairingPreview")
            request("POST", "/pairings/" + challenge["pairRequestId"] + "/confirm", dict(pairCode=challenge["pairCode"]), "RemoteDeviceView")
            print("pairing preview and confirmation: PASS")
            worker = challenge["workerId"]
            def hello():
                return dict(type="worker.hello", wireRevision=2, protocolVersion=dto.PROTOCOL_VERSION, workerId=worker, workerStoreId=store, workerEpoch=epoch, platform="linux", architecture="x86_64", capabilityRevision=1, lastServerAck=None)
            def receive(ws):
                value = json.loads(ws.recv(timeout=5))
                dto.RemoteV2ServerOutboundFrame.model_validate(value)
                return value
            def send(ws, value):
                dto.RemoteV2WorkerOutboundFrame.model_validate(value)
                ws.send(json.dumps(value))
            seq = 0
            def emit(ws, kind, **fields):
                nonlocal seq
                seq += 1
                value = dict(type=kind, wireRevision=2, eventId=uid(), workerId=worker, workerStoreId=store, workerEpoch=epoch, seq=seq, occurredAt=stamp(time.time()), **fields)
                send(ws, value)
                ack = receive(ws)
                assert ack['type'] == 'worker.events_ack' and ack['position']['seq'] == seq
            def grant(ws, command):
                emit(ws, 'command.received', commandId=command['commandId'], conversationId=command['conversationId'], commandDigest=digest(command), deliverBy=command['deliverBy'], receivedAt=stamp(time.time()))
                permission = receive(ws)
                assert permission['type'] == 'command.delivery_granted' and permission['commandDigest'] == digest(command)
                emit(ws, 'command.accepted', commandId=command['commandId'], conversationId=command['conversationId'], receivedAt=stamp(time.time()), status='accepted')
            ws_headers = {"Authorization": "Bearer " + secret, "X-Forwarded-Proto": "https"}
            with connect(f"ws://127.0.0.1:{port}/ws/v2/worker", additional_headers=ws_headers, proxy=None) as ws:
                send(ws, hello())
                handshake = receive(ws)
                assert handshake["commandDelivery"] == "ready"
                catalog = dict(workerId=worker, workerStoreId=store, capabilityRevision=1, observedAt=stamp(time.time()), workspaces=[dict(workspaceId="workspace", name="Smoke", displayPath="/workspace", vcs="git", canWrite=True)], scenes=[dict(sceneId="scene", name="Smoke", version=1, readOnly=False)], remotelyBlockedActions=[])
                emit(ws, 'capability.changed', payload=catalog)
                emit(ws, 'sync.busy.snapshot', snapshotId=uid(), connectionId=handshake['connectionId'], capturedAt=stamp(time.time()), partIndex=0, partCount=1, conversationIds=[])
                create_response = request('POST', '/conversations', dict(targetWorkerId=worker, workerStoreId=store, title='Smoke', workspaceId='workspace', sceneId='scene', sceneVersion=1), 'RemoteQueuedReceipt')
                assert create_response.status_code == 202
                conv = create_response.json()['data']['conversationId']
                command = receive(ws)
                assert command['type'] == 'conversation.create'
                grant(ws, command)
                local = command['localConversationId']
                emit(ws, 'sync.conversation.upserted', syncGeneration=1, payload=dict(conversationId=local, workspaceId='workspace', sceneId='scene', sceneVersion=1, title='Smoke', createdAt=stamp(time.time()), updatedAt=stamp(time.time()), archived=False, visibility='both', metadataVersion=1, authority='remote'))
                control = dict(outcome='confirmed', executionMayStillBeRunning=False, orphanProcessIds=[], reason='Metadata committed', evidence='metadata_committed', observedAt=stamp(time.time()))
                emit(ws, 'command.completed', commandId=command['commandId'], conversationId=conv, resultStatus='confirmed', controlResult=control)
                queued = request('POST', '/conversations/' + conv + '/messages', dict(clientMessageId=uid(), text='Smoke communication only', sessionMode='new'), 'RemoteQueuedReceipt').json()['data']
                assert queued['deliveryState'] == 'queued_online'
                submit = receive(ws)
                grant(ws, submit)
                answer = 'Complete reply from fake computer'
                emit(ws, 'sync.message.segment', syncGeneration=1, payload=dict(messageId='message-local', conversationId=local, messageSequence=1, messageRevision=1, role='assistant', createdAt=stamp(time.time()), text=answer, segmentIndex=0, segmentCount=1, totalUtf8Bytes=len(answer.encode()), contentSha256=hashlib.sha256(answer.encode()).hexdigest()))
                messages = request('GET', '/conversations/' + conv + '/messages', model='RemoteSyncMessagePage').json()['data']
                assert messages['items'][0]['text'] == answer
            offline = client.post('/api/v2/conversations/' + conv + '/messages', json=dict(clientMessageId=uid(), text='Must not queue', sessionMode='new'), headers={'Idempotency-Key': uid()})
            dto.ApiEnvelope.model_validate(offline.json())
            assert offline.status_code == 409 and offline.json()['error']['code'] == 'REMOTE_DEVICE_OFFLINE'
            with connect(f"ws://127.0.0.1:{port}/ws/v2/worker", additional_headers=ws_headers, proxy=None) as ws:
                send(ws, hello())
                handshake = receive(ws)
                assert handshake['commandDelivery'] == 'ready'
                assert not request('GET', '/devices/' + worker, model='RemoteDeviceView').json()['data']['busySnapshotFresh']
                emit(ws, 'sync.busy.snapshot', snapshotId=uid(), connectionId=handshake['connectionId'], capturedAt=stamp(time.time()), partIndex=0, partCount=1, conversationIds=[])
            request("GET", "/conversations/" + conv + "/snapshot", model="RemoteConversationSnapshot")
            assert request("GET", "/commands/" + queued["commandId"], model="RemoteCommandView").json()["data"]["status"] == "accepted"
            print("fake Worker revision 2, create/grant/sync, offline refusal and reconnect: PASS")
            native_sensitive = native_smoke(client, port, request)
            import sqlite3
            with sqlite3.connect(data / 'hub.sqlite3') as database:
                tables = [r[0] for r in database.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                stored = '\n'.join(str(v) for table in tables for row in database.execute('SELECT * FROM "'+table+'"') for v in row)
            assert native_sensitive[2] not in stored and native_sensitive[3] not in stored
            print('ephemeral query body and selection absent from database: PASS')
            publication = client.get('/api/v2/openapi.json')
            assert publication.status_code == 200 and publication.json()['info']['version'] == dto.PROTOCOL_VERSION
            assert 'X-Request-Id' in publication.headers
            print('packaged public OpenAPI and request IDs: PASS')
            issued = request('POST', '/api-tokens', dict(name='local smoke', scopes=['devices:read','devices:manage','devices:delete']), 'RemoteApiTokenIssuedView').json()['data']
            pat_secret = issued['secret']
            pat_headers = {'Authorization': 'Bearer ' + pat_secret, 'Cookie': ''}
            device = request('GET', '/devices/' + worker, model='RemoteDeviceView', extra=pat_headers).json()['data']
            paused = request('PATCH', '/devices/' + worker, dict(expectedVersion=device['version'], remoteAccess='suspended'), 'RemoteDeviceView', pat_headers).json()['data']
            denied = client.post('/api/v2/conversations/' + conv + '/messages', json=dict(clientMessageId=uid(), text='Must not queue while suspended', sessionMode='new'), headers={'Idempotency-Key': uid()})
            assert denied.json()['error']['code'] == 'REMOTE_DEVICE_SUSPENDED'
            request('PATCH', '/devices/' + worker, dict(expectedVersion=paused['version'], remoteAccess='enabled'), 'RemoteDeviceView', pat_headers)
            request('DELETE', '/devices/' + worker, model='RemoteDeviceDeletionView', extra=pat_headers)
            request('DELETE', '/api-tokens/' + issued['token']['tokenId'], model='RemoteApiTokenRevocationView')
            invalid = client.get('/api/v2/devices', headers=pat_headers)
            assert invalid.status_code == 401 and invalid.json()['error']['code'] == 'REMOTE_API_TOKEN_INVALID'
            print('PAT issuance, device pause/resume/delete and immediate revocation: PASS')
            backup = subprocess.run([sys.executable, "-m", "server.cli", "backup", str(data / "backup.sqlite3")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)
            assert backup.returncode == 0
            print(backup.stdout.strip())
            assert password not in created.stdout + created.stderr + backup.stdout + backup.stderr
    finally:
        process.terminate()
        process.wait(timeout=10)
        log_output.close()
        logs = log_path.read_text(encoding='utf-8')
        for sensitive in (password, secret, locals().get("cookie", "no-cookie-marker"), locals().get('pat_secret', 'no-pat-marker')):
            assert sensitive not in logs
        if "challenge" in locals():
            assert challenge["pairCode"] not in logs
        for private in locals().get('native_sensitive', []):
            assert private not in logs
    print("server output credential redaction: PASS")
    print("SMOKE PASS")


if __name__ == "__main__":
    main()
