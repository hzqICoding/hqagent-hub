from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from protocol.generated.python import ApiEnvelope, RemoteLinkView
from core.local_auth import COOKIE_NAME
from runtime.remote.link import PairingHTTP
from remote_support import FakeRemoteServer, System, TOKEN

ORIGIN = "http://127.0.0.1"
OPERATIONS = [("GET", "link"), ("POST", "pairing"), ("DELETE", "pairing"), ("POST", "unlink")]
WRITES = OPERATIONS[1:]
PAIR_INPUT = {"serverOrigin": "https://remote.invalid", "deviceName": "browser"}


async def login(system):
    # Same local-session exchange as the existing browser-workbench tests.
    # No Hub Bearer is available to the browser client for any of these requests.
    system.local.headers.pop("Authorization", None)
    code = system.application.local_auth.issue_code("browser-connection-code")
    response = await system.local.post("/api/v2/auth/local-session", json={"code": code},
                                       headers={"Origin": ORIGIN})
    assert response.status_code == 200
    assert COOKIE_NAME in system.local.cookies
    assert "httponly" in response.headers["set-cookie"].lower()
    assert TOKEN not in response.text


def assert_response(response, *, status=200, credentials=()):
    assert response.status_code == status, response.text
    assert response.headers["cache-control"] == "no-store"
    value = response.json()
    ApiEnvelope.model_validate(value)
    if value["success"]:
        RemoteLinkView.model_validate(value["data"])
    assert TOKEN not in response.text
    assert "authorization" not in response.text.lower()
    assert '"secret"' not in response.text.lower()
    for secret in credentials:
        assert secret not in response.text
        assert "Bearer " + secret not in response.text
    return value.get("data")


