from __future__ import annotations

import asyncio
import platform
import sys
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from protocol.generated.python import (ApiEnvelope, RemoteLinkPairingInput, RemotePairingChallenge,
    RemotePairingRequestInput, RemotePairingStatusView)
from core.errors import HubError
from storage.idempotency import request_hash
from storage.local_chat import uid
from runtime.remote.security import normalize_origin, safe_text


def expired(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")) <= datetime.now(timezone.utc)


def machine():
    return {"platform": "windows" if sys.platform == "win32" else sys.platform,
        "architecture": "aarch64" if platform.machine().lower() in {"arm64", "aarch64"} else "x86_64"}


class PairingHTTP:
    def __init__(self, vault, *, transport=None):
        self.vault, self.transport = vault, transport

    async def request(self, origin, method, path, *, value=None, key=None):
        # No redirects (including same-origin), cookies, environment proxies or
        # HTTP debug logger carrying Authorization. Errors are never reflected.
        headers = {"Authorization": "Bearer " + self.vault.read()}
        if key:
            headers["Idempotency-Key"] = key
        try:
            async with httpx.AsyncClient(follow_redirects=False, trust_env=False, timeout=10,
                                        transport=self.transport) as client:
                response = await client.request(method, origin + path, headers=headers, json=value)
            if response.status_code == 410:
                raise HubError("REMOTE_PAIRING_EXPIRED", "配对请求已过期")
            if response.status_code in {401, 403}:
                raise HubError("REMOTE_DEVICE_AUTH_FAILED", "设备认证未通过")
            if not 200 <= response.status_code < 300:
                raise ValueError()
            raw = response.json()
            envelope = ApiEnvelope.model_validate(raw)
            if not envelope.success:
                raise ValueError()
            return envelope.data
        except HubError:
            raise
        except Exception:
            raise HubError("REMOTE_SERVER_UNREACHABLE", "远程服务请求未确认，可用相同请求标识重试") from None


class LinkService:
    def __init__(self, repository, vault, *, development=False, http=None, hub_token=""):
        self.repo, self.vault = repository, vault
        self.development = development
        self.http = http or PairingHTTP(vault)
        self.hub_token = hub_token
        self.lock = asyncio.Lock()
        self.disconnect = None
        self.before_clear = None

    def sanitized(self, value):
        secret = self.vault.read() if self.vault.path.exists() else ""
        return safe_text(value, (self.hub_token, secret))

    def contains_credentials(self, value):
        secret = self.vault.read() if self.vault.path.exists() else ""
        return any(item and item in value for item in (self.hub_token, secret))

    async def view(self):
        async with self.lock:
            self._expire()
            return self.repo.view()

    def _expire(self):
        link = self.repo.get("link")
        if link["view"]["state"] == "pairing" and expired(link["view"]["expiresAt"]):
            self._clear("REMOTE_PAIRING_EXPIRED")

    def _operation(self, tx, route, key, request, generation):
        if not key or len(key) > 200:
            raise HubError("VALIDATION_FAILED", "必须提供不超过200字符的Idempotency-Key")
        digest = request_hash(request)
        row = tx.connection.execute("SELECT digest,generation FROM remote_operations WHERE route=? AND key=?", (route, key)).fetchone()
        if row:
            if row[0] != digest:
                raise HubError("IDEMPOTENCY_MISMATCH", "相同请求标识不能用于不同内容")
            return row[1]
        tx.connection.execute("INSERT INTO remote_operations VALUES(?,?,?,?)", (route, key, digest, generation))
        return None

    async def pair(self, value: RemoteLinkPairingInput, key):
        origin = normalize_origin(value.server_origin, development=self.development)
        if self.contains_credentials(origin):
            raise HubError("REMOTE_SERVER_ORIGIN_INVALID", "远程地址不允许包含凭据")
        device = self.sanitized(value.device_name)
        request = {"serverOrigin": origin, "deviceName": device}
        async with self.lock:
            self._expire()
            link = self.repo.get("link")
            with self.repo.database.transaction() as tx:
                generation = link["generation"] + 1
                prior = self._operation(tx, "pair", key, request, generation)
                if prior is not None:
                    if prior != link["generation"] or not link.get("intent"):
                        return self.repo.view()
                else:
                    if link["view"]["state"] in {"paired", "revoked", "frozen"}:
                        raise HubError("REMOTE_PAIRING_CONFLICT", "当前绑定须先显式解绑")
                    if link.get("intent") or link["view"]["state"] == "pairing":
                        raise HubError("REMOTE_PAIRING_IN_PROGRESS", "已有进行中的配对")
                    self.vault.create()
                    self.repo.new_binding_store(tx)
                    link.update(generation=generation, intent={**request, "requestKey": uid("pair")})
                    self.repo.put("link", link, tx)
                    self.repo.seal(tx)
            if link["view"]["state"] == "pairing":
                return self.repo.view()
            generation = link["generation"]
            intent = link["intent"]
            body = RemotePairingRequestInput.model_validate({"deviceName": device,
                "workerStoreId": self.repo.get("identity")["store"], **machine()})
        try:
            raw = await self.http.request(origin, "POST", "/api/v2/worker/pairing-requests",
                value=body.model_dump(mode="json", by_alias=True), key=intent["requestKey"])
            challenge = RemotePairingChallenge.model_validate(raw)
        except Exception as error:
            code = error.code if isinstance(error, HubError) else "REMOTE_SERVER_UNREACHABLE"
            async with self.lock:
                current = self.repo.get("link")
                if generation == current["generation"] and current["view"]["state"] == "unpaired":
                    if code == "REMOTE_PAIRING_EXPIRED":
                        self._clear(code)
                    else:
                        with self.repo.database.transaction() as tx:
                            self.repo.set_view(tx, {"state": "unpaired", "serverOrigin": origin, "lastErrorCode": code})
                            self.repo.seal(tx)
            if isinstance(error, HubError):
                raise HubError(error.code, "配对请求未确认，请重试或取消") from None
            raise HubError("REMOTE_SERVER_UNREACHABLE", "配对响应无效") from None
        async with self.lock:
            link = self.repo.get("link")
            if generation != link["generation"]:
                return self.repo.view()
            if link["view"]["state"] != "unpaired":
                return self.repo.view()
            if expired(challenge.expires_at):
                self._clear("REMOTE_PAIRING_EXPIRED")
                return self.repo.view()
            # Reject reflected credential material even in otherwise valid IDs.
            if self.sanitized(challenge.pair_request_id) != challenge.pair_request_id or self.sanitized(challenge.worker_id) != challenge.worker_id:
                raise HubError("REMOTE_SERVER_UNREACHABLE", "配对响应无效")
            with self.repo.database.transaction() as tx:
                link["candidateWorkerId"] = challenge.worker_id
                self.repo.put("link", link, tx)
                self.repo.set_view(tx, {"state": "pairing", **request, "pairRequestId": challenge.pair_request_id,
                    "pairCode": challenge.pair_code, "expiresAt": challenge.expires_at})
                self.repo.seal(tx)
            return self.repo.view()

    def _clear_in_transaction(self, tx, code=None):
        self.vault.delete()  # On failure both the intent and completion roll back.
        if self.before_clear is not None:
            self.before_clear(tx)
        link = self.repo.get("link", tx)
        value = {"state": "unpaired"}
        if link["view"].get("serverOrigin"):
            value["serverOrigin"] = link["view"]["serverOrigin"]
        if code:
            value["lastErrorCode"] = code
        self.repo.put("link", {"view": link["view"], "generation": link["generation"] + 1}, tx)
        self.repo.set_view(tx, value)
        self.repo.seal(tx)

    def _clear(self, code=None):
        with self.repo.database.transaction() as tx:
            self._clear_in_transaction(tx, code)

    async def clear(self, key, *, unlink=False):
        async with self.lock:
            link = self.repo.get("link")
            with self.repo.database.transaction() as tx:
                prior = self._operation(tx, "unlink" if unlink else "cancel", key, {}, link["generation"])
                if prior is not None:
                    return self.repo.view()
                if not unlink and link["view"]["state"] in {"paired", "revoked", "frozen"}:
                    raise HubError("REMOTE_PAIRING_CONFLICT", "当前绑定须先显式解绑")
                self._clear_in_transaction(tx, "REMOTE_AUTH_REQUIRED" if unlink and link["view"]["state"] != "unpaired" else None)
            if self.disconnect:
                await self.disconnect()
            return self.repo.view()

    async def poll(self):
        async with self.lock:
            self._expire()
            link = self.repo.get("link")
            if link["view"]["state"] != "pairing":
                return
            view, generation = link["view"], link["generation"]
        origin = normalize_origin(view["serverOrigin"], development=self.development)
        try:
            raw = await self.http.request(origin, "GET", "/api/v2/worker/pairing-requests/" + quote(view["pairRequestId"], safe=""))
        except HubError as error:
            if error.code in {"REMOTE_PAIRING_EXPIRED", "REMOTE_DEVICE_AUTH_FAILED"}:
                async with self.lock:
                    if generation == self.repo.get("link")["generation"]:
                        self._clear(error.code)
            raise
        try:
            status = RemotePairingStatusView.model_validate(raw)
        except Exception:
            raise HubError("REMOTE_SERVER_UNREACHABLE", "配对状态响应无效") from None
        async with self.lock:
            link = self.repo.get("link")
            if generation != link["generation"] or link["view"]["state"] != "pairing":
                return
            if status.pair_request_id != view["pairRequestId"] or status.worker_id != link["candidateWorkerId"]:
                raise HubError("REMOTE_TARGET_MISMATCH", "配对响应引用不匹配")
            if expired(view["expiresAt"]) or str(status.status) in {"expired", "revoked"}:
                self._clear("REMOTE_PAIRING_EXPIRED")
            elif str(status.status) == "paired":
                with self.repo.database.transaction() as tx:
                    link.pop("intent", None)
                    self.repo.put("link", link, tx)
                    self.repo.set_view(tx, {"state": "paired", "serverOrigin": view["serverOrigin"],
                        "deviceName": view["deviceName"], "workerId": status.worker_id,
                        "connectionStatus": "offline", "lastConnectedAt": None})
                    self.repo.seal(tx)
