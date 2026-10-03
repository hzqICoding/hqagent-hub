"""Local structural census. Never decode, retain or emit transcript string values.

JSON bytes must be scanned to discover structure; body strings are replaced before
JSON decoding. Only structural enums, numeric CLI versions and ephemeral identity
hashes survive. No paths, IDs, titles, arguments or message values enter the report.
Uses the R3 validators on this structural projection, bypassing only version policy.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'hub'))
from adapters.history import FileHistory, HistoryStructureError

STRING = re.compile(rb'"[^"\\\x00-\x1f]*(?:\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})[^"\\\x00-\x1f]*)*"')
VERSION = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?')
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_.-]{0,79}')
IDS = {'id', 'uuid', 'parentUuid', 'sessionId', 'session_id', 'call_id', 'tool_use_id'}
ENUMS = {'type', 'role', 'channel', 'source', 'subtype', 'userType'}
CONTAINERS = re.compile(rb'[{}\[\]]')
SCHEMA_OBJECTS = {(), ('payload',), ('message',), ('payload', 'content', '[]'), ('message', 'content', '[]')}


def project(raw):
    # Track schema paths so a tool input containing keys named "type", "cwd"
    # or "version" cannot trick the projector into decoding body values.
    stack = []
    previous = 0

    def value_path():
        if not stack:
            return ()
        kind, path, key = stack[-1]
        return path + (('[]' if kind == 91 else key),)

    def replace(match):
        nonlocal previous
        for delimiter in CONTAINERS.finditer(raw, previous, match.start()):
            char = raw[delimiter.start()]
            if char in (123, 91):
                stack.append([char, value_path(), ''])
            elif stack:
                stack.pop()
        previous = match.end()
        token = match.group()
        end = match.end()
        while end < len(raw) and raw[end] in b' \t\r\n':
            end += 1
        if end < len(raw) and raw[end] == 58:
            # Field names, never their associated body values.
            key = json.loads(token) if stack and stack[-1][1] in SCHEMA_OBJECTS else 'opaque'
            if stack:
                stack[-1][2] = key
            return json.dumps(key).encode()
        path = value_path()
        key = path[-1] if path else ''
        schema_value = path[:-1] in SCHEMA_OBJECTS
        if not schema_value:
            return b'"X"'
        if key in IDS:
            return json.dumps(hashlib.sha256(token).hexdigest()).encode()
        if key in {'version', 'cli_version'}:
            value = json.loads(token) if len(token) <= 82 else ''
            return json.dumps(value if VERSION.fullmatch(value) else 'unknown').encode()
        if key in ENUMS:
            value = json.loads(token) if len(token) <= 90 else ''
            return json.dumps(value if NAME.fullmatch(value) else 'unknown').encode()
        if key == 'cwd':
            value = json.loads(token)
            return json.dumps(str(Path.cwd().anchor) if Path(value).is_absolute() else 'relative').encode()
        return b'"X"'  # Body string is never JSON-decoded.

    return json.loads(STRING.sub(replace, raw))


class CensusReader(FileHistory):
    def verified_version(self, version):
        return isinstance(version, str) and len(version) <= 80 and VERSION.fullmatch(version) is not None

    def version_rejection(self, version):
        return '' if self.verified_version(version) else 'CLI版本不是有效的major.minor.patch'


def typename(value):
    if value is None:
        return 'null'
    return {dict: 'object', list: 'array', str: 'string', bool: 'boolean', int: 'number', float: 'number'}[type(value)]


def fields(row):
    """Schema-bearing levels only; arbitrary tool input/output objects are opaque."""
    result = defaultdict(set)

    def add(value, prefix=''):
        if not isinstance(value, dict):
            return
        for key, item in value.items():
            if NAME.fullmatch(key):
                result[prefix + key].add(typename(item))

    add(row)
    for name in ('payload', 'message'):
        value = row.get(name)
        add(value, name + '.')
        if isinstance(value, dict) and isinstance(value.get('content'), list):
            for block in value['content']:
                add(block, name + '.content[].')
    return result


def census(roots):
    groups = {}
    for agent, root in roots.items():
        reader = CensusReader(agent, root)
        for path in root.rglob('*.jsonl'):
            active = 'unknown'
            source = None
            state = {'hash_ids': True}
            file_results = defaultdict(Counter)
            try:
                with path.open('rb') as stream:
                    remaining = os.fstat(stream.fileno()).st_size
                    while remaining:
                        raw = stream.readline(remaining)
                        if not raw:
                            file_results[active]['io_error'] += 1
                            break
                        remaining -= len(raw)
                        if not raw.strip():
                            continue
                        # Incomplete append is not a complete JSONL record.
                        if not raw.endswith(b'\n'):
                            file_results[active]['incomplete_tail'] += 1
                            break
                        try:
                            row = project(raw)
                            if not isinstance(row, dict):
                                raise ValueError()
                        except (ValueError, UnicodeError, RecursionError):
                            file_results[active]['json_structure'] += 1
                            continue
                        payload = row.get('payload') if agent == 'codex' else row
                        version = payload.get('cli_version' if agent == 'codex' else 'version') if isinstance(payload, dict) else None
                        if isinstance(version, str):
                            active = version
                        key = (agent, active)
                        group = groups.setdefault(key, {'records': Counter(), 'fields': defaultdict(lambda: defaultdict(set)),
                            'validation': Counter(), 'structure_validation': Counter(), 'files': Counter()})
                        kind = row.get('type', 'unknown')
                        kind = kind if isinstance(kind, str) and NAME.fullmatch(kind) else 'unknown'
                        group['records'][kind] += 1
                        for field, types in fields(row).items():
                            group['fields'][kind][field].update(types)
                        if source is None and isinstance(payload, dict):
                            vendor = payload.get('id' if agent == 'codex' else 'sessionId')
                            cwd = payload.get('cwd')
                            if isinstance(vendor, str) and isinstance(cwd, str):
                                source = SimpleNamespace(vendor_id=vendor, cwd=Path(cwd), version=active,
                                    structure_counts={}, title=None, reason='')
                        try:
                            if source is None:
                                # Auxiliary records before the first envelope still
                                # participate in Claude parent-chain validation.
                                reader._validate_chain([row], seen=state.setdefault('seen', set()), hash_ids=True)
                                category = 'no_envelope'
                            else:
                                reader._validate_identity([row], source)
                                category = 'pass'
                        except HistoryStructureError as error:
                            category = re.sub(r'第\d+条', '', str(error))
                        except (ValueError, KeyError, TypeError):
                            category = 'record_structure'
                        # Validate the message/block/parent-chain independently:
                        # non-terminal provenance is a read gate, not evidence
                        # of a changed JSONL message schema.
                        if source is not None:
                            try:
                                reader._messages([row], source, metadata_only=True, state=state, hidden_secrets=())
                                structure = 'pass'
                            except HistoryStructureError as error:
                                structure = re.sub(r'第\d+条', '', str(error))
                            except (ValueError, KeyError, TypeError):
                                structure = 'record_structure'
                            group['structure_validation'][structure] += 1
                            if category == 'pass':
                                category = structure
                        group['validation'][category] += 1
                        file_results[active][category] += 1
            except OSError:
                file_results[active]['io_error'] += 1
            for version, results in file_results.items():
                group = groups.setdefault((agent, version), {'records': Counter(), 'fields': defaultdict(lambda: defaultdict(set)),
                    'validation': Counter(), 'structure_validation': Counter(), 'files': Counter()})
                group['files']['total'] += 1
                failures = set(results) - {'pass', 'no_envelope', 'incomplete_tail'}
                if source is None:
                    failures.add('no_envelope')
                group['files']['fail' if failures else 'pass'] += 1
                for category in failures:
                    group['files'][category] += 1
                for category in ('json_structure', 'incomplete_tail', 'io_error'):
                    group['validation'][category] += results[category]
    return {agent + ':' + version: {'records': dict(g['records']), 'fields': {kind: {k: sorted(v) for k, v in fs.items()}
        for kind, fs in g['fields'].items()}, 'validation': dict(g['validation']),
        'structure_validation': dict(g['structure_validation']), 'files': dict(g['files'])}
        for (agent, version), g in sorted(groups.items())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = census({'codex': Path.home() / '.codex' / 'sessions', 'claude': Path.home() / '.claude' / 'projects'})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    for version, group in result.items():
        print(json.dumps({'version': version, 'records': group['records'], 'validation': group['validation'],
            'structure_validation': group['structure_validation'], 'files': group['files']}, ensure_ascii=False))
