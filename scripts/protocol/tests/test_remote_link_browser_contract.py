"""D44: local browser aliases reuse D43 without changing the wire contract."""
from pathlib import Path
import json
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = ROOT / 'packages/protocol'
BASE = 'b84fe9137bcc35e0bb97f9f149d75476ca358c8d'
LOCAL_FILE = PROTOCOL / 'openapi/local-chat.v2.yaml'
# Historical D44 release audit; live v1/v2 routes and auth are tested in test_remote_sync_contract.
def frozen(path):
    return subprocess.check_output(['git', 'show', f'500bf1f:{path}'], cwd=ROOT).decode('utf-8')

LOCAL = yaml.safe_load(frozen('packages/protocol/openapi/local-chat.v2.yaml'))
V1 = yaml.safe_load(frozen('packages/protocol/openapi/local-hub.v1.yaml'))
OPERATIONS = [('/link', 'get'), ('/pairing', 'post'), ('/pairing', 'delete'), ('/unlink', 'post')]


def original(relative):
    return subprocess.check_output(['git', 'show', f'{BASE}:{relative}'], cwd=ROOT).decode('utf-8')


def resolve(ref):
    file, pointer = ref.split('#', 1)
    path = (LOCAL_FILE.parent / file).resolve() if file else LOCAL_FILE
    raw = frozen(path.relative_to(ROOT).as_posix())
    node = json.loads(raw) if path.suffix == '.json' else yaml.safe_load(raw)
    for part in pointer.strip('/').split('/'):
        node = node[part.replace('~1', '/').replace('~0', '~')]
    return node


def test_only_four_operations_added_to_existing_local_cookie_group():
    old = yaml.safe_load(original('packages/protocol/openapi/local-chat.v2.yaml'))
    for path, item in old['paths'].items():
        assert LOCAL['paths'][path] == item
    added = set(LOCAL['paths']) - set(old['paths'])
    assert added == {'/api/v2/remote/link', '/api/v2/remote/pairing', '/api/v2/remote/unlink'}
    assert {(p, m) for p in added for m in LOCAL['paths'][p]} == {
        ('/api/v2/remote' + suffix, method) for suffix, method in OPERATIONS
    }
    assert LOCAL['components']['securitySchemes'] == old['components']['securitySchemes']
    assert LOCAL['components']['securitySchemes']['localSession'] == {
        'type': 'apiKey', 'in': 'cookie', 'name': 'hqagent_local_session'
    }
    ids = [op['operationId'] for path in LOCAL['paths'].values() for op in path.values()]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize('suffix,method', OPERATIONS)
def test_alias_reuses_d43_payload_and_local_browser_auth(suffix, method):
    current = LOCAL['paths']['/api/v2/remote' + suffix][method]
    legacy = V1['paths']['/api/v1/remote' + suffix][method]
    assert current['security'] == [{'localSession': []}]
    assert current.get('requestBody') == legacy.get('requestBody')
    result = current['responses']['200']
    assert result['content'] == legacy['responses']['200']['content']
    assert result['x-dataSchema'] == legacy['responses']['200']['x-dataSchema']
    assert result['x-dataSchema']['$ref'] == '../schema/remote-link.json#/$defs/RemoteLinkView'
    if method != 'get':
        params = {p['name']: p for p in current['parameters']}
        for key in ['Origin', 'Idempotency-Key']:
            assert params[key]['in'] == 'header' and params[key]['required'] is True
        assert params['Idempotency-Key'] == legacy['parameters'][0]
    else:
        assert '轮询' in current['description']


@pytest.mark.parametrize('suffix,method', OPERATIONS)
def test_success_and_boundary_errors_are_not_cacheable_and_refs_resolve(suffix, method):
    op = LOCAL['paths']['/api/v2/remote' + suffix][method]
    assert {'200', '401', '403', 'default'} <= set(op['responses'])
    if method != 'get':
        assert {'409', '422'} <= set(op['responses'])
    for response in op['responses'].values():
        if '$ref' in response:
            response = resolve(response['$ref'])
        assert response['headers']['Cache-Control']['schema'] == {'type': 'string', 'const': 'no-store'}

    def walk(node):
        if isinstance(node, dict):
            if '$ref' in node:
                assert resolve(node['$ref'])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(op)
    walk(LOCAL['components']['responses']['LocalRemoteLinkError'])


def test_d44_does_not_change_schema_error_registry_events_v1_or_cloud():
    files = [p for p in (PROTOCOL / 'schema').glob('*.json') if p.name != 'remote-sync.json'] + [
        PROTOCOL / 'registry/error-codes.yaml',
        PROTOCOL / 'events/event-dictionary.md',
        PROTOCOL / 'openapi/local-hub.v1.yaml',
        PROTOCOL / 'openapi/remote-hub.v2.yaml',
    ]
    for path in files:
        current = frozen(path.relative_to(ROOT).as_posix())
        old = original(path.relative_to(ROOT).as_posix())
        if path == PROTOCOL / 'schema/remote.json':
            # D45 explicitly adds one optional browser snapshot property.
            expected = json.loads(old)
            expected['$defs']['RemoteConversationSnapshot']['properties']['approvals'] = {
                'type': 'array', 'items': {'$ref': 'remote.json#/$defs/RemoteApprovalView'},
                'maxItems': 100,
                'description': 'Pending, unexpired approvals for this conversation; omitted means []. Truncation sets hasMore.',
            }
            assert json.loads(current) == expected
        else:
            assert current == old
    remote = json.loads(frozen('packages/protocol/schema/remote.json'))['$defs']
    frames = [d for d in remote.values() if 'wireRevision' in d.get('properties', {})]
    assert len(frames) == 27
    assert all(d['properties']['wireRevision']['const'] == 1 for d in frames)


def test_version_bump_preserves_all_existing_contract_fixtures():
    assert frozen('packages/protocol/VERSION').strip() == '0.6.3'
    assert LOCAL['info']['version'] == '0.6.2'
    manifest = json.loads(frozen('packages/protocol/fixtures/contracts/manifest.json'))
    old = json.loads(original('packages/protocol/fixtures/contracts/manifest.json'))
    assert manifest['protocolVersion'] == '0.6.3'
    assert manifest['fixtures'] == {
        **old['fixtures'],
        'remote.RemoteConversationSnapshot.with-approvals.json': 'RemoteConversationSnapshot',
    }
    for filename in old['fixtures']:
        path = PROTOCOL / 'fixtures/contracts' / filename
        assert path.read_text(encoding='utf-8') == original(path.relative_to(ROOT).as_posix())
