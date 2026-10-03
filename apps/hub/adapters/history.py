"""Versioned, bounded built-in history readers. No Worker wire/filesystem policy here."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.errors import HubError
from runtime.remote.security import safe_text

MAX_SOURCE_BYTES = 64 * 1024 * 1024
FILTER_VERSION = "public-text-v1"
CANCEL_READ = ContextVar("native_read_cancel", default=None)
CLAUDE_AUXILIARY = frozenset({'progress', 'summary', 'attachment', 'mode', 'permission-mode',
    'bridge-session', 'atis-latch', 'ai-title', 'last-prompt', 'file-history-snapshot',
    'file-history-delta', 'queue-operation', 'cost-state', 'system'})


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
    title: str | None = None
    structure_counts: dict = field(default_factory=dict)

    @property
    def revision(self):
        return digest([self.identity, self.cut, self.prefix_hash, self.version, self.reader_id, FILTER_VERSION])


class HistoryStructureError(ValueError):
    """Only fixed field names/record offsets; never source contents."""


class FileHistory:
    """Official history capability is absent in the current Adapter port.

    This fallback requires a bounded version profile AND record validation:
    Codex session_meta.source=cli; Claude an interactive history.jsonl entry
    matching both exact sessionId and canonical project. Sidechains never qualify.
    """
    # Local metadata-only census: .hqagent/reviews/native-versions-census.json.
    # Optional metadata differs; the consumed identity/message fields do not.
    # Non-terminal sources and inconsistent identities remain excluded.
    verified_series = {"codex": (0, 98, 0), "claude": (2, 1, 251)}
    surveyed_maximum = {"codex": (0, 159, 2), "claude": (2, 1, 288)}
    structure_version = 'structures-v3'
    version_policy = "census-range-and-same-major-future-record-structure-v1"
    compatible_reason = "结构兼容、版本未逐一验证"

    def __init__(self, agent_type, data_root, *, runtime_id=None, secrets_provider=lambda: ()):
        self.agent_type = agent_type
        self.root = Path(data_root).expanduser().resolve()
        self.runtime_id = runtime_id or "local." + agent_type + ".default"
        self.secrets_provider = secrets_provider
        self.diagnostics = []
        self.observed_versions = set()
        self.version_diagnostics = []
        self.structure_counts = {}

    def capabilities(self):
        return {"history.list": self.root.is_dir(), "history.read": self.root.is_dir(),
                "history.adopt": self.root.is_dir(), "provider": "versioned-file-fallback",
                "verifiedSeries": self.series_description(), "observedVersions": sorted(self.observed_versions),
                "versionPolicy": self.version_policy,
                "versionDiagnostics": list(self.version_diagnostics),
                "structureCounts": dict(self.structure_counts),
                "reason": "" if self.root.is_dir() else "Runtime历史目录不可用"}

    def series_description(self):
        lower = self.verified_series[self.agent_type]
        upper = self.surveyed_maximum[self.agent_type]
        return {"series": '.'.join(map(str, lower)) + '–' + '.'.join(map(str, upper)), "minimumPatch": lower[2]}

    def paths(self):
        return self.root.rglob('*.jsonl')

    @staticmethod
    def version_tuple(version):
        if not isinstance(version, str) or len(version) > 32:
            return None
        match = re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version)
        return tuple(map(int, match.groups())) if match else None

    def verified_version(self, version):
        value = self.version_tuple(version)
        return value is not None and self.verified_series[self.agent_type] <= value <= self.surveyed_maximum[self.agent_type]

    def version_rejection(self, version):
        value = self.version_tuple(version)
        if value is None:
            return 'CLI版本不是有效的major.minor.patch'
        minimum = self.verified_series[self.agent_type]
        if value[0] != minimum[0]:
            return 'CLI主版本不在当前读取器支持范围'
        if value < minimum:
            return 'CLI版本低于结构普查支持下限' + '.'.join(map(str, minimum))
        # Future patches/minors may qualify only after the complete record
        # validators pass. A header is an internal candidate, never that proof.
        return ''

    def record_diagnostic(self, source):
        reported = source.version if self.version_tuple(source.version) else 'unknown'
        if len(self.observed_versions) < 32:
            self.observed_versions.add(reported)
        diagnostic = (f"实际版本={reported}; 已验证系列={self.series_description()}; 判定方式={self.version_policy}; "
                      + (source.reason or ('结构校验通过' if source.readable else '结构校验失败')))
        if diagnostic not in self.version_diagnostics:
            self.version_diagnostics = (self.version_diagnostics + [diagnostic])[-32:]
        if not source.readable and source.reason not in self.diagnostics:
            self.diagnostics.append(source.reason)

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

    def inspect(self, path, *, snapshot=None, terminals=None, _data=None, metadata_only=False, validate_chain=True, header_only=False):
        self.structure_counts = {}
        content, identity, st = _data if _data is not None else self._bytes(Path(path), snapshot)
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
                if any(r.get('isSidechain') for r in records) and not any(
                        not r.get('isSidechain') and r.get('type') in {'user', 'assistant'} for r in records):
                    return None  # Auxiliary-only remainder of an excluded sidechain.
                envelope = next((r for r in records if not r.get('isSidechain') and
                    r.get('type') in {'user','assistant','system'} and all(k in r for k in ("sessionId", "cwd", "version"))), None)
                if envelope is None:
                    self.diagnostics.append("原生记录缺少可验证的会话信封")
                    return None
                if any(r.get("source") not in {None,"cli","terminal"} or r.get("userType") not in {None,"external"}
                       for r in records if not r.get('isSidechain') and r.get('type') in {'user','assistant'}):
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
            profile = self.agent_type + ".jsonl." + str(version) + '.' + self.structure_version
            source = HistorySource(Path(path), identity, len(content), hashlib.sha256(content).hexdigest(),
                vendor, cwd, str(version), profile, self.agent_type, created, stamp(st.st_mtime), st.st_mtime,
                not self.version_rejection(version) and not damaged, [])
            source.created_time_basis = "metadata" if source_time(created_raw) else "file_stat"
            # Only numeric versions enter diagnostics; arbitrary source text is
            # never reflected as a purported version or diagnostic detail.
            reported = version if re.fullmatch(r"[0-9.]{1,32}", version) else "unknown"
            if len(self.observed_versions) < 32:
                self.observed_versions.add(reported)
            if not source.readable:
                source.reason = self.version_rejection(version) or "JSONL含损坏或未识别的完整记录"
                self.record_diagnostic(source)
                return source
            if not self.verified_version(version):
                source.reason = self.compatible_reason
            if header_only:
                return source
            try:
                self._validate_identity(records, source)
                source.messages = self._messages(records, source, metadata_only=metadata_only, validate_chain=validate_chain)
            except HistoryStructureError as error:
                source.readable, source.reason = False, str(error)
            except (ValueError, KeyError, TypeError):
                source.readable, source.reason = False, "消息块、角色或记录链结构不符合已验证读取器"
            self.record_diagnostic(source)
            self.structure_counts = dict(source.structure_counts)
            return source
        except (ValueError, KeyError, TypeError):
            raise HubError("NATIVE_SESSION_UNSUPPORTED", "原生记录格式无法识别") from None

    def _validate_identity(self, records, source, *, record_offset=0):
        for index, row in enumerate(records, record_offset):
            check_cancelled()
            if row.get('isSidechain'):
                continue
            if self.agent_type == "claude":
                if row.get('type') not in CLAUDE_AUXILIARY | {'user', 'assistant'}:
                    continue
                required = {"sessionId", "cwd", "version"} if row.get("type") in {"user", "assistant"} else set()
                fields = {"sessionId": source.vendor_id, "session_id": source.vendor_id, "cwd": source.cwd, "version": source.version}
                values = row
            else:
                if row.get("type") in {"session_meta", "event_msg", "turn_context", "compacted"} and not isinstance(row.get("payload"), dict):
                    raise HistoryStructureError(f"第{index + 1}条记录的payload必须为对象")
                if row.get("type") == "session_meta":
                    required = {"id", "cwd", "cli_version", "source"}
                    fields = {"id": source.vendor_id, "cwd": source.cwd, "cli_version": source.version, "source": "cli"}
                elif row.get("type") == "turn_context":
                    required = set()
                    fields = {"cwd": source.cwd, "cli_version": source.version, "session_id": source.vendor_id}
                else:
                    continue
                values = row["payload"]
            for key, expected in fields.items():
                if key not in values and key not in required:
                    continue
                actual = values.get(key)
                if key == "cwd":
                    # The initial envelope owns the canonical workspace and
                    # import binding. Later working directories are context,
                    # not a request to rebind this native identity.
                    if not isinstance(actual, str) or not Path(actual).is_absolute():
                        raise HistoryStructureError(f"第{index + 1}条记录的cwd缺失或不是绝对目录")
                    continue
                if key in {"version", "cli_version"}:
                    rejection = self.version_rejection(actual)
                    if rejection:
                        raise HistoryStructureError(f"第{index + 1}条记录的{key}：{rejection}")
                    if not self.verified_version(actual):
                        source.reason = self.compatible_reason
                    if len(self.observed_versions) < 32:
                        self.observed_versions.add(actual)
                    continue
                if actual != expected:
                    raise HistoryStructureError(f"第{index + 1}条记录的{key}缺失或与会话信封不一致")

    @staticmethod
    def _compact_boundary(row):
        return row.get('isCompactSummary') is True or (
            row.get('type') == 'system' and row.get('subtype') == 'compact_boundary'
            and isinstance(row.get('compactMetadata'), dict))

    def _validate_chain(self, records, *, seen=None, record_offset=0, hash_ids=False):
        # All main-stream record IDs participate, including hidden/meta records.
        # Multiple assistant blocks may share an earlier parent; adjacency is
        # not the chain invariant. Only explicit compact boundaries may refer
        # to a discarded prefix.
        seen = set() if seen is None else seen
        for index, row in enumerate(records, record_offset):
            check_cancelled()
            if row.get('isSidechain'):
                continue
            mid, parent = row.get('uuid'), row.get('parentUuid')
            key = digest(mid) if hash_ids and isinstance(mid, str) else mid
            parent_key = digest(parent) if hash_ids and isinstance(parent, str) else parent
            if row.get('type') not in CLAUDE_AUXILIARY | {'user', 'assistant'}:
                if isinstance(mid, str) and mid:
                    seen.add(key)
                continue
            message = row.get('type') in {'user', 'assistant'} or (row.get('type') == 'system' and 'message' in row)
            if message and (not isinstance(mid, str) or not mid):
                raise HistoryStructureError(f'第{index + 1}条消息缺少有效uuid')
            if mid is not None:
                if not isinstance(mid, str) or not mid or key in seen:
                    raise HistoryStructureError(f'第{index + 1}条记录uuid无效或重复')
                if parent is not None and (not isinstance(parent, str) or not parent):
                    raise HistoryStructureError(f'第{index + 1}条记录parentUuid无效')
                if parent is not None and parent_key not in seen and not self._compact_boundary(row):
                    raise HistoryStructureError(f'第{index + 1}条记录的parentUuid没有先行记录')
                seen.add(key)

    def _messages(self, records, source, *, metadata_only=False, validate_chain=True,
                  state=None, record_offset=0, hidden_secrets=None):
        state = {} if state is None else state
        result, calls = [], state.setdefault('calls', {})
        counts = source.structure_counts = state.setdefault('counts', dict(ignoredRecords=0, unknownRecords=0,
            unknownItems=0, unknownEvents=0, unknownBlocks=0, sidechainRecords=0, internalMessages=0))
        # DPAPI and environment lookup once per operation, never once per message.
        hidden_secrets = self.secrets_provider() if hidden_secrets is None else hidden_secrets
        private = {'thinking', 'reasoning', 'redacted_thinking', 'encrypted_content'}
        tool_names = {'Read', 'Write', 'Edit', 'Bash', 'Glob', 'Grep', 'shell', 'exec_command', 'apply_patch'}
        if self.agent_type == 'claude' and validate_chain:
            self._validate_chain(records, seen=state.setdefault('seen', set()), record_offset=record_offset, hash_ids=state.get('hash_ids',False))
        call_key = (lambda value: digest(value)) if state.get('hash_ids') else (lambda value:value)

        def emit(mid, role, text, row):
            if not text:
                return
            if role == 'user' and text.lstrip().startswith((
                    '<environment_context>', '<permissions instructions>', '# AGENTS.md instructions')):
                return
            if role == 'user' and state.get('first_title') is None:
                state['first_title'] = public_text(text, hidden_secrets)[:120]
                state['first_title_record'] = index
            text.encode('utf-8')
            if metadata_only:
                result.append({'id': digest([source.vendor_id, mid, role]), 'role': role, 'recordIndex': index})
                return
            value = {'id': digest([source.vendor_id, mid, role]), 'role': role,
                'text': public_text(text, hidden_secrets)}
            if source_time(row.get('timestamp')):
                value['createdAt'] = source_time(row['timestamp'])
            result.append(value)

        def tool_name(value):
            return value if isinstance(value, str) and value in tool_names else '工具'

        for index, row in enumerate(records, record_offset):
            check_cancelled()
            if row.get('isSidechain'):
                counts['sidechainRecords'] += 1
                continue
            if self.agent_type == 'codex':
                if row.get('type') in {'session_meta', 'event_msg', 'turn_context', 'compacted'}:
                    counts['ignoredRecords'] += 1
                    if row.get('type') == 'event_msg' and row['payload'].get('type') not in {
                            'task_started','task_complete','item_completed','token_count','thread_settings_applied',
                            'user_message','agent_message','turn_aborted'}:
                        counts['unknownEvents'] += 1
                    if row.get('type') == 'compacted':
                        emit(digest([index, 'compact']), 'tool_summary', '对话已压缩', row)
                    continue
                if row.get('type') != 'response_item':
                    counts['unknownRecords'] += 1
                    continue
                message = row.get('payload')
                if not isinstance(message, dict):
                    raise HistoryStructureError(f'第{index + 1}条记录payload不是对象')
                kind = message.get('type')
                if kind in {'function_call', 'custom_tool_call'}:
                    name = tool_name(message.get('name'))
                    call = message.get('call_id')
                    if isinstance(call, str):
                        calls[call_key(call)] = name
                    emit(digest([index, 'tool']), 'tool_summary', name + '：历史调用', row)
                    continue
                if kind in {'function_call_output', 'custom_tool_call_output'}:
                    call = message.get('call_id')
                    name = calls.get(call_key(call), '工具') if isinstance(call, str) else '工具'
                    emit(digest([index, 'tool']), 'tool_summary', name + '：历史返回记录', row)
                    continue
                if kind in private:
                    continue
                if kind == 'web_search_call':
                    emit(digest([index, 'tool']), 'tool_summary', '工具：历史搜索调用', row)
                    continue
                if kind != 'message':
                    counts['unknownItems'] += 1
                    continue
                mid = message.get('id') or digest([index, row])
            else:
                is_message = row.get('type') in {'user', 'assistant'} or (row.get('type') == 'system' and 'message' in row)
                if not is_message:
                    if self._compact_boundary(row):
                        emit(row.get('uuid') or digest([index, 'compact']), 'tool_summary', '对话已压缩', row)
                    if row.get('type') == 'ai-title' and isinstance(row.get('aiTitle'), str) and not row.get('isMeta') and not row.get('isVisibleInTranscriptOnly'):
                        # Only this explicitly supported title field is read.
                        # bridge-session/account/organization metadata stays opaque.
                        state['ai_title'] = public_text(row['aiTitle'], hidden_secrets)[:120] or None
                        state['ai_title_record'] = index
                    counts['ignoredRecords' if row.get('type') in CLAUDE_AUXILIARY else 'unknownRecords'] += 1
                    continue
                mid, message = row['uuid'], row.get('message')
                if not isinstance(message, dict):
                    raise HistoryStructureError(f'第{index + 1}条消息缺失或不是对象')
                if message.get('role') != row['type']:
                    raise HistoryStructureError(f'第{index + 1}条消息role与记录类型不一致')

            role = message.get('role')
            if role not in {'user', 'assistant', 'system', 'developer'}:
                raise HistoryStructureError(f'第{index + 1}条消息role非法')
            content = message.get('content')
            blocks = [{'type': 'text', 'text': content}] if isinstance(content, str) else content
            if not isinstance(blocks, list) or not all(isinstance(block, dict) for block in blocks):
                raise HistoryStructureError(f'第{index + 1}条消息content结构非法')
            if self._compact_boundary(row):
                emit(mid, 'tool_summary', '对话已压缩', row)
                continue
            if row.get('isMeta') or row.get('isVisibleInTranscriptOnly'):
                counts['internalMessages'] += 1
                continue
            if message.get('channel') in {'analysis', 'reasoning'} or role == 'developer':
                continue
            if message.get('channel') not in {None, 'final', 'commentary'}:
                raise HistoryStructureError(f'第{index + 1}条消息channel未知')
            if role == 'system':
                # NativeMessagePart has no system role. Never upload raw system
                # instructions; retain a safe notice, mapped to system on import.
                if self.agent_type == 'claude':
                    emit(mid, 'tool_summary', '[系统消息]', row)
                continue
            texts, tools = [], []
            for block in blocks:
                kind = block.get('type')
                if not isinstance(kind, str):
                    raise HistoryStructureError(f'第{index + 1}条消息内容块缺少类型')
                if kind in private:
                    continue
                if kind in {'image', 'image_url', 'input_image'}:
                    texts.append('[图片]')
                elif kind in {'text', 'input_text', 'output_text'}:
                    if not isinstance(block.get('text'), str):
                        raise HistoryStructureError(f'第{index + 1}条消息text不是字符串')
                    texts.append(block['text'])
                elif kind in {'tool_use', 'tool_result'}:
                    if kind == 'tool_use':
                        name = tool_name(block.get('name'))
                        if isinstance(block.get('id'), str):
                            calls[call_key(block['id'])] = name
                        tools.append(name + '：历史调用')
                    else:
                        call = block.get('tool_use_id')
                        name = calls.get(call_key(call), '工具') if isinstance(call, str) else '工具'
                        tools.append(name + '：历史返回记录')
                else:
                    counts['unknownBlocks'] += 1
                    texts.append('[不支持的内容块]')
            emit(mid, role, ''.join(texts), row)
            emit(mid, 'tool_summary', '\n'.join(tools), row)
        source.title = state.get('ai_title') or state.get('first_title')
        return result



    def list(self, workspaces, excluded=()):
        self.diagnostics = []
        if not self.root.is_dir():
            self.diagnostics.append("Runtime历史目录不可用")
            return []
        terminals = self._terminal_history()
        values = []
        paths = self.paths()
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
