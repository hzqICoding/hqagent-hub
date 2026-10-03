"""Opaque instance/runtime image-input snapshots; never persist configuration values."""
import json
import os
from pathlib import Path
import re
import tomllib

from storage.idempotency import request_hash

TRANSPORTS = {'claude': 'stream-json-image-v1', 'codex': 'app-server-localImage-v1'}
VERSION = re.compile(r'^[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?(?:\+[A-Za-z0-9.-]+)?$')
# Authentication rotation and presentation settings intentionally do not invalidate
# paid observations. Only observable routing/model/input settings contribute.
CONFIG_KEYS = {'model', 'model_provider', 'model_providers', 'base_url', 'wire_api',
               'model_reasoning_effort', 'model_context_window', 'profile', 'profiles',
               'modelOverrides', 'availableModels', 'effortLevel'}
ENV_KEYS = {'ANTHROPIC_MODEL', 'ANTHROPIC_DEFAULT_SONNET_MODEL',
            'ANTHROPIC_DEFAULT_OPUS_MODEL', 'ANTHROPIC_DEFAULT_HAIKU_MODEL',
            'ANTHROPIC_BASE_URL', 'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX',
            'CLAUDE_CODE_USE_FOUNDRY', 'OPENAI_BASE_URL', 'CODEX_HOME', 'CLAUDE_CONFIG_DIR'}


def configuration(kind, adapter):
    runner = getattr(adapter, 'runner', None)
    executable = runner.find(kind) if runner is not None and hasattr(runner, 'find') else None
    root = Path(os.environ.get('CODEX_HOME' if kind == 'codex' else 'CLAUDE_CONFIG_DIR',
                              str(Path.home() / ('.codex' if kind == 'codex' else '.claude'))))
    path = root / ('config.toml' if kind == 'codex' else 'settings.json')
    config = {}
    try:
        value = tomllib.loads(path.read_text('utf-8')) if kind == 'codex' else json.loads(path.read_text('utf-8'))
        def filtered(value):
            if isinstance(value, dict):
                return {k: filtered(v) for k, v in value.items()
                        if not any(s in k.lower() for s in ('key', 'token', 'secret', 'password', 'header', 'credential'))}
            return value
        config = filtered({k: v for k, v in value.items() if k in CONFIG_KEYS})
        env = value.get('env', {})
        config['env'] = {k: v for k, v in env.items() if k in ENV_KEYS}
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        config = {'unreadable': True}
    extra = getattr(adapter, 'verification_configuration', None)
    return request_hash([executable, str(root), config,
                         {k: os.environ[k] for k in ENV_KEYS if k in os.environ},
                         extra() if callable(extra) else extra])


def target_for(agent_id, kind, version, model, adapter):
    target = {'agentId': agent_id, 'agentType': kind}
    if model is not None:
        target['modelId'] = model
    if version and VERSION.fullmatch(version):
        target['cliVersion'] = version
    if kind in TRANSPORTS:
        target['transport'] = TRANSPORTS[kind]
    target['targetRevision'] = request_hash([target, configuration(kind, adapter),
                                           type(adapter).__module__, type(adapter).__qualname__])
    return target
