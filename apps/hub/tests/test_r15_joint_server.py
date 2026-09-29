"""Real P1 create_app + TLS socket + Worker/core; no imported field evidence."""
from __future__ import annotations

import asyncio
import json
import secrets
import socket
import ssl
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
import uvicorn
from protocol.generated import python as dto

from remote_support import System, TLS_FILES, until, WORKER_CODECS, SERVER_CODECS
from runtime.paths import HubPaths
from runtime.remote.security import CredentialVault
from runtime.remote.worker import NoRedirectConnect
from storage.database import Database
from storage.events import EventStore
from storage.local_chat import LocalChatRepository, now
from storage.remote import RemoteRepository
from storage.migrations import LATEST_SCHEMA_VERSION


@pytest.fixture(autouse=True)
def server_source(monkeypatch):
    # The server package lives in the adjacent workspace; no install/network.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "server"))


class RealPair:
    def __init__(self, path, *, hold_history=False):
        from server.config import Settings
        self.path = path
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        self.origin = f"https://127.0.0.1:{self.socket.getsockname()[1]}"
        self.settings = Settings(database=path / "server.db", key=secrets.token_bytes(32),
                                 origin=self.origin, rate_limit=10000)
        self.sent, self.received = [], []
        self.hold_history = hold_history
        self.hold_seq = None
        self.history_held = asyncio.Event()
        self.release_history = asyncio.Event()
        self.worker_id = "synthetic-r1-worker"
        self.password = "synthetic-joint-test-password"
        self._seed_r1()

    def _seed_r1(self):
        from server.repository import Repository, MIGRATIONS
        from server.security import Security
        from runtime.remote.link import machine

        class R1Repository(Repository):
            def migrate(self):
                for version in range(1, 4):
                    self.connection.executescript("BEGIN;" + MIGRATIONS[version] + f"PRAGMA user_version={version};COMMIT;")

        cloud = R1Repository(self.settings.database)
        security = Security(cloud, self.settings)
        security.create_account("joint", self.password, "Joint fixture")
        def legacy_record(tx, kind, identifier, value):
            tx.db.execute("INSERT INTO records(owner,kind,id,worker,store,parent,body) VALUES(?,?,?,?,?,?,?)", (
                self.owner, kind, identifier, value.get("targetWorkerId", value.get("workerId", "")),
                value.get("workerStoreId", ""), value.get("conversationId", ""), json.dumps(value)))
        paths = HubPaths.resolve(self.path / "data-root")
        paths.create()
        db = Database(paths.data / "hub.db")
        db.initialize(target_version=6)
        local = LocalChatRepository(db)
        repo = RemoteRepository(db, EventStore(db), paths.root / "remote")
        vault = CredentialVault(paths.root / "remote")
        vault.create()
        _, verifier = security.bearer("Bearer " + vault.read())
        store = repo.get("identity")["store"]
        with cloud.transaction() as tx:
            self.owner = tx.auth_get("account:" + security.mac("login", "joint"))["owner"]
            tx.auth_put("credential:" + verifier, dict(owner=self.owner, worker=self.worker_id), self.owner)
            legacy_record(tx, "device", self.worker_id, dict(workerId=self.worker_id,
                workerStoreId=store, deviceName="R1 fixture", **machine(), status="offline",
                capabilityRevision=1, pairedAt=now(), observedAt=now(), _frozen=False, _everConnected=True))
        with db.transaction() as tx:
            repo.set_view(tx, dict(state="paired", workerId=self.worker_id, deviceName="R1 fixture",
                                  serverOrigin=self.origin, connectionStatus="offline", lastConnectedAt=None))
            repo.seal(tx)
        self.legacy_ids = []
        for index in range(2):
            conversation = local.create_conversation(dto.CreateLocalConversationInput(
                title=f"R1 synthetic {index}", workspaceId="workspace", sceneId="analyze"), f"old-{index}")
            self.legacy_ids.append(conversation.id)
            with db.transaction() as tx:
                raw = json.loads(tx.connection.execute("SELECT payload_json FROM local_conversations WHERE conversation_id=?", (conversation.id,)).fetchone()[0])
                raw["authority"] = "remote"
                tx.connection.execute("UPDATE local_conversations SET payload_json=? WHERE conversation_id=?", (json.dumps(raw), conversation.id))
                for sequence in range(1, 13):
                    tx.connection.execute("INSERT INTO local_messages VALUES(?,?,?,?,?,?,?)", (
                        f"r1-{index}-{sequence}", conversation.id, sequence, "assistant", "synthetic history", None, now()))
            with cloud.transaction() as tx:
                legacy_record(tx, "conversation", conversation.id, dict(conversationId=conversation.id,
                    targetWorkerId=self.worker_id, workerStoreId=store, workspaceId="workspace", sceneId="analyze",
                    sceneVersion=1, title=conversation.title, authority="remote", createdAt=conversation.created_at,
                    updatedAt=conversation.updated_at, _nextSeq=1))
        assert db.schema_version == 6
        assert cloud.connection.execute("PRAGMA user_version").fetchone()[0] == 3
        db.close(); cloud.close()

    async def __aenter__(self):
        from server.app import create_app
        self.app = create_app(self.settings)
        self.service = self.app.state.service
        assert self.service.repo.connection.execute("PRAGMA user_version").fetchone()[0] == 4
        config = uvicorn.Config(self.app, log_config=None, access_log=False, log_level="critical",
            ssl_certfile=str(TLS_FILES / "test-cert.pem"), ssl_keyfile=str(TLS_FILES / "test-key.pem"),
            ws="websockets-sansio", lifespan="on")
        self.server = uvicorn.Server(config)
        self.server_job = asyncio.create_task(self.server.serve(sockets=[self.socket]))
        await until(lambda: self.server.started)
        self.tls = ssl.create_default_context(cafile=str(TLS_FILES / "test-cert.pem"))
        self.browser = httpx.AsyncClient(base_url=self.origin + "/api/v2", verify=self.tls,
            headers={"Origin": self.origin, "Idempotency-Key": "joint-login"})
        login = await self.browser.post("/auth/login", json={"loginName": "joint", "password": self.password})
        assert login.status_code == 200, login.text
        self.browser.headers["X-CSRF-Token"] = login.json()["data"]["csrfToken"]
        self.system = System(self.path)
        assert self.system.db.schema_version == LATEST_SCHEMA_VERSION
        self.system.worker.connector = self.connect
        self.system.adapter.result = self.system.adapter.result.model_copy(update={"summary": "记住了"})
        await self.system.chat.start()
        await self.system.worker.start()
        await until(lambda: any(f["type"] == "worker.hello_ack" for f in self.received))
        assert next(f for f in self.received if f["type"] == "worker.hello_ack")["wireRevision"] == 2
        assert self.system.repo.get("identity")["wireRevision"] == 2
        return self

    @asynccontextmanager
    async def connect(self, uri, **kwargs):
        pair = self
        async with NoRedirectConnect(uri, ssl=self.tls, **kwargs) as ws:
            class TracedSocket:
                async def send(self, raw):
                    frame = WORKER_CODECS[json.loads(raw)["wireRevision"]].model_validate_json(raw).model_dump(mode="json", by_alias=True, exclude_none=True)
                    pair.sent.append(frame)
                    if pair.hold_history and pair.hold_seq is None and frame["type"] == "sync.backfill.progress" and not frame["complete"]:
                        pair.hold_seq = frame["seq"]
                    await ws.send(raw)

                async def incoming(self, raw):
                    frame = SERVER_CODECS[json.loads(raw)["wireRevision"]].model_validate_json(raw).model_dump(mode="json", by_alias=True, exclude_none=True)
                    pair.received.append(frame)
                    if frame["type"] == "worker.events_ack" and pair.hold_seq is not None and frame["position"]["seq"] >= pair.hold_seq:
                        pair.history_held.set()
                        await pair.release_history.wait()
                    return raw

                async def recv(self):
                    return await self.incoming(await ws.recv())

                async def messages(self):
                    async for raw in ws:
                        yield await self.incoming(raw)

                def __aiter__(self):
                    return self.messages()

                async def close(self):
                    await ws.close()

            yield TracedSocket()

    async def __aexit__(self, *_args):
        self.release_history.set()
        await self.system.close()
        await self.browser.aclose()
        self.server.should_exit = True
        await asyncio.wait_for(self.server_job, 5)
        self.socket.close()

    def cloud_conversation(self, local):
        with self.service.repo.transaction() as tx:
            values = tx.list(self.owner, "conversation", worker=self.worker_id)
            return next((v for v in values if v.get("_localId") == local), None)

    def cloud_messages(self, local):
        conversation = self.cloud_conversation(local)
        if conversation is None:
            return []
        with self.service.repo.transaction() as tx:
            return tx.list(self.owner, "message", parent=conversation["conversationId"])

    async def send_local(self, conversation, key):
        response = await self.system.local.post(f"/api/v2/conversations/{conversation}/messages", json={
            "clientMessageId": key, "text": "remember synthetic context", "sessionMode": "new"}, headers={"Idempotency-Key": key})
        assert response.status_code == 202, response.text
        run_id = response.json()["data"]["runId"]
        await until(lambda: self.system.chat.repository.run_record(run_id)["status"] == "succeeded")
        return run_id

    async def mirrored(self, local, answers):
        def finished():
            return self.system.repo.get("link")["view"]["state"] == "frozen" or len([
                m for m in self.cloud_messages(local) if m["role"] == "assistant" and "记住了" in m["text"]]) >= answers
        await until(finished, timeout=12)
        errors = [f for f in self.received if f["type"] == "worker.hello_rejected"]
        assert self.system.repo.get("link")["view"]["state"] == "paired", {
            "hubError": self.system.repo.get("link")["view"].get("lastErrorCode"),
            "receivedErrors": errors,
            "metadata": [{k:f["payload"][k] for k in ("metadataVersion", "updatedAt")} for f in self.sent
                         if f["type"] == "sync.conversation.upserted" and f["payload"]["conversationId"] == local]}


