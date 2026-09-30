"""Incremental JSONL structural index and offset reads; no cached transcript bodies."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import threading
from dataclasses import asdict
from pathlib import Path

from adapters.history import HistorySource, HistoryStructureError, MAX_SOURCE_BYTES, FILTER_VERSION, check_cancelled, digest
from core.errors import HubError


class HistoryIndex:
    policy = 'offset-index-v2:' + FILTER_VERSION

    def __init__(self, reader, repository):
        self.reader, self.repository = reader, repository
        self.policy = self.policy + ':' + digest([reader.structure_version, reader.version_policy, reader.verified_series])
        self.entries = {}
        self.lock = threading.RLock()
        self.parsed_bytes = 0
        self.normalized_records = 0
        self.page_parsed_bytes = 0
        self.hash_bytes = 0

    def key(self, path):
        return digest([self.reader.runtime_id, self.reader.agent_type, str(self.reader.root), str(Path(path))])

    def _stat(self, path):
        try:
            resolved = Path(path).resolve(strict=True)
            resolved.relative_to(self.reader.root)
            st = resolved.stat()
            if st.st_size > MAX_SOURCE_BYTES:
                raise HubError('REMOTE_SYNC_RESOURCE_LIMIT', '原生记录超过当前读取配额')
            return st
        except (OSError, ValueError):
            raise HubError('NATIVE_SESSION_CHANGED', '原生记录文件不可安全读取') from None

    @staticmethod
    def fingerprint(st):
        return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns]

    def _decode(self, raw):
        self.parsed_bytes += len(raw)
        return json.loads(raw)

    def _hash(self, stream, length):
        value = hashlib.sha256()
        remaining = length
        while remaining:
            check_cancelled()
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise HubError('NATIVE_SESSION_CHANGED', '原生快照已截断')
            value.update(chunk)
            self.hash_bytes += len(chunk)
            remaining -= len(chunk)
        return value

    def load(self, path):
        key = self.key(path)
        result = self.entries.get(key)
        if result is None:
            result = self.repository.load(key)
            if result is not None and result.get('policy') == self.policy:
                result = self.entries.setdefault(key, result)
            else:
                result = None
        return result

    @staticmethod
    def source(entry):
        if entry is None or entry.get('source') is None:
            return None
        values = dict(entry['source'])
        values.update(path=Path(values['path']), cwd=Path(values['cwd']), identity=tuple(values['identity']), messages=[])
        return HistorySource(**values)

    def _header(self, path, st, terminals):
        malformed = False
        saw_sidechain = False
        with Path(path).open('rb') as stream:
            remaining = st.st_size
            while remaining:
                check_cancelled()
                raw = stream.readline(remaining)
                remaining -= len(raw)
                if not raw.endswith(b'\n'):
                    break
                if not raw.strip():
                    continue
                try:
                    row = self._decode(raw)
                except (ValueError, UnicodeError):
                    malformed = True
                    continue
                if not isinstance(row, dict):
                    malformed = True
                    continue
                saw_sidechain |= bool(row.get('isSidechain'))
                candidate = self.reader.agent_type == 'codex' or (
                    not row.get('isSidechain') and row.get('type') in {'user', 'assistant', 'system'}
                    and all(k in row for k in ('sessionId', 'cwd', 'version')))
                if candidate:
                    self.parsed_bytes += len(raw)  # inspect's header decode
                    source = self.reader.inspect(path, terminals=terminals,
                        _data=(raw, (st.st_dev, st.st_ino), st), metadata_only=True, validate_chain=False, header_only=True)
                    if source and malformed:
                        source.readable, source.reason = False, 'JSONL含损坏或未识别的完整记录'
                    if source and not re.fullmatch(r'[0-9.]{1,32}', source.version):
                        source.version = 'unknown'
                        source.reader_id = self.reader.agent_type + '.jsonl.unknown.' + self.reader.structure_version
                    return source
        if not saw_sidechain:
            self.reader.diagnostics.append('原生记录缺少可验证的会话信封')
        return None

    @staticmethod
    def _references(row):
        """Only IDs needed to name tool-result summaries, never tool arguments."""
        message = row.get('message') if row.get('type') in {'user', 'assistant', 'system'} else row.get('payload')
        if not isinstance(message, dict):
            return []
        refs = []
        if message.get('type') in {'function_call_output', 'custom_tool_call_output'}:
            refs.append(message.get('call_id'))
        if isinstance(message.get('content'), list):
            refs.extend(b.get('tool_use_id') for b in message['content']
                        if isinstance(b, dict) and b.get('type') == 'tool_result')
        return [r for r in refs if isinstance(r, str)]

    def refresh(self, path, *, terminals=None):
        # Call only in a worker thread, outside the Hub's write transaction.
        path = str(Path(path))
        with self.lock:
            before = self._stat(path)
            old = self.load(path)
            same_identity = old is not None and old['fingerprint'][:2] == self.fingerprint(before)[:2]
            if same_identity and old['fingerprint'] == self.fingerprint(before):
                try:
                    self.verify(old)
                    if old.get('diagnostic'):
                        self.reader.diagnostics.append(old['diagnostic'])
                    return old
                except HubError as error:
                    if error.code != 'NATIVE_SESSION_CHANGED':
                        raise
            with Path(path).open('rb') as stream:
                append = False
                if same_identity and before.st_size >= old['cut'] and old.get('source'):
                    hasher = self._hash(stream, old['cut'])
                    append = hasher.hexdigest() == old['prefix_hash']
                if append:
                    entry = copy.deepcopy(old)
                    source = self.source(entry)
                    state = entry['state']
                    state['seen'] = set(state.get('seen', []))
                    stream.seek(entry['cut'])
                else:
                    source = self._header(path, before, terminals)
                    entry = dict(policy=self.policy, path=path, cut=0, records=0, offsets=[], state={})
                    entry['diagnostic'] = self.reader.diagnostics[-1] if source is None and self.reader.diagnostics else None
                    state = entry['state']
                    state['seen'] = set()
                    state['hash_ids'] = True
                    stream.seek(0)
                    hasher = hashlib.sha256()
                hidden = self.reader.secrets_provider()  # one DPAPI operation for this scan
                while stream.tell() < before.st_size:
                    check_cancelled()
                    offset = stream.tell()
                    raw = stream.readline(before.st_size - offset)
                    if not raw.endswith(b'\n'):
                        break  # retry the incomplete record on the next append
                    hasher.update(raw)
                    entry['cut'] = stream.tell()
                    if not raw.strip() or source is None or not source.readable:
                        continue
                    number = entry['records']
                    entry['records'] += 1
                    try:
                        row = self._decode(raw)
                        if not isinstance(row, dict):
                            raise ValueError()
                        self.reader._validate_identity([row], source, record_offset=number)
                        refs = {digest(key): state.get('calls', {}).get(digest(key), '工具') for key in self._references(row)}
                        items = self.reader._messages([row], source, metadata_only=True,
                            state=state, record_offset=number, hidden_secrets=hidden)
                        if state.get('first_title_record') == number:
                            state['first_title_location'] = [offset, len(raw)]
                        if state.get('ai_title_record') == number:
                            state['ai_title_location'] = [offset, len(raw)]
                        if items:
                            entry['offsets'].append(dict(offset=offset, length=len(raw), record=number, calls=refs))
                    except HistoryStructureError as error:
                        source.readable, source.reason = False, str(error)
                    except (ValueError, KeyError, TypeError):
                        source.readable, source.reason = False, '原生记录身份、版本、消息结构或父链校验失败'
                entry['prefix_hash'] = hasher.hexdigest()
                state['seen'] = sorted(state.get('seen', []))
                if source is not None:
                    source.cut, source.prefix_hash = entry['cut'], entry['prefix_hash']
                    source.modified = before.st_mtime
                    from adapters.history import stamp
                    source.updated_at = stamp(before.st_mtime)
                    source.messages = []
                    source.structure_counts = state.get('counts', {})
                    values = asdict(source)
                    values.pop('messages')
                    values.update(path=str(source.path), cwd=str(source.cwd))
                    entry['source'] = values
                else:
                    entry['source'] = None
                entry['fingerprint'] = self.fingerprint(before)
                after = self._stat(path)
                if self.fingerprint(after) != self.fingerprint(before):
                    # Concurrent append is safe at this complete-record cut.
                    # A rewrite/truncation/replacement must fail verification.
                    self.verify(entry)
                self.entries[self.key(path)] = entry
        # Do not hold the index lock while waiting for the shared SQLite lock.
        try:
            self.repository.save(self.key(path), entry)
        except Exception:
            if self.entries.get(self.key(path)) is entry:
                self.entries.pop(self.key(path), None)
            raise
        return entry

    def verify(self, entry, *, snapshot=None):
        st = self._stat(entry['path'])
        identity = (st.st_dev, st.st_ino)
        expected = tuple(snapshot['identity']) if snapshot else tuple(entry['fingerprint'][:2])
        cut = snapshot['cut'] if snapshot else entry['cut']
        prefix = snapshot['prefix_hash'] if snapshot else entry['prefix_hash']
        if identity != expected or st.st_size < cut:
            raise HubError('NATIVE_SESSION_CHANGED', '原生记录身份或长度变化')
        try:
            with Path(entry['path']).open('rb') as stream:
                if self._hash(stream, cut).hexdigest() != prefix:
                    raise HubError('NATIVE_SESSION_CHANGED', '原生记录快照前缀变化')
        except OSError:
            raise HubError('NATIVE_SESSION_CHANGED', '原生记录暂不可读取') from None
        return st

    def normalized(self, entry, descriptor, hidden):
        source = self.source(entry)
        with Path(entry['path']).open('rb') as stream:
            stream.seek(descriptor['offset'])
            raw = stream.read(descriptor['length'])
        self.normalized_records += 1
        self.page_parsed_bytes += len(raw)
        # Count page parsing independently of structural indexing.
        row = json.loads(raw)
        state = {'calls': dict(descriptor['calls']), 'first_title': '', 'hash_ids': True}
        return self.reader._messages([row], source, validate_chain=False, state=state,
            record_offset=descriptor['record'], hidden_secrets=hidden)

    def page(self, entry, position, limit):
        self.verify(entry)
        source = self.source(entry)
        if source is None or not source.readable:
            raise HubError('NATIVE_SESSION_UNSUPPORTED', source.reason if source else '原生格式不可读取')
        record, part = position if position is not None else (len(entry['offsets']) - 1, 0)
        selected, size = [], 0
        hidden = self.reader.secrets_provider()
        while record >= 0 and len(selected) < limit:
            check_cancelled()
            messages = self.normalized(entry, entry['offsets'][record], hidden)
            parts = []
            for message in reversed(messages):
                text = message['text']
                count = max(1, (len(text) + 15999) // 16000)
                sha = hashlib.sha256(text.encode()).hexdigest()
                total = len(text.encode())
                for i in range(count):
                    parts.append(dict(messageId=message['id'], role=message['role'], text=text[i*16000:(i+1)*16000],
                        **({'createdAt':message['createdAt']} if message.get('createdAt') else {}),
                        segmentIndex=i, segmentCount=count, contentSha256=sha, totalUtf8Bytes=total))
            while part < len(parts) and len(selected) < limit:
                value = parts[part]
                added = len(json.dumps(value, ensure_ascii=False).encode())
                if size + added > 1024 * 1024 - 8192:
                    self.verify(entry)
                    return selected, (record, part)
                selected.append(value); size += added; part += 1
            if part == len(parts):
                record -= 1; part = 0
        self.verify(entry)
        return selected, ((record, part) if record >= 0 else None)

    def full(self, entry, *, after=0):
        self.verify(entry)
        source = self.source(entry)
        if source is None or not source.readable:
            raise HubError('NATIVE_SESSION_UNSUPPORTED', '原生结构未通过验证')
        hidden = self.reader.secrets_provider()
        source.messages = [message for offset in entry['offsets'] if offset['offset'] >= after
                           for message in self.normalized(entry, offset, hidden)]
        self.verify(entry)
        return source
