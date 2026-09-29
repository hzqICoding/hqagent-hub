"""Versioned, bounded built-in history readers. No Worker wire/filesystem policy here."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.errors import HubError
from runtime.remote.security import safe_text

MAX_SOURCE_BYTES = 64 * 1024 * 1024
FILTER_VERSION = "public-text-v1"
CANCEL_READ = ContextVar("native_read_cancel", default=None)


def check_cancelled():
    cancellation = CANCEL_READ.get()
    if cancellation is not None and cancellation.is_set():
        raise HubError("REMOTE_QUERY_TIMEOUT", "原生读取已取消")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace("+00:00", "Z")


def source_time(value, fallback=None):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (AttributeError, ValueError, TypeError):
        return stamp(fallback) if fallback is not None else None


def public_text(text, secrets=()):
    # Drop an unfinished private block too. Filtering precedes all segmentation.
    text = re.sub(r"(?is)<(?:analysis|think|thinking)>.*?(?:</(?:analysis|think|thinking)>|\Z)", "[redacted]", text)
    text = re.sub(r"(?is)-----BEGIN [^-]*PRIVATE KEY-----.*?(?:-----END [^-]*PRIVATE KEY-----|\Z)", "[redacted]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[redacted]", text)
    return safe_text(text, secrets)


@dataclass
class HistorySource:
    path: Path
    identity: tuple
    cut: int
    prefix_hash: str
    vendor_id: str
    cwd: Path
    version: str
    reader_id: str
    agent_type: str
    created_at: str
    updated_at: str
    modified: float
    readable: bool
    messages: list
    reason: str = ""
    created_time_basis: str = "metadata"
    updated_time_basis: str = "file_stat"

    @property
    def revision(self):
        return digest([self.identity, self.cut, self.prefix_hash, self.version, self.reader_id, FILTER_VERSION])


class FileHistory:
    """Official history capability is absent in the current Adapter port.

    This explicit fallback only accepts tested versions and terminal provenance:
    Codex session_meta.source=cli; Claude an interactive history.jsonl entry
    matching both exact sessionId and canonical project. Sidechains never qualify.
    """
    versions = {"codex": {"0.153.4"}, "claude": {"2.1.261", "2.1.272", "2.1.283"}}

    def __init__(self, agent_type, data_root, *, runtime_id=None, secrets_provider=lambda: ()):
        self.agent_type = agent_type
        self.root = Path(data_root).expanduser().resolve()
        self.runtime_id = runtime_id or "local." + agent_type + ".default"
        self.secrets_provider = secrets_provider
        self.diagnostics = []

    def capabilities(self):
        return {"history.list": self.root.is_dir(), "history.read": self.root.is_dir(),
                "history.adopt": self.root.is_dir(), "provider": "versioned-file-fallback",
                "versions": sorted(self.versions[self.agent_type]),
                "reason": "" if self.root.is_dir() else "Runtime历史目录不可用"}

    def _bytes(self, path, snapshot=None):
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(self.root)
            with resolved.open("rb") as stream:
                st = os.fstat(stream.fileno())
                identity = (st.st_dev, st.st_ino)
                if snapshot and tuple(snapshot["identity"]) != identity:
                    raise HubError("NATIVE_SESSION_CHANGED", "原生记录文件身份已变化")
                size = snapshot["cut"] if snapshot else st.st_size
                if size > MAX_SOURCE_BYTES:
                    raise HubError("REMOTE_SYNC_RESOURCE_LIMIT", "原生记录超过当前读取配额")
                chunks = []
                remaining = size
                while remaining:
                    check_cancelled()
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                content = b"".join(chunks)
                after = os.fstat(stream.fileno())
                if (after.st_dev, after.st_ino) != identity or len(content) != size:
                    raise HubError("NATIVE_SESSION_CHANGED", "原生记录读取期间发生变化")
                if snapshot:
                    if hashlib.sha256(content).hexdigest() != snapshot["prefix_hash"]:
                        raise HubError("NATIVE_SESSION_CHANGED", "原生历史快照前缀已变化")
                else:
                    # Only complete records are eligible, never parse half JSON.
                    content = content[:content.rfind(b"\n") + 1]
                return content, identity, st
        except (OSError, ValueError):
            raise HubError("NATIVE_SESSION_CHANGED", "原生记录不可安全读取") from None

    def _terminal_history(self):
        if self.agent_type != "claude":
            return set()
        result = set()
        history = self.root.parent / "history.jsonl"
        try:
            with history.open("rb") as stream:
                if os.fstat(stream.fileno()).st_size > MAX_SOURCE_BYTES:
                    return result
                for line in stream:
                    try:
                        row = json.loads(line)
                        if not isinstance(row,dict):
                            continue
                        # Interactive command history is additional provenance,
                        # not the transcript filename or mere userType=external.
                        if isinstance(row.get("display"), str) and isinstance(row.get("timestamp"), (int, float)):
                            result.add((row["sessionId"], str(Path(row["project"]).resolve())))
                    except (ValueError, KeyError, TypeError):
                        continue
        except OSError:
            pass
        return result

    def inspect(self, path, *, snapshot=None, terminals=None):
        content, identity, st = self._bytes(Path(path), snapshot)
        try:
            records, damaged = [], False
            for line in content.splitlines():
                if not line.strip():
                    continue
                try:
                    records.append(json.loads(line))
                except ValueError:
                    damaged = True
                    break
            if not records or not all(isinstance(r, dict) for r in records):
                raise ValueError()
            if self.agent_type == "codex":
                first = records[0]
                if first.get("type") != "session_meta":
                    self.diagnostics.append("原生记录缺少可验证的会话信封")
                    return None
                meta = first["payload"]
                if not isinstance(meta,dict):
                    raise ValueError()
                if meta.get("source") != "cli":
                    return None
                if not Path(meta["cwd"]).is_absolute():
                    return None
                vendor, cwd, version = meta["id"], Path(meta["cwd"]).resolve(), meta.get("cli_version","unknown")
                created_raw = meta.get("timestamp")
                created = source_time(created_raw, st.st_ctime)
            else:
                envelope = next((r for r in records if all(k in r for k in ("sessionId", "cwd"))), None)
                if envelope is None:
                    self.diagnostics.append("原生记录缺少可验证的会话信封")
                    return None
                if any(r.get("isSidechain") for r in records):
                    return None
                if any(r.get("source") not in {None,"cli","terminal"} or r.get("userType") not in {None,"external"} for r in records):
                    return None
                if not Path(envelope["cwd"]).is_absolute():
                    return None
                vendor, cwd, version = envelope["sessionId"], Path(envelope["cwd"]).resolve(), envelope.get("version","unknown")
                if (vendor, str(cwd)) not in (terminals if terminals is not None else self._terminal_history()):
                    self.diagnostics.append("原生来源无法证明为终端；未收录")
                    return None
                created_raw = envelope.get("timestamp")
                created = source_time(created_raw, st.st_ctime)
            if not isinstance(vendor, str) or not cwd.is_absolute():
                return None
            try:
                if str(uuid.UUID(vendor)) != vendor.lower():
                    return None
            except ValueError:
                return None
            if not isinstance(version,str) or not version.isascii():
                version = "unknown"
            profile = self.agent_type + ".jsonl." + str(version)
            source = HistorySource(Path(path), identity, len(content), hashlib.sha256(content).hexdigest(),
                vendor, cwd, str(version), profile, self.agent_type, created, stamp(st.st_mtime), st.st_mtime,
                version in self.versions[self.agent_type] and not damaged, [])
            source.created_time_basis = "metadata" if source_time(created_raw) else "file_stat"
            if not source.readable:
                source.reason = "没有经过验证的CLI版本读取器"
                return source
            try:
                source.messages = self._messages(records, source)
            except (ValueError, KeyError, TypeError):
                source.readable, source.reason = False, "记录结构不符合已验证的读取器，不能推测正文"
            return source
        except (ValueError, KeyError, TypeError):
            raise HubError("NATIVE_SESSION_UNSUPPORTED", "原生记录格式无法识别") from None

    def _messages(self, records, source):
        result, chain, seen = [], None, set()
        calls = {}
        private = {"thinking", "reasoning", "redacted_thinking", "encrypted_content"}
        tool_names = {"Read", "Write", "Edit", "Bash", "Glob", "Grep", "shell", "exec_command", "apply_patch"}
        for index, row in enumerate(records):
            check_cancelled()
            if self.agent_type == "codex":
                if row.get("type") in {"session_meta", "event_msg", "turn_context", "compacted"}:
                    continue
                if row.get("type") != "response_item":
                    raise ValueError()
                message = row["payload"]
                if not isinstance(message,dict):
                    raise ValueError()
                if message.get("type") in {"function_call","custom_tool_call"}:
                    name = message.get("name")
                    if name in tool_names:
                        calls[message.get("call_id")] = name
                        result.append({"id":digest([source.vendor_id,index,"tool"]),"role":"tool_summary","text":"工具 " + name + "：历史调用"})
                    continue
                if message.get("type") in {"function_call_output","custom_tool_call_output"}:
                    name = calls.get(message.get("call_id"))
                    if name:
                        result.append({"id":digest([source.vendor_id,index,"tool"]),"role":"tool_summary","text":"工具 " + name + "：历史返回记录"})
                    continue
                if message.get("type") in private | {"function_call", "function_call_output", "custom_tool_call", "custom_tool_call_output", "web_search_call"}:
                    continue
                if message.get("type") != "message":
                    raise ValueError()
                mid = message.get("id") or digest([index, row])
            else:
                if row.get("type") not in {"user", "assistant"}:
                    if row.get("type") in {"progress", "system", "summary", "file-history-snapshot", "queue-operation", "last-prompt"}:
                        continue
                    raise ValueError()
                if row.get("isMeta"):
                    continue
                if row.get("sessionId") != source.vendor_id or Path(row["cwd"]).resolve() != source.cwd or row.get("version") != source.version:
                    raise ValueError()
                mid, parent = row["uuid"], row.get("parentUuid")
                if mid in seen:
                    raise ValueError()
                if chain is not None and parent != chain:
                    raise ValueError()  # Branch reconstruction unsupported, never mix paths.
                chain = mid
                seen.add(mid)
                message = row["message"]
                if not isinstance(message,dict):
                    raise ValueError()
            role = message.get("role")
            if role in {"system", "developer"}:
                continue
            if message.get("channel") in {"analysis", "reasoning"}:
                continue
            if message.get("channel") not in {None, "final", "commentary"}:
                raise ValueError()
            if role not in {"user", "assistant"}:
                raise ValueError()
            content = message["content"]
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
            if not isinstance(blocks,list) or not all(isinstance(block,dict) for block in blocks):
                raise ValueError()
            texts, tools = [], []
            for block in blocks:
                kind = block.get("type")
                if kind in private or kind in {"image", "image_url", "input_image", "document"}:
                    continue
                if kind in {"text", "input_text", "output_text"}:
                    texts.append(block["text"])
                elif kind in {"tool_use", "tool_result"}:
                    if block.get("name") in tool_names:
                        tools.append("工具 " + block["name"] + "：历史记录")
                else:
                    raise ValueError()
            for message_role, text in ((role, "".join(texts)), ("tool_summary", "\n".join(tools))):
                if text:
                    if message_role == "user" and text.lstrip().startswith((
                            "<environment_context>", "<permissions instructions>", "# AGENTS.md instructions")):
                        continue  # Runtime-injected instruction/context envelopes.
                    text.encode("utf-8")  # Invalid Unicode is unsupported, never a truncated reply.
                    value = {"id": digest([source.vendor_id, mid, message_role]), "role": message_role,
                        "text": public_text(text, self.secrets_provider())}
                    if source_time(row.get("timestamp")):
                        value["createdAt"] = source_time(row["timestamp"])
                    result.append(value)
        return result

    def list(self, workspaces, excluded=()):
        self.diagnostics = []
        if not self.root.is_dir():
            self.diagnostics.append("Runtime历史目录不可用")
            return []
        terminals = self._terminal_history()
        values = []
        paths = self.root.rglob("*.jsonl")
        for count, path in enumerate(paths):
            if count >= 10000:
                raise HubError("REMOTE_SYNC_RESOURCE_LIMIT", "原生索引超过扫描限额")
            try:
                source = self.inspect(path, terminals=terminals)
            except HubError:
                self.diagnostics.append("原生记录不可读取；未推测来源或正文")
                continue
            if source is None or (self.runtime_id, source.vendor_id) in excluded:
                continue
            matches = [w for w in workspaces if source.cwd.is_relative_to(Path(w.path).resolve()) and Path(w.path).is_dir()]
            if matches:
                workspace = max(matches, key=lambda w: len(Path(w.path).resolve().parts))
                # Discovery retains metadata + already-filtered title only.
                # Never accumulate every transcript's full body in an index scan.
                first_user = next((m for m in source.messages if m["role"] == "user"),None)
                source.messages = [{**first_user,"text":first_user["text"][:120]}] if first_user else []
                values.append((source, workspace.id))
        return values

    def read(self, source):
        result = self.inspect(source.path, snapshot={"identity": source.identity, "cut": source.cut, "prefix_hash": source.prefix_hash})
        if result is None or not result.readable:
            raise HubError("NATIVE_SESSION_UNSUPPORTED", "原生格式不支持读取")
        return result

    def adopt(self, source):
        current = self.inspect(source.path)
        if current is None or current.revision != source.revision:
            raise HubError("NATIVE_SESSION_CHANGED", "原生会话已变化，请重新确认")
        if not current.readable:
            raise HubError("NATIVE_SESSION_UNSUPPORTED", "原生格式不支持导入")
        return current
