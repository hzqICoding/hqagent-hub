"""Local-only root CAS and short-lived, opaque directory selections."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from contextlib import ExitStack, contextmanager

from protocol.generated.python import LocalAuthorizedRootsView, DirectoryListingPage
from core.errors import HubError
from storage.events import EventDraft
from storage.local_chat import uid
from runtime.native.paths import absolute_directory, directory_lease, denied


class AuthorizedRoots:
    def __init__(self, repository, chat_repository, *, monotonic=time.monotonic):
        self.repo, self.chat = repository, chat_repository
        self.clock = monotonic
        self.references = {}
        with self.repo.database.transaction() as tx:
            if self.repo.get("authorized-roots", tx) is None:
                self.repo.put("authorized-roots", {"version": 1, "roots": []}, tx)
                self.repo.seal(tx)

    def view(self):
        state = self.repo.get("authorized-roots")
        return LocalAuthorizedRootsView.model_validate({"version": state["version"],
            "roots": [{k: v for k, v in r.items() if not k.startswith("_")} for r in state["roots"]]})

    def catalog(self):
        return [{k: root[k] for k in ("rootId", "displayName", "version")}
                for root in self.repo.get("authorized-roots")["roots"]]

    def replace(self, value, key):
        def change(tx):
            current = self.repo.get("authorized-roots", tx)
            if current["version"] != value.expected_version:
                raise HubError("CONFLICT", "授权根目录已变化，请刷新后重试")
            old = {r["rootId"]: r for r in current["roots"]}
            roots, ids, identities = [], set(), set()
            with ExitStack() as leases:
                for requested in value.roots:
                    title = requested.display_name.strip()
                    if not title:
                        raise HubError("VALIDATION_FAILED", "根目录名称不能为空")
                    root_id = requested.root_id
                    if root_id is not None and (root_id not in old or root_id in ids):
                        raise HubError("REMOTE_ROOT_NOT_AUTHORIZED", "根目录引用不属于当前配置")
                    path, identity = leases.enter_context(directory_lease(requested.path))
                    if identity in identities:
                        raise HubError("CONFLICT", "不能重复授权相同真实目录")
                    identities.add(identity)
                    root_id = root_id or uid("root")
                    ids.add(root_id)
                    before = old.get(root_id)
                    changed = before is not None and (before["path"] != str(path) or
                        before["displayName"] != title or before["_identity"] != list(identity))
                    roots.append({"rootId": root_id, "displayName": title, "path": str(path),
                        "version": before["version"] + int(changed) if before else 1, "_identity": list(identity)})
                state = {"version": current["version"] + 1, "roots": roots}
                self.repo.put("authorized-roots", state, tx)
                # Durable intent; the revision-3 catalog publisher consumes it.
                self.repo.put("authorized-roots-catalog-pending", {"version": state["version"]}, tx)
                self.repo.seal(tx)
            return {"version": state["version"], "roots": [
                {k: v for k, v in r.items() if not k.startswith("_")} for r in roots]}
        result, _ = self.chat.command("remote.authorized-roots", key,
            value.model_dump(mode="json", by_alias=True), change)
        return LocalAuthorizedRootsView.model_validate(result)

    def _root(self, root_id, version):
        root = next((r for r in self.repo.get("authorized-roots")["roots"] if r["rootId"] == root_id), None)
        if root is None or root["version"] != version:
            raise HubError("REMOTE_ROOT_NOT_AUTHORIZED", "授权根目录已移除或变化")
        return root

    def _prune(self):
        stamp = self.clock()
        self.references = {k: v for k, v in self.references.items() if v["expires"] > stamp}

    def _token(self, root, path, identity, *, listing=None, offset=0):
        self._prune()
        if len(self.references) >= 4096:
            raise HubError("REMOTE_RATE_LIMITED", "目录选择引用过多，请稍后重试")
        token = secrets.token_urlsafe(32)
        self.references[token] = {"store": self.repo.get("identity")["store"], "rootId": root["rootId"],
            "rootVersion": root["version"], "path": str(path), "identity": identity,
            "expires": self.clock() + 900, "listing": listing, "offset": offset}
        return token

    def _reference(self, token, root, *, cursor=False):
        self._prune()
        value = self.references.get(token)
        if (value is None or value["store"] != self.repo.get("identity")["store"] or
                value["rootId"] != root["rootId"] or value["rootVersion"] != root["version"] or
                (value["listing"] is not None) != cursor):
            raise denied("REMOTE_DIRECTORY_CHANGED")
        return value

    @contextmanager
    def selected(self, root_id, version, token):
        root = self._root(root_id, version)
        ref = self._reference(token, root)
        with directory_lease(root["path"], identity=root["_identity"]) as (base, _):
            with directory_lease(ref["path"], root=base, identity=ref["identity"]) as target:
                yield target
                self._root(root_id, version)

    def audit(self, request_id, root_id, code):
        with self.repo.database.transaction() as tx:
            self.repo.events.append(tx, EventDraft(aggregate_type="system", aggregate_id="directory-audit",
                type="remote.directory.audited", payload={"requestId": request_id, "operation": "directory.list",
                "rootId": root_id, "resultCode": code}))
            self.repo.seal(tx)

    def listing(self, value, request_id):
        try:
            result = self._listing(value)
        except HubError as error:
            self.audit(request_id, value.root_id, error.code)
            raise
        self.audit(request_id, value.root_id, "OK")
        return result

    def _listing(self, value):
        root = self._root(value.root_id, value.root_version)
        reference = self._reference(value.directory_token, root) if value.directory_token else None
        with directory_lease(root["path"], identity=root["_identity"]) as (base, _):
            with directory_lease(reference["path"] if reference else root["path"], root=base,
                    identity=reference["identity"] if reference else root["_identity"]) as (directory, identity):
                rows = []
                modified = directory.stat().st_mtime_ns
                for child in directory.iterdir():
                    if child.suffix.lower() == ".lnk" or not child.is_dir():
                        continue
                    absolute_directory(str(child))
                    with directory_lease(str(child), root=base) as (_, child_identity):
                        rows.append((child.name, str(child), child_identity, (child / ".git").is_dir()))
                    if len(rows) > 10000:
                        raise HubError("REMOTE_QUERY_TOO_LARGE", "目录规模超过当前安全浏览限额")
                rows.sort(key=lambda row: (row[0].casefold(), row[0], row[2]))
                digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()
                offset = 0
                if value.cursor:
                    cursor = self._reference(value.cursor, root, cursor=True)
                    if cursor["identity"] != identity or cursor["listing"] != digest:
                        raise denied("REMOTE_DIRECTORY_CHANGED")
                    offset = cursor["offset"]
                limit = value.limit or 50
                page = rows[offset:offset + limit]
                body = {"rootId": root["rootId"], "rootVersion": root["version"],
                    "directoryToken": self._token(root, directory, identity),
                    "entries": [{"name": name, "isGitRepository": git, "directoryToken": self._token(root, path, ident)}
                                for name, path, ident, git in page], "hasMore": offset + len(page) < len(rows)}
                if body["hasMore"]:
                    body["nextCursor"] = self._token(root, directory, identity, listing=digest, offset=offset + len(page))
                self._root(value.root_id, value.root_version)
                if directory.stat().st_mtime_ns != modified:
                    raise denied("REMOTE_DIRECTORY_CHANGED")
                return DirectoryListingPage.model_validate(body)
