"""PI selectors and owned-process guard checks. No PI configuration file reads."""
import hashlib
import json
import math
from pathlib import Path
import re
import shlex
from datetime import datetime, timezone

from protocol.generated.python import PiModelSelection, PiGuardCheckInput
from adapters.path_guard import PathGuard

TOOLS = ('bash', 'edit', 'find', 'grep', 'ls', 'powershell', 'read', 'write')
READ_TOOLS = ('find', 'grep', 'ls', 'read')
GUARD_REVISION = 'hub-guard-v1'
GUARD_PATH = Path(__file__).parent / 'resources' / 'pi' / 'hub-guard.mjs'
GUARD_SHA256 = 'cf4a76f6de900788027d7c6547a5e64b16ec705ca436486bbcb890f644d09809'


def sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def selector(value):
    value = PiModelSelection.model_validate({'modelId': value}).model_id_
    provider, model = value.split('/', 1)
    if any(part in {'.', '..'} for part in value.split('/')):
        raise ValueError('invalid model selector')
    return provider, model


def unique_object(text):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def finite(_):
        raise ValueError('non-finite JSON')
    value = json.loads(text, object_pairs_hook=pairs, parse_constant=finite)
    if not isinstance(value, dict):
        raise ValueError('object required')
    def check(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError('non-finite JSON')
        if isinstance(item, (dict, list)):
            for v in item.values() if isinstance(item, dict) else item:
                check(v)
    check(value)
    return value


def validate_check(raw, state, context, inventory):
    value = PiGuardCheckInput.model_validate(raw)
    if (value.session_id != state.session_id or value.node_id != state.spec.node_id
            or value.policy_revision != context['policyRevision']
            or value.tool_inventory_sha256 != inventory):
        raise ValueError('stale guard binding')
    if len(value.arguments_json.encode('utf-8')) > 65536 or sha(value.arguments_json) != value.arguments_sha256:
        raise ValueError('argument mismatch')
    remaining = datetime.fromisoformat(value.expires_at.replace('Z', '+00:00')).timestamp() - datetime.now(timezone.utc).timestamp()
    if not 0 < remaining <= 301:
        raise ValueError('expired guard request')
    return value, unique_object(value.arguments_json), min(remaining, 300)


def blocked_reason(state, tool, args):
    if tool not in TOOLS:
        return 'tool_not_allowed'
    if state.spec.read_only and tool not in READ_TOOLS:
        return 'read_only_tool'
    # Never let a task access the installation guard or authentication roots,
    # including when the user has registered an ancestor as a workspace.
    forbidden = [GUARD_PATH.parent.resolve(), Path.home() / '.pi' / 'agent',
                 Path.home() / '.codex', Path.home() / '.claude', Path.home() / '.ssh', Path.home() / '.aws']
    if state.guard.platform != 'nt':
        forbidden.extend([Path('/proc'), Path('/sys'), Path('/dev')])
    extra = getattr(state, 'private_roots', ())
    forbidden.extend(Path(p).resolve() for p in extra)
    paths = list(PathGuard._extract_paths(args))
    if tool in READ_TOOLS or tool in {'edit', 'write'}:
        paths.append(str(args.get('path', '.')))
    for candidate in paths:
        if re.search(r'[*?\[\]{}]', candidate) or '..' in candidate.replace('\\', '/').split('/'):
            return 'path_outside_scope'
        path = Path(candidate).expanduser()
        path = (path if path.is_absolute() else state.guard.root / path).resolve()
        if any(path == p or path.is_relative_to(p) or (tool in {'grep', 'find'} and p.is_relative_to(path)) for p in forbidden):
            return 'path_outside_scope'
    if tool in {'bash', 'powershell'}:
        command = args.get('command')
        if not isinstance(command, str) or re.search(r'[|;&<>`$\r\n*?{}]', command):
            return 'unsupported_shell'
        try:
            tokens = shlex.split(command, posix=state.guard.platform != 'nt')
        except ValueError:
            return 'unsupported_shell'
        if not tokens or tokens[0].lower() not in {'cat', 'head', 'type', 'get-content', 'git', 'rm', 'remove-item', 'mkdir', 'touch', 'cp', 'mv'}:
            return 'unsupported_shell'
        verb, operands = tokens[0].lower(), tokens[1:]
        if verb == 'git':
            if operands not in [['status'], ['diff'], ['log'], ['push'], ['merge']]:
                return 'unsupported_shell'
        elif verb == 'head':
            if not (len(operands) == 3 and operands[0] == '-n' and operands[1].isdigit()):
                return 'unsupported_shell'
        elif verb in {'get-content', 'remove-item'}:
            if not (len(operands) == 2 and operands[0].lower() == '-literalpath'):
                return 'unsupported_shell'
        elif len(operands) != (2 if verb in {'cp', 'mv'} else 1) or any(t.startswith('-') for t in operands):
            return 'unsupported_shell'
        # Shell scope includes every literal path operand, not only drive paths.
        for token in tokens[1:]:
            token = token.strip('\"\'')
            if token.startswith('-') or token.isdigit():
                continue
            path = Path(token).expanduser()
            path = (path if path.is_absolute() else state.guard.root / path).resolve()
            if any(path == p or path.is_relative_to(p) for p in forbidden):
                return 'path_outside_scope'
            if not state.guard.contains(token):
                return 'path_outside_scope'
    name = 'glob' if tool == 'find' else tool
    if state.guard.inspect_tool_call(name, args):
        return 'path_outside_scope'
    return None