@pytest.mark.parametrize("during_history", [False, True])
def test_real_r1_upgrade_backfill_and_computer_rounds_keep_reply_and_connection(tmp_path, during_history):
    async def scenario():
        async with RealPair(tmp_path, hold_history=during_history) as pair:
            if during_history:
                await asyncio.wait_for(pair.history_held.wait(), 5)
                assert pair.system.repo.get("sync-work")["phase"] == "backfilling"
            else:
                await until(lambda: pair.system.repo.get("sync-work")["phase"] == "synced")
            created = await pair.system.local.post("/api/v2/conversations", json={"title": "电脑建的对话",
                "workspaceId": "workspace", "sceneId": "analyze"}, headers={"Idempotency-Key": "computer-create"})
            assert created.status_code == 201
            conversation = dto.LocalConversationView.model_validate(created.json()["data"])
            if not during_history:
                await until(lambda: pair.cloud_conversation(conversation.id) is not None)
            await pair.send_local(conversation.id, "first")
            if during_history:
                assert pair.cloud_conversation(conversation.id) is None
                assert not any(f.get("complete") for f in pair.sent if f["type"] == "sync.backfill.progress")
                pair.release_history.set()
            await pair.mirrored(conversation.id, 1)
            await pair.send_local(conversation.id, "second")
            await pair.mirrored(conversation.id, 2)
            assert all(pair.cloud_conversation(c) for c in pair.legacy_ids)
            assert pair.system.chat.repository.conversation(conversation.id).version == 1
            await until(lambda: not pair.cloud_conversation(conversation.id).get("_busy"))
            response = await pair.browser.get("/conversations/" + pair.cloud_conversation(conversation.id)["conversationId"])
            view = dto.RemoteConversationView.model_validate(response.json()["data"])
            assert view.busy is False and view.busy_fresh is True
            page = await pair.browser.get("/conversations/" + view.conversation_id + "/messages")
            messages = dto.RemoteSyncMessagePage.model_validate(page.json()["data"])
            assert len([m for m in messages.items if str(m.role) == 'assistant' and '记住了' in m.text]) == 2
            if not during_history:
                # Continue the same computer Session through the real P1 grant
                # path too; schema-compatible fake endpoints cannot hide drift.
                receipt = await pair.browser.post("/conversations/" + view.conversation_id + "/messages",
                    json={"clientMessageId": "phone", "text": "continue remembered context", "sessionMode": "continue"},
                    headers={"Idempotency-Key": "phone"})
                assert receipt.status_code == 202, receipt.text
                dto.RemoteQueuedReceipt.model_validate(receipt.json()["data"])
                await pair.mirrored(conversation.id, 3)
                assert len(pair.system.adapter.resumed) == 1
            assert not [f for f in pair.received if f["type"] == "worker.hello_rejected" and f["error"]["code"] != "REMOTE_PROTOCOL_UNSUPPORTED"]
    asyncio.run(scenario())