def test_cookie_pairing_query_cancel_unlink_and_v1_share_one_link_service(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            await login(system)
            async with FakeRemoteServer() as server:
                system.link.http = PairingHTTP(system.link.vault,
                    transport=httpx.AsyncHTTPTransport(verify=server.client_tls))
                body = {**PAIR_INPUT, "serverOrigin": server.origin}
                headers = {"Origin": ORIGIN, "Idempotency-Key": "browser-pair"}
                initial = await system.local.post("/api/v2/remote/pairing", json=body, headers=headers)
                first_secret = system.link.vault.read()
                pairing = assert_response(initial, credentials=(first_secret,))
                assert pairing["state"] == "pairing" and pairing["pairCode"] == "ABCD2345"
                snapshot = await system.local.get("/api/v2/remote/link")
                assert assert_response(snapshot, credentials=(first_secret,)) == pairing
                # v1 remains Bearer-only even though this client has a valid Cookie.
                assert_response(await system.local.get("/api/v1/remote/link"), status=401,
                                credentials=(first_secret,))
                seq = system.events.latest_seq()
                bearer = {"Authorization": "Bearer " + TOKEN, "Idempotency-Key": "browser-pair"}
                replay = await system.local.post("/api/v1/remote/pairing", json=body, headers=bearer)
                assert assert_response(replay, credentials=(first_secret,)) == pairing
                assert server.pair_calls == 1 and system.events.latest_seq() == seq
                cancelled = await system.local.delete("/api/v2/remote/pairing",
                    headers={"Origin": ORIGIN, "Idempotency-Key": "browser-cancel"})
                assert assert_response(cancelled, credentials=(first_secret,))["state"] == "unpaired"
                assert not system.link.vault.path.exists()
                assert "pairCode" not in cancelled.text

                # Re-pair and simulate the legitimate phone-side confirmation.
                server.secret = None
                paired_request = await system.local.post("/api/v2/remote/pairing", json=body,
                    headers={"Origin": ORIGIN, "Idempotency-Key": "browser-repair"})
                second_secret = system.link.vault.read()
                secrets = first_secret, second_secret
                assert_response(paired_request, credentials=secrets)
                assert first_secret != second_secret
                server.claimed = True
                await system.link.poll()
                paired = assert_response(await system.local.get("/api/v2/remote/link"), credentials=secrets)
                assert paired["state"] == "paired" and paired["lastConnectedAt"] is None
                v1 = await system.local.get("/api/v1/remote/link", headers=bearer)
                assert assert_response(v1, credentials=secrets) == paired
                conflict = await system.local.delete("/api/v2/remote/pairing",
                    headers={"Origin": ORIGIN, "Idempotency-Key": "cannot-cancel-paired"})
                assert_response(conflict, status=409, credentials=secrets)
                assert conflict.json()["error"]["code"] == "REMOTE_PAIRING_CONFLICT"
                unlink = await system.local.post("/api/v2/remote/unlink",
                    headers={"Origin": ORIGIN, "Idempotency-Key": "browser-unlink"})
                unpaired = assert_response(unlink, credentials=secrets)
                assert unpaired["state"] == "unpaired"
                assert unpaired["lastErrorCode"] == "REMOTE_AUTH_REQUIRED"
                assert not system.link.vault.path.exists()
                assert assert_response(await system.local.get("/api/v1/remote/link", headers=bearer), credentials=secrets) == unpaired
                events = [event.payload for event in system.events.page(0, 200).events
                          if event.type == "remote.link.changed"]
                assert events[-1] == unpaired
                for secret in (*secrets, TOKEN):
                    assert secret not in json.dumps(events)
                assert "Authorization" not in system.local.headers
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("method,path", OPERATIONS)
def test_v2_remote_requires_local_session(tmp_path, method, path):
    async def scenario():
        system = System(tmp_path)
        try:
            system.local.headers.pop("Authorization", None)
            response = await system.local.request(method, "/api/v2/remote/" + path,
                json=PAIR_INPUT if method == "POST" and path == "pairing" else None,
                headers={"Origin": ORIGIN, "Idempotency-Key": "unauthorized"})
            assert_response(response, status=401)
            assert response.json()["error"]["code"] == "UNAUTHORIZED"
            assert not system.link.vault.path.exists()
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("method,path", WRITES)
@pytest.mark.parametrize("failure", ["missing-origin", "foreign-origin", "missing-key"])
def test_cookie_writes_preserve_origin_and_idempotency_rules(tmp_path, method, path, failure):
    async def scenario():
        system = System(tmp_path)
        try:
            await login(system)
            headers = {"Origin": ORIGIN, "Idempotency-Key": "guard"}
            if failure == "missing-origin":
                headers.pop("Origin")
            elif failure == "foreign-origin":
                headers["Origin"] = "https://foreign.invalid"
            else:
                headers.pop("Idempotency-Key")
            seq = system.events.latest_seq()
            response = await system.local.request(method, "/api/v2/remote/" + path,
                json=PAIR_INPUT if method == "POST" and path == "pairing" else None, headers=headers)
            assert_response(response, status=422 if failure == "missing-key" else 403)
            assert response.json()["error"]["code"] == (
                "VALIDATION_FAILED" if failure == "missing-key" else "ORIGIN_NOT_ALLOWED")
            assert system.events.latest_seq() == seq and not system.link.vault.path.exists()
        finally:
            await system.close()
    asyncio.run(scenario())


def test_v1_and_v2_reuse_validation_and_do_not_echo_rejected_fields(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            await login(system)
            for index, body in enumerate((
                {**PAIR_INPUT, "serverOrigin": "https://user:password@remote.invalid"},
                {**PAIR_INPUT, "secret": TOKEN, "Authorization": "Bearer " + TOKEN},
            )):
                v1 = await system.local.post("/api/v1/remote/pairing", json=body,
                    headers={"Authorization": "Bearer " + TOKEN, "Idempotency-Key": f"invalid-{index}"})
                v2 = await system.local.post("/api/v2/remote/pairing", json=body,
                    headers={"Origin": ORIGIN, "Idempotency-Key": f"invalid-{index}"})
                assert_response(v1, status=422)
                assert_response(v2, status=422)
                assert v1.json()["error"] == v2.json()["error"]
                assert "user:password" not in v1.text + v2.text
            assert not system.link.vault.path.exists()
        finally:
            await system.close()
    asyncio.run(scenario())
