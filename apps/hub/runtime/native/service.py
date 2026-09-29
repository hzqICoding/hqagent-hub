"""Local native authority, independent of the remote link and wire revision."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import time
from pathlib import Path

from protocol.generated.python import (NativeSessionIndex, LocalNativeSessionPage, NativeMessagePage,
    NativeClosureConfirmation, LocalConversationView, AgentTaskSpec, SessionView, CreateTaskInput,
    SaveTeamProfileInput)
from adapters.history import FileHistory, HistorySource, digest, public_text
from core.errors import HubError
from storage.events import EventDraft
from storage.local_chat import now, uid
from runtime.native.activity import evidence, process_match


class NativeService:
    def __init__(self, repo, chat, link, *, plugins=None, probe=process_match):
        self.repo, self.chat, self.link = repo, chat, link
        self.db = repo.database
        self.probe = probe
        self.plugins = plugins if plugins is not None else [
            FileHistory("claude", Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))) / "projects", secrets_provider=self.secrets),
            FileHistory("codex", Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "sessions", secrets_provider=self.secrets)]
        self.lock = asyncio.Lock()
        self.pages = {}
        self.boot_id = uid("native-owner")
        self.db.native_service = self
        # A previous writer is not known stopped merely because this Hub restarted.
        with self.db.transaction() as tx:
            tx.connection.execute("UPDATE native_writers SET state='recovery'")

    def secrets(self):
        values = [self.link.hub_token]
        if self.link.vault.path.exists():
            values.append(self.link.vault.read())
        values.extend(v for k, v in os.environ.items() if v and any(p in k.upper() for p in ("TOKEN", "SECRET", "PASSWORD", "API_KEY")))
        return tuple(values)

    def row(self, identifier, *, conversation=False, session=False):
        field = "conversation_id" if conversation else "session_id" if session else "native_id"
        with self.db.locked_connection() as db:
            row = db.execute(f"SELECT * FROM native_sources WHERE {field}=?", (identifier,)).fetchone()
        if row is None:
            raise HubError("NOT_FOUND", "原生会话未登记")
        return dict(row)

    def plugin(self, row):
        source = json.loads(row["source_json"])
        match = next((p for p in self.plugins if p.runtime_id == row["runtime_id"] and p.root == Path(source["root"])), None)
        if match is None:
            raise HubError("NATIVE_SESSION_UNSUPPORTED", "读取插件或数据根已变化")
        return match

    def source(self, row, *, snapshot=None):
        stored = json.loads(row["source_json"])
        source = self.plugin(row).inspect(stored["path"], snapshot=snapshot)
        if source is None or source.vendor_id != stored["vendor_id"] or str(source.cwd) != stored["cwd"]:
            raise HubError("NATIVE_SESSION_CHANGED", "原生身份或目录已变化")
        return source

    async def scan(self):
        # Workspaces are authoritative; a provider scan failure is NOT deletion.
        workspaces = await self.chat.ports.workspaces.list_workspaces(None, None)
        with self.db.locked_connection() as db:
            excluded = {(r[0], r[1]) for r in db.execute("SELECT agent_instance_id,external_session_id FROM sessions WHERE external_session_id IS NOT NULL")}
            managed = {r[0] for r in db.execute("SELECT binding_key FROM native_sources WHERE conversation_id IS NOT NULL")}
        found = []
        for plugin in self.plugins:
            for source, workspace in await asyncio.to_thread(plugin.list, workspaces, excluded):
                root_identity = plugin.root.stat()
                key = digest([plugin.runtime_id, (root_identity.st_dev,root_identity.st_ino), plugin.agent_type, source.vendor_id])
                if key not in managed:
                    found.append((plugin, source, workspace, key))
        with self.db.transaction() as tx:
            registered = {w.id for w in workspaces}
            for row in tx.connection.execute("SELECT * FROM native_sources WHERE removed=0"):
                if row["workspace_id"] not in registered:
                    tx.connection.execute("UPDATE native_sources SET removed=1 WHERE native_id=?", (row["native_id"],))
                elif not row["conversation_id"]:
                    try:
                        Path(json.loads(row["source_json"])["path"]).stat()
                    except FileNotFoundError:
                        tx.connection.execute("UPDATE native_sources SET removed=2 WHERE native_id=?", (row["native_id"],))
                    except OSError:
                        pass  # A scan/permission failure is not a source deletion.
            for plugin, source, workspace, key in found:
                old = tx.connection.execute("SELECT * FROM native_sources WHERE binding_key=?", (key,)).fetchone()
                if old and old["conversation_id"]:
                    continue  # A concurrent import won while discovery ran.
                old_index = json.loads(old["index_json"]) if old else None
                identifier = old["native_id"] if old else uid("native")
                activity = evidence(source, self.probe)
                fmt = {"status": "readable" if source.readable else "unsupported", "cliVersion": public_text(source.version,self.secrets())[:80]}
                if source.readable:
                    fmt["readerId"] = source.reader_id
                else:
                    fmt["reason"] = source.reason
                title = next((m["text"] for m in source.messages if m["role"] == "user"), "原生会话")[:120]
                index = {"nativeSessionId": identifier, "workspaceId": workspace, "agentType": source.agent_type,
                    "title": title, "createdAt": source.created_at, "updatedAt": source.updated_at,
                    "indexVersion": old_index["indexVersion"] if old_index else 1, "sourceRevision": source.revision,
                    "format": fmt, "activity": activity}
                if old_index:
                    compared = lambda i: {**i, "activity": {k: v for k, v in i["activity"].items() if k != "observedAt"}}
                    if compared(index) != compared(old_index):
                        index["indexVersion"] += 1
                    else:
                        index = old_index
                NativeSessionIndex.model_validate(index)
                data = {"root": str(plugin.root), "path": str(source.path), "vendor_id": source.vendor_id,
                    "cwd": str(source.cwd), "identity": source.identity, "cut": source.cut, "prefix_hash": source.prefix_hash,
                    "timeBasis":{"createdAt":source.created_time_basis,"updatedAt":source.updated_time_basis}}
                tx.connection.execute("INSERT INTO native_sources(native_id,binding_key,workspace_id,runtime_id,agent_type,source_json,index_json) "
                    "VALUES(?,?,?,?,?,?,?) ON CONFLICT(binding_key) DO UPDATE SET workspace_id=excluded.workspace_id,source_json=excluded.source_json,index_json=excluded.index_json,removed=0",
                    (identifier, key, workspace, plugin.runtime_id, source.agent_type, json.dumps(data), json.dumps(index)))
        with self.db.locked_connection() as db:
            imported = [dict(r) for r in db.execute("SELECT c.* FROM local_conversations c JOIN native_sources n ON n.conversation_id=c.conversation_id WHERE n.removed=0")]
        for row in imported:
            view = LocalConversationView.model_validate_json(row["payload_json"])
            observed = await asyncio.to_thread(self.decorate, view)
            def facts(value):
                activity = value.native_activity.model_dump(mode="json",by_alias=True) if value.native_activity else {}
                return value.native_source_revision,{k:v for k,v in activity.items() if k!='observedAt'}
            if facts(observed) != facts(view):
                with self.db.transaction() as tx:
                    # Re-read metadata to avoid overwriting a simultaneous rename.
                    current = LocalConversationView.model_validate_json(tx.connection.execute("SELECT payload_json FROM local_conversations WHERE conversation_id=?",(view.id,)).fetchone()[0])
                    current = current.model_copy(update={"native_activity":observed.native_activity,"native_source_revision":observed.native_source_revision})
                    tx.connection.execute("UPDATE local_conversations SET payload_json=? WHERE conversation_id=?",(current.model_dump_json(by_alias=True,exclude_none=True),view.id))

    def _cursor(self, value):
        self.pages = {k: v for k, v in self.pages.items() if v["expires"] > time.monotonic()}
        if len(self.pages) >= 128:
            raise HubError("REMOTE_RATE_LIMITED", "原生读取快照过多")
        token = secrets.token_urlsafe(32)
        self.pages[token] = {**value, "expires": time.monotonic() + 900}
        return token

    def _page(self, token, kind):
        value = self.pages.get(token)
        if value is None or value["expires"] <= time.monotonic() or value["kind"] != kind:
            raise HubError("REMOTE_CURSOR_INVALID", "原生游标无效或过期")
        return value

    async def listing(self, workspace=None, agent=None, cursor=None, limit=50):
        if cursor:
            saved = self._page(cursor, "list")
            if saved["filter"] != [workspace, agent]:
                raise HubError("REMOTE_CURSOR_INVALID", "游标过滤条件不匹配")
            items, start = saved["items"], saved["offset"]
        else:
            await self.scan()
            with self.db.locked_connection() as db:
                items = [json.loads(r[0]) for r in db.execute("SELECT index_json FROM native_sources WHERE removed=0 AND conversation_id IS NULL")]
            items = sorted([i for i in items if (workspace is None or i["workspaceId"] == workspace) and
                (agent is None or i["agentType"] == agent)], key=lambda i: (i["updatedAt"], i["nativeSessionId"]), reverse=True)
            if not items and any(p.diagnostics for p in self.plugins if agent is None or p.agent_type == agent):
                raise HubError("NATIVE_SESSION_UNSUPPORTED", "原生读取能力不足：存在目录不可用、来源或格式无法确认的记录")
            start = 0
        selected = []
        for item in items[start:start + limit]:
            row = self.row(item["nativeSessionId"])
            if not row["removed"] and row["conversation_id"] is None:
                selected.append(item)
        result = {"items": selected, "hasMore": start + limit < len(items)}
        if result["hasMore"]:
            result["nextCursor"] = self._cursor({"kind": "list", "filter": [workspace, agent], "items": items, "offset": start + limit})
        return LocalNativeSessionPage.model_validate(result)

    async def registered(self, row):
        if row["removed"]:
            raise HubError("NOT_FOUND", "项目已移除")
        workspaces = await self.chat.ports.workspaces.list_workspaces(None, None)
        workspace = next((w for w in workspaces if w.id == row["workspace_id"]), None)
        cwd = Path(json.loads(row["source_json"])["cwd"])
        if workspace is None or not cwd.is_dir() or not cwd.resolve().is_relative_to(Path(workspace.path).resolve()):
            raise HubError("NOT_FOUND", "原生会话不属于已登记项目")
        return workspace

    async def detail(self, identifier):
        await self.scan()
        row = self.row(identifier)
        await self.registered(row)
        if row["conversation_id"]:
            raise HubError("NOT_FOUND", "会话已导入")
        return NativeSessionIndex.model_validate_json(row["index_json"])

    async def read(self, identifier, *, revision=None, before=None, limit=50, scope=None):
        row = self.row(identifier)
        await self.registered(row)
        if row["conversation_id"]:
            raise HubError("NOT_FOUND", "会话已导入")
        if before:
            page = self._page(before, "messages")
            if page["id"] != identifier or page.get("scope") != scope or (revision and revision != page["revision"]):
                raise HubError("NATIVE_SESSION_CHANGED", "读取快照版本不匹配")
            source = await asyncio.to_thread(self.source, row, snapshot=page["snapshot"])
            offset, current_revision = page["offset"], page["revision"]
        else:
            source = await asyncio.to_thread(self.source, row)
            if revision and source.revision != revision:
                raise HubError("NATIVE_SESSION_CHANGED", "原生记录已变化")
            offset, current_revision = 0, source.revision
        if not source.readable:
            raise HubError("NATIVE_SESSION_UNSUPPORTED", source.reason)
        parts = []
        for message in reversed(source.messages):
            text = message["text"]
            chunks = [text[i:i + 16000] for i in range(0, len(text), 16000)] or [""]
            for index, chunk in enumerate(chunks):
                parts.append({"messageId": message["id"], "role": message["role"], "text": chunk,
                    **({"createdAt": message["createdAt"]} if message.get("createdAt") else {}),
                    "segmentIndex": index, "segmentCount": len(chunks), "totalUtf8Bytes": len(text.encode()),
                    "contentSha256": hashlib.sha256(text.encode()).hexdigest()})
        snapshot = {"identity": source.identity, "cut": source.cut, "prefix_hash": source.prefix_hash}
        cursor_data = {"kind": "messages", "id": identifier, "snapshot": snapshot, "revision": current_revision,"scope":scope}
        selected, size = [], 0
        for part in parts[offset:offset + limit]:
            encoded = len(json.dumps(part, ensure_ascii=False).encode())
            if size + encoded > 1024 * 1024 - 8192:
                break
            size += encoded; selected.append(part)
        if not selected and offset < len(parts):
            raise HubError("REMOTE_QUERY_TOO_LARGE", "读取页超过大小限制")
        end = offset + len(selected)
        body = {"nativeSessionId": identifier, "sourceRevision": current_revision,
            "snapshotCursor": self._cursor({**cursor_data, "offset": offset}), "items": selected, "hasMore": end < len(parts)}
        if body["hasMore"]:
            body["before"] = self._cursor({**cursor_data, "offset": end})
        await self.registered(self.row(identifier))
        # Validate the original prefix once more before returning a body.
        await asyncio.to_thread(self.source, row, snapshot=snapshot)
        return NativeMessagePage.model_validate(body)

    def check(self, row, source, confirmation=None):
        repository = getattr(self.chat.ports.workspaces,"repository",None)
        if repository is not None:
            workspace = repository.get(row["workspace_id"])
            if not source.cwd.is_relative_to(Path(workspace.path).resolve()):
                raise HubError("NOT_FOUND", "原生会话的工作区归属已变化")
        if not source.readable:
            raise HubError("NATIVE_SESSION_UNSUPPORTED", source.reason)
        if row["conversation_id"]:
            with self.db.locked_connection() as db:
                latest = db.execute("SELECT r.task_id FROM local_runs r JOIN local_messages m ON m.message_id=r.message_id "
                    "WHERE r.conversation_id=? AND r.task_id IS NOT NULL ORDER BY m.sequence DESC LIMIT 1", (row["conversation_id"],)).fetchone()
            observer = getattr(type(self.chat.ports.tasks),"control_observation",None)
            if latest and observer is not None:
                observation = self.chat.ports.tasks.control_observation(latest[0])
                if observation.get("recoveryRequired") or observation.get("unresolvedCancellation") or observation.get("evidenceAvailable") is False:
                    raise HubError("SESSION_NOT_RESUMABLE", "原执行仍需本机核对，不能续接同一原生会话")
        activity = evidence(source, self.probe)
        owned = json.loads(row["source_json"]).get("owned_revision") if confirmation is None else None
        with self.db.locked_connection() as db:
            writer = db.execute("SELECT 1 FROM native_writers WHERE binding_key=?", (row["binding_key"],)).fetchone()
        if writer:
            raise HubError("NATIVE_SESSION_WRITER_CONFLICT", "该原生会话仍有工具内写者或待核对执行")
        if activity["processMatch"] == "present" or (activity["recentlyModified"] and owned != source.revision):
            raise HubError("NATIVE_SESSION_ACTIVE", "终端会话存在活跃证据")
        saved = confirmation or (json.loads(row["confirmation_json"]) if row["confirmation_json"] else None)
        if saved is None:
            raise HubError("NATIVE_SESSION_ACTIVE", "请明确确认终端已关闭")
        if saved["sourceRevision"] != source.revision and owned != source.revision:
            raise HubError("NATIVE_SESSION_CHANGED", "外部会话已修改，必须重新确认")
        return saved

    def confirm(self, source, request_id):
        return NativeClosureConfirmation(confirmationId=uid("confirmation"), confirmedAt=now(), requestId=request_id,
            sourceRevision=source.revision, terminalClosedConfirmed=True).model_dump(mode="json", by_alias=True)

    def audit(self, tx, row, confirmation, command_id=None, remote_scope=None):
        payload = {"nativeSessionId": row["native_id"], "confirmation": confirmation}
        if command_id:
            payload["commandId"] = command_id
            payload["_workerId"],payload["_storeId"] = remote_scope
        self.repo.events.append(tx, EventDraft(aggregate_type="system", aggregate_id="native-audit",
            type="native.closure.confirmed", payload=payload))

    async def import_session(self, identifier, value, key, request_id, *, confirmation=None, command_id=None, remote_scope=None, on_commit=None):
        async with self.lock:
            row = self.row(identifier)
            await self.registered(row)
            if row["conversation_id"]:
                result, _ = self.chat.repository.command("native.import:" + identifier, key,
                    value.model_dump(mode="json", by_alias=True), lambda tx:{"conversationId":row["conversation_id"]})
                return self.chat.repository.conversation(result["conversationId"])
            source = await asyncio.to_thread(self.source, row)
            if not row["conversation_id"]:
                index = json.loads(row["index_json"])
                if value.expected_index_version != index["indexVersion"] or value.source_revision != source.revision:
                    raise HubError("NATIVE_SESSION_CHANGED", "原生索引已变化，请刷新并确认")
            confirmation = confirmation or self.confirm(source, request_id)
            if not row["conversation_id"]:
                self.check(row, source, confirmation)
            def commit(tx):
                current = self.row(identifier)
                if current["conversation_id"]:
                    return {"conversationId": current["conversation_id"]}
                verified = self.plugin(row).adopt(source)
                self.check(row, verified, confirmation)
                conversation, session, stamp = uid("conversation"), uid("session"), now()
                view = LocalConversationView(id=conversation, workspaceId=row["workspace_id"],
                    title=json.loads(row["index_json"])["title"], createdAt=stamp, updatedAt=stamp,
                    authority="local", visibility="both", archived=False, version=1, conversationKind="native",
                    agentType=row["agent_type"], nativeSessionId=identifier, nativeSourceRevision=source.revision,
                    nativeActivity={**evidence(source, self.probe), "activity": "closed_confirmed", "terminalClosedConfirmedAt": confirmation["confirmedAt"]})
                tx.connection.execute("INSERT INTO local_conversations VALUES(?,?,?)", (conversation, view.model_dump_json(by_alias=True, exclude_none=True), stamp))
                for sequence, message in enumerate(verified.messages, 1):
                    tx.connection.execute("INSERT INTO local_messages VALUES(?,?,?,?,?,?,?)", (uid("message"), conversation,
                        sequence, "system" if message["role"] == "tool_summary" else message["role"], message["text"], None, message.get("createdAt", stamp)))
                tx.connection.execute("UPDATE native_sources SET conversation_id=?,session_id=?,confirmation_json=? WHERE native_id=?",
                    (conversation, session, json.dumps(confirmation), identifier))
                self.audit(tx, row, confirmation, command_id, remote_scope)
                if on_commit is not None:
                    on_commit(tx,{"conversationId":conversation,"workspaceId":row["workspace_id"],"nativeSessionId":identifier})
                self.repo.seal(tx)
                return {"conversationId": conversation}
            result, _ = self.chat.repository.command("native.import:" + identifier, key,
                value.model_dump(mode="json", by_alias=True), commit)
            return self.chat.repository.conversation(result["conversationId"])

    def authorize_send(self, tx, conversation, value):
        row = self.row(conversation, conversation=True)
        if value.session_mode != "continue":
            raise HubError("SESSION_NOT_RESUMABLE", "原生对话必须续接精确会话，不能新建上下文")
        source = self.source(row)
        supplied = value.native_confirmation
        confirmation = None
        if supplied:
            if supplied.source_revision != source.revision:
                raise HubError("NATIVE_SESSION_CHANGED", "显式确认的源版本已变化")
            confirmation = self.confirm(source, uid("request"))
        saved = self.check(row, source, confirmation)
        if confirmation:
            tx.connection.execute("UPDATE native_sources SET confirmation_json=? WHERE native_id=?", (json.dumps(saved), row["native_id"]))
            self.audit(tx, row, saved)

    def remote_confirmation(self, tx, conversation, proof, command_id):
        proof = NativeClosureConfirmation.model_validate(proof).model_dump(mode="json",by_alias=True)
        row = self.row(conversation,conversation=True)
        self.check(row,self.source(row),proof)
        tx.connection.execute("UPDATE native_sources SET confirmation_json=? WHERE native_id=?",(json.dumps(proof),row["native_id"]))
        self.audit(tx,row,proof,command_id,(self.repo.get("link",tx)["view"]["workerId"],self.repo.get("identity",tx)["store"]))

    async def task_input(self, record):
        row = self.row(record["conversation_id"], conversation=True)
        workspace = await self.registered(row)
        source = await asyncio.to_thread(self.source, row)
        self.check(row, source)
        candidates = await self.chat.ports.tasks.directory.list_candidates()
        candidate = next((a for a in candidates if a.instance_id == row["runtime_id"]),None)
        if candidate is None or "session_resume" not in candidate.capabilities:
            raise HubError("SESSION_NOT_RESUMABLE", "当前Runtime没有声明精确会话续接能力")
        sessions = self.chat.ports.tasks.runtime.sessions.repository
        session = await sessions.get(row["session_id"])
        if session is not None and (str(session.status) != "idle" or not session.is_valid):
            raise HubError("SESSION_NOT_RESUMABLE", "原生会话当前不可安全续接")
        profile_id = "native-profile:" + row["native_id"]
        await self.chat.ports.team_profiles.save_profile(profile_id, SaveTeamProfileInput.model_validate({
            "id": profile_id, "name": "原生单Agent", "scope": "global", "isDefault": False,
            "roleBindings": {"analyst": {"roleId": "analyst", "roleName": "原生Agent", "primaryAgentId": row["runtime_id"], "fallbackAgentIds": []}}}))
        return CreateTaskInput(objective=self.chat.repository.run_text(record["run_id"]), workspaceId=row["workspace_id"],
            profileId=profile_id, source="desktop", workflowRoles=["analyst"], roleOverrides={"analyst": row["runtime_id"]},
            resumeSessions={"analyst": row["session_id"]})

    async def prepare_session(self, session_id, task_id, node_id, objective):
        try:
            row = self.row(session_id, session=True)
        except HubError as error:
            if error.code == "NOT_FOUND":
                return
            raise
        workspace = await self.registered(row)
        source = await asyncio.to_thread(self.source, row)
        self.check(row, source)
        sessions = self.chat.ports.tasks.runtime.sessions.repository
        session = await sessions.get(session_id)
        # Internal single-Agent read-only execution policy; never a fabricated
        # LocalScene or role snapshot. Native source cwd remains the resume cwd.
        if session is None:
            stamp = now()
            session = SessionView(id=row["session_id"], status="idle", workspaceId=row["workspace_id"],
                workspaceName=workspace.name, roleId="analyst", agentInstanceId=row["runtime_id"],
                agentDisplayName=row["agent_type"], adapterId=row["agent_type"], externalSessionId=source.vendor_id,
                purpose="adhoc", reusePolicy="resume_explicit", taskId=task_id, nodeId=node_id, createdAt=stamp, lastUsedAt=stamp,
                isValid=True, turnCount=0)
            spec = AgentTaskSpec(sessionId=session.id, taskId=task_id, nodeId=node_id,
                workspaceId=row["workspace_id"], roleId="analyst", objective=objective, worktreePath=str(source.cwd),
                allowedPaths=[], sessionPurpose="adhoc", reusePolicy="resume_explicit", readOnly=True)
            await sessions.save_spec(session.id, spec)
            await sessions.save(session)

    async def acquire_session(self, session_id, message):
        try:
            row = self.row(session_id, session=True)
        except HubError as error:
            if error.code == "NOT_FOUND":
                return False
            raise
        await self.registered(row)
        source = await asyncio.to_thread(self.source, row)
        with self.db.transaction() as tx:
            self.check(row, source)
            tx.connection.execute("INSERT INTO native_writers VALUES(?,?,?,?,?,?,?)", (
                row["binding_key"], session_id, self.boot_id, "active", source.revision, now(), digest(public_text(message,self.secrets()))))
            self.repo.seal(tx)
        return True

    def release_session(self, session_id, *, safe):
        with self.db.locked_connection() as db:
            if db.execute("SELECT 1 FROM native_writers WHERE session_id=?", (session_id,)).fetchone() is None:
                return
        with self.db.transaction() as tx:
            if safe:
                writer = tx.connection.execute("SELECT * FROM native_writers WHERE session_id=? AND owner=? AND state='active'", (session_id,self.boot_id)).fetchone()
                if writer:
                    # Attribute only an unchanged prefix plus this exact turn's
                    # single user input. Foreign user input, format changes,
                    # replacement or a matching live terminal require reconfirm.
                    try:
                        row = self.row(session_id,session=True)
                        old = json.loads(row["source_json"])
                        prefix = self.source(row,snapshot=old)
                        current = self.source(row)
                        users = [m['text'] for m in current.messages[len(prefix.messages):] if m['role']=='user']
                        if (current.readable and prefix.readable and len(users)==1 and digest(users[0])==writer['input_hash']
                                and self.probe(current.vendor_id) != 'present'):
                            old.update(identity=current.identity,cut=current.cut,prefix_hash=current.prefix_hash,owned_revision=current.revision)
                            tx.connection.execute("UPDATE native_sources SET source_json=? WHERE native_id=?",(json.dumps(old),row['native_id']))
                    except HubError:
                        pass
                tx.connection.execute("DELETE FROM native_writers WHERE session_id=? AND owner=? AND state='active'", (session_id, self.boot_id))
            else:
                tx.connection.execute("UPDATE native_writers SET state='recovery' WHERE session_id=?", (session_id,))
            self.repo.seal(tx)

    def decorate(self, view):
        if str(view.conversation_kind) != "native":
            return view
        row = self.row(view.id, conversation=True)
        try:
            source = self.source(row)
        except HubError:
            from protocol.generated.python import NativeActivityEvidence
            return view.model_copy(update={"native_activity":NativeActivityEvidence(
                activity="unknown",observedAt=now(),processMatch="unknown",recentlyModified=False)})
        observed = evidence(source, self.probe)
        confirmation = json.loads(row["confirmation_json"]) if row["confirmation_json"] else None
        with self.db.locked_connection() as db:
            writer = db.execute("SELECT 1 FROM native_writers WHERE binding_key=?", (row["binding_key"],)).fetchone()
        if not writer and confirmation and source.revision in {confirmation["sourceRevision"],json.loads(row["source_json"]).get("owned_revision")} and observed["activity"] == "unknown":
            observed.update(activity="closed_confirmed", terminalClosedConfirmedAt=confirmation["confirmedAt"])
        from protocol.generated.python import NativeActivityEvidence
        return view.model_copy(update={"native_source_revision": source.revision,
            "native_activity": NativeActivityEvidence.model_validate(observed)})