def test_real_server_rejection_preserves_error_instead_of_inventing_epoch_failure(tmp_path):
    async def scenario():
        async with RealPair(tmp_path) as pair:
            await until(lambda: pair.system.repo.get("sync-work")["phase"] == "synced")
            original = next(f for f in pair.sent if f["type"] == "sync.conversation.upserted")
            # A genuine same-version metadata conflict, not an activity update.
            with pair.system.db.transaction() as tx:
                pair.system.repo.emit(tx, "sync.conversation.upserted", syncGeneration=1,
                    payload={**original["payload"], "title": "conflicting metadata"})
                pair.system.repo.seal(tx)
            await until(lambda: pair.system.repo.get("link")["view"]["state"] == "frozen")
            assert pair.received[-1]["type"] == "worker.hello_rejected"
            assert pair.received[-1]["error"]["code"] == "REMOTE_SYNC_CONFLICT"
            assert pair.system.repo.get("link")["view"]["lastErrorCode"] == "REMOTE_SYNC_CONFLICT"
            hello = next(f for f in pair.received if f["type"] == "worker.hello_ack")
            assert all(f['connectionId'] == hello['connectionId'] for f in pair.received
                       if f['type'] in {'worker.events_ack', 'server.heartbeat'})
            with pair.service.repo.transaction() as tx:
                device = pair.service.get(tx, pair.owner, 'device', pair.worker_id)
                assert not device['_frozen']
                assert device['_epoch'] == pair.system.repo.get('identity')['epoch']
    asyncio.run(scenario())
