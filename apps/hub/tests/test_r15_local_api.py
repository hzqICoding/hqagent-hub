from __future__ import annotations

import asyncio

from protocol.generated.python import ApiEnvelope, LocalConversationView, RemoteSyncSettingsView
from remote_support import System, FakeRemoteServer, until, TOKEN
from test_r15_worker import local_conversation, command, receive
from test_remote_cookie_routes import login, ORIGIN


def test_v1_v2_sync_settings_share_cas_idempotency_and_cookie_security(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            original = await system.local.get("/api/v1/remote/sync-settings")
            assert original.status_code == 200
            assert original.headers["cache-control"] == "no-store"
            assert original.json()["data"] == {"mirrorEnabled": True, "version": 1, "syncGeneration": 1}
            await login(system)
            for suffix in ("link", "sync-settings"):
                response = await system.local.get("/api/v2/remote/" + suffix)
                assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
            path = "/api/v2/remote/sync-settings"
            data = {"mirrorEnabled": False, "expectedVersion": 1}
            absent_origin = await system.local.put(path, json=data, headers={"Idempotency-Key": "off"})
            assert absent_origin.status_code == 403
            absent_key = await system.local.put(path, json=data, headers={"Origin": ORIGIN})
            assert absent_key.status_code == 422 and absent_key.json()["error"]["code"] == "VALIDATION_FAILED"
            headers = {"Origin": ORIGIN, "Idempotency-Key": "off"}
            response = await system.local.put(path, json=data, headers=headers)
            assert response.status_code == 200, response.text
            RemoteSyncSettingsView.model_validate(response.json()["data"])
            assert response.json()["data"] == {"mirrorEnabled": False, "version": 2, "syncGeneration": 2}
            duplicate = await system.local.put(path, json=data, headers=headers)
            assert duplicate.json()["data"] == response.json()["data"]
            stale = await system.local.put(path, json=data, headers={**headers, "Idempotency-Key": "stale"})
            assert stale.status_code == 409 and stale.json()["error"]["code"] == "CONFLICT"
            v1_cookie = await system.local.get("/api/v1/remote/sync-settings")
            assert v1_cookie.status_code == 401
            enabled = await system.local.put("/api/v1/remote/sync-settings", json={"mirrorEnabled": True, "expectedVersion": 2},
                headers={"Authorization": "Bearer " + TOKEN, "Idempotency-Key": "on"})
            assert enabled.status_code == 200
            assert enabled.json()["data"] == {"mirrorEnabled": True, "version": 3, "syncGeneration": 3}
            for value in (original, response, duplicate, stale, enabled):
                ApiEnvelope.model_validate(value.json())
                assert TOKEN not in value.text and "Authorization" not in value.text and '"secret"' not in value.text
            system.local.cookies.clear()
            for method in ("GET", "PUT"):
                unauth = await system.local.request(method, path, json=data if method == "PUT" else None, headers=headers)
                assert unauth.status_code == 401
        finally:
            await system.close()
    asyncio.run(scenario())


def test_visibility_filters_only_display_and_all_three_values_fully_sync(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            ids = {}
            for visibility in ("both", "pc_only", "mobile_only"):
                view = await local_conversation(system, visibility)
                response = await system.local.patch(f"/api/v1/conversations/{view.id}", json={
                    "visibility": visibility, "expectedVersion": 1}, headers={"Idempotency-Key": "visibility-" + visibility})
                assert response.status_code == 200, response.text
                result = LocalConversationView.model_validate(response.json()["data"])
                assert result.visibility == visibility and result.version == 2
                ids[visibility] = view.id
            await login(system)
            for prefix, headers in (("/api/v1", {"Authorization": "Bearer " + TOKEN}), ("/api/v2", {})):
                for include_hidden in (False, True):
                    response = await system.local.get(prefix + "/conversations", params={"includeHidden": str(include_hidden).lower()}, headers=headers)
                    assert response.status_code == 200, response.text
                    values = [LocalConversationView.model_validate(v) for v in response.json()["data"]]
                    assert {v.id for v in values} == set(ids.values() if include_hidden else (ids["both"], ids["pc_only"]))
            # Cookie PATCH can recover a hidden item by its stable local ID.
            response = await system.local.patch("/api/v2/conversations/" + ids["mobile_only"],
                json={"visibility": "both", "expectedVersion": 2}, headers={"Origin": ORIGIN, "Idempotency-Key": "recover-hidden"})
            assert response.status_code == 200 and response.json()["data"]["version"] == 3
            restore = await system.local.patch("/api/v2/conversations/" + ids["mobile_only"],
                json={"visibility": "mobile_only", "expectedVersion": 3}, headers={"Origin": ORIGIN, "Idempotency-Key": "hide-again"})
            assert restore.status_code == 200
            system.local.headers["Authorization"] = "Bearer " + TOKEN
            with system.db.transaction() as tx:
                for visibility, conversation in ids.items():
                    from storage.local_chat import now
                    tx.connection.execute("INSERT INTO local_messages VALUES(?,?,?,?,?,?,?)",
                        ("message-" + visibility, conversation, 1, "assistant", visibility + " full content", None, now()))
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                await until(lambda: system.repo.get("sync-work")["phase"] == "synced")
                assert len(server.replica_messages) == 3
                metadata = {f["payload"]["conversationId"]: f["payload"] for f in server.frames if f["type"] == "sync.conversation.upserted"}
                assert set(metadata) == set(ids.values())
                for visibility, conversation in ids.items():
                    assert metadata[conversation]["visibility"] == visibility
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_unlink_releases_provisional_without_downgrading_authority_or_hanging_local_send(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            conversation = await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server, start=True)
                await receive(server, command(system, "held-unlink", conversation.id))
                assert system.worker.busy.ids() == [conversation.id]
                result = await system.local.post("/api/v1/remote/unlink", headers={"Idempotency-Key": "unlink"})
                assert result.status_code == 200
                assert system.worker.busy.ids() == []
                assert system.worker.sync.settings().mirror_enabled
                response = await system.local.post(f"/api/v2/conversations/{conversation.id}/messages", json={
                    "clientMessageId": "after-unlink", "text": "local offline input", "sessionMode": "new"},
                    headers={"Idempotency-Key": "after-unlink"})
                assert response.status_code == 202, response.text
                await until(lambda: system.chat.repository.run_record(response.json()["data"]["runId"])["status"] == "succeeded")
                assert len(system.adapter.started) == 1
        finally:
            await system.close()
    asyncio.run(scenario())
