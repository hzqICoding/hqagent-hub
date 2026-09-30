"""Build/check the public API bundle and generated documentation tables.

Run from any directory with the repository venv Python. --write updates only
protocol artifacts; default mode detects drift. This does not run a server.
"""
from copy import deepcopy
from datetime import datetime
import argparse
import ast
import json
import hashlib
from pathlib import Path
import re

import yaml

P = Path(__file__).resolve().parents[1]
ROOT = P.parents[1]
SOURCE = P / 'openapi/remote-hub.v2.yaml'
GUIDE = P / 'remote/api-guide.md'
BUNDLE = P / 'openapi/remote-hub.v2.bundle.json'
METHODS = {'get','post','put','patch','delete','head','options'}
ATTACHMENT_OPERATIONS = {
    ('GET','/api/v2/attachments/limits'),
    ('POST','/api/v2/conversations/{conversationId}/attachments'),
    ('GET','/api/v2/attachments/{attachmentId}'),
    ('DELETE','/api/v2/attachments/{attachmentId}'),
    ('GET','/api/v2/attachments/{attachmentId}/content'),
    ('GET','/api/v2/attachments/{attachmentId}/thumbnail'),
    ('POST','/api/v2/worker/attachments'),
    ('GET','/api/v2/worker/attachments/{attachmentId}/content'),
}


def check_binary_response(response):
    assert 'x-dataSchema' not in response and 'x-errorSchema' not in response
    assert set(response['content']) <= {'application/octet-stream','image/png'}
    assert response['content']
    for media in response['content'].values():
        assert media['schema']=={'type':'string','format':'binary'}
        assert 'example' in media
    headers=response['headers']
    assert headers['Content-Disposition']['example'].startswith('attachment;')
    assert headers['Content-Disposition']['schema']['pattern']=='^attachment;'
    assert headers['X-Content-Type-Options']['schema']['const']=='nosniff'
    assert headers['Cache-Control']['schema']['const']=='no-store'
    assert 'X-Request-Id' in headers and 'Content-Length' in headers


def check_binary_request(op):
    media=op['requestBody']['content']
    assert set(media)=={'application/octet-stream'}
    assert media['application/octet-stream']['schema']=={'type':'string','format':'binary'}
    body=media['application/octet-stream']['examples']['request']['value']
    assert body==op['x-request-example']['body']
    headers=op['x-request-example']['headers']
    assert headers['Content-Length']==len(body.encode('utf-8'))
    assert headers['X-Content-Sha256']==hashlib.sha256(body.encode('utf-8')).hexdigest()
    params={p['name']:p for p in op['parameters']}
    assert all(params[n]['required'] for n in ['Idempotency-Key','Content-Length','X-File-Name','X-Content-Sha256'])
    assert params['Content-Length']['schema']['maximum']==20000000


def load(path):
    text = path.read_text(encoding='utf-8')
    return json.loads(text) if path.suffix == '.json' else yaml.safe_load(text)


def operations(api):
    return {(method.upper(), path): op for path, item in api['paths'].items()
            for method, op in item.items() if method in METHODS}


def resolve_external(ref):
    file, pointer = ref.split('#', 1)
    path = (SOURCE.parent / file).resolve()
    if not path.is_relative_to(P / 'schema'):
        raise ValueError(f'Unexpected external reference: {ref}')
    value = load(path)
    for part in pointer.strip('/').split('/'):
        value = value[part.replace('~1','/').replace('~0','~')]
    return path, pointer.rsplit('/',1)[-1], value


def bundled(api, registry):
    result = deepcopy(api)
    schemas = result.setdefault('components',{}).setdefault('schemas',{})
    loaded = set()
    def external(ref):
        path, name, value = resolve_external(ref)
        if name not in loaded:
            if name in schemas: raise ValueError(f'Schema name collision: {name}')
            loaded.add(name)
            schemas[name] = {}  # recursion guard, although current DTO graph is acyclic
            schemas[name] = walk(deepcopy(value), path)
        return '#/components/schemas/' + name
    def walk(node, origin=None):
        if isinstance(node, str):
            if node.startswith('../schema/') and '#/$defs/' in node: return external(node)
            return node
        if isinstance(node, list): return [walk(item, origin) for item in node]
        if not isinstance(node, dict): return node
        out = {}
        for key, value in node.items():
            if key == '$ref' and '#/$defs/' in value:
                if value.startswith('../schema/'):
                    out[key] = external(value)
                elif origin:
                    file, pointer = value.split('#',1)
                    target = (origin.parent / file).resolve() if file else origin
                    out[key] = external('../schema/' + target.name + '#' + pointer)
                else: raise ValueError(value)
            else: out[key] = walk(value, origin)
        if 'x-registry' in node and not node.get('x-registry-open'):
            key = node['x-registry']
            doc = load(P/'registry'/f'{key}.yaml')
            field, attr = ('errors','code') if key=='error-codes' else (key,'id')
            out['enum'] = [item[attr] for item in doc[field]]
        if 'x-generic' in node:
            out = {k:v for k,v in out.items() if k!='x-generic'}
        return out
    # Do not recurse into the mutable schema dictionary while populating it.
    original_components = result.pop('components')
    result = walk(result)
    for key,value in original_components.items():
        if key!='schemas': original_components[key]=walk(value)
    result['components']=original_components
    # Give standard OpenAPI consumers a concrete typed envelope for each response.
    for op in operations(result).values():
        for response in op['responses'].values():
            key = 'data' if 'x-dataSchema' in response else 'error' if 'x-errorSchema' in response else None
            if key:
                target = response['x-dataSchema' if key=='data' else 'x-errorSchema']
                response['content']['application/json']['schema'] = {
                    'allOf': [{'$ref':'#/components/schemas/ApiEnvelope'},
                              {'type':'object','required':['success',key],
                               'properties':{'success':{'const':key=='data'},key:target,
                                             ('error' if key=='data' else 'data'):False}}]
                }
    # YAML extension maps may use integer revision keys. A published JSON
    # object always has string keys; return that canonical representation too.
    return json.loads(json.dumps(result, ensure_ascii=False))


def table_blocks(api, registry, guidance):
    def cell(value): return str(value).replace('|','\\|').replace('\n',' ')
    lines = ['| 方法与路径 | operationId | 鉴权 / PAT scope | 成功 data |',
             '| --- | --- | --- | --- |']
    for (method,path),op in operations(api).items():
        auth=op['x-auth-mode']
        scopes=', '.join(op.get('x-required-pat-scopes',[]))
        results=[]
        for status,response in op['responses'].items():
            if status.isdigit() and 200<=int(status)<300:
                target=response.get('x-dataSchema',{}).get('$ref','原始字节流' if op.get('x-binary-download') else '原始OpenAPI文档').split('/')[-1]
                results.append(status+' '+target)
        lines.append(f'| `{method} {path}` | `{op["operationId"]}` | {auth} {scopes} | {"; ".join(results)} |')
    errors=['| code | HTTP | retryable | 中文提示 | 典型原因 | 调用方处理 | 适用域 |',
            '| --- | --- | --- | --- | --- | --- | --- |']
    for error in registry:
        g=guidance[error['code']]
        errors.append('| '+' | '.join([f'`{error["code"]}`',str(error['http']),str(error['retryable']).lower(),cell(g['message']),cell(g['cause']),cell(g['handling']),cell(g['surface'])])+' |')
    frames=['| 线路修订 | type | 类型 | 事实源 |','| --- | --- | --- | --- |']
    for file in ['remote.json','remote-sync.json','remote-native.json','remote-attachments.json']:
        for name,d in load(P/'schema'/file)['$defs'].items():
            props=d.get('properties',{})
            if 'wireRevision' in props and 'const' in props.get('type',{}):
                frames.append(f'| {props["wireRevision"]["const"]} | `{props["type"]["const"]}` | `{name}` | `{file}#/$defs/{name}` |')
    return {'API_INDEX':'\n'.join(lines),'ERROR_TABLE':'\n'.join(errors),'WIRE_INDEX':'\n'.join(frames)}


def check_example_semantics(api):
    """Check live HTTP examples, not the immutable legacy fixture history."""
    send = ('POST', '/api/v2/conversations/{conversationId}/messages')
    patch = ('PATCH', '/api/v2/devices/{workerId}')
    decide = '/api/v2/approvals/{approvalId}/decisions'
    approval = api['paths']['/api/v2/approvals/{approvalId}']['get']['responses']['200']['content']['application/json']['examples']['success']['value']['data']

    def walk(value):
        if isinstance(value, dict):
            assert value.get('deliveryState') != 'queued_offline', 'Current HTTP examples cannot advertise offline queuing'
            if {'sha256','sizeBytes','mimeType','kind','fileName'} <= value.keys():
                images={'image/jpeg','image/png','image/webp','image/gif'}
                assert value['kind'] == ('image' if value['mimeType'] in images else 'file')
                assert value['mimeType'] in images | {'application/pdf','text/plain'}
                assert 0 < value['sizeBytes'] <= (10000000 if value['kind']=='image' else 20000000)
                assert not any(c in value['fileName'] for c in '/\\\r\n\x00')
            if {'support','cliEntry','runtimeImplemented','verified','mimeTypes','maxBytes'} <= value.keys():
                if value['support']=='supported':
                    assert value['cliEntry']=='supported' and value['runtimeImplemented'] is True and value['verified'] is True
                    assert value['mimeTypes'] and 0 < value['maxBytes'] <= 10000000
            if 'suspendedAt' in value:
                assert value['remoteAccess'] == 'suspended'
                assert datetime.fromisoformat(value['suspendedAt']) <= datetime.fromisoformat(value['observedAt'])
            for nested in value.values(): walk(nested)
        elif isinstance(value, list):
            for nested in value: walk(nested)

    for key, op in operations(api).items():
        request = op['x-request-example']
        if key[0] == 'GET' and not any(p['name'] in {'cursor','before','after'} for p in op['parameters']):
            assert not {'REMOTE_CURSOR_INVALID','REMOTE_CURSOR_EXPIRED'}.intersection(op['x-error-codes'])
        if 'requestBody' in op:
            if op.get('x-streaming-upload'):check_binary_request(op)
            else:assert request['body'] == op['requestBody']['content']['application/json']['examples']['request']['value']
        for status, response in op['responses'].items():
            if not status.startswith('2') or 'x-dataSchema' not in response: continue
            kind = response['x-dataSchema']['$ref'].split('/')[-1]
            for example in response['content']['application/json']['examples'].values():
                data = example['value']['data'];walk(data)
                if kind == 'RemoteQueuedReceipt':
                    assert {'NOT_FOUND','REMOTE_DELIVERY_EXPIRED'} <= set(op['x-error-codes'])
                    assert data['status'] == 'queued' and data['workerOnline'] is True
                    assert data['deliveryState'] == 'queued_online'
                    assert ('conversationSeq' in data) == (key == send), 'Only a new run.submit receipt allocates a sequence'
                    ttl = datetime.fromisoformat(data['expiresAt']) - datetime.fromisoformat(example['x-observed-at'])
                    assert 0 < ttl.total_seconds() <= 30
                if kind == 'RemoteResourceQueuedReceipt':
                    assert key[0] == 'POST'
                    assert 'conversationSeq' not in data and 'conversationId' not in data and 'runId' not in data
                    assert data['status'] == 'queued' and data['deliveryState'] == 'queued_online' and data['workerOnline'] is True
                    expected_type = 'native.import' if key[1].endswith('/imports') else 'workspace.register'
                    assert data['type'] == expected_type
                    ttl = datetime.fromisoformat(data['expiresAt']) - datetime.fromisoformat(example['x-observed-at'])
                    assert 0 < ttl.total_seconds() <= 30
                if kind in {'NativeMessagePage', 'DirectoryListingPage'}:
                    assert op.get('x-ephemeral-result') is True and op.get('x-persist-response') is False
                    assert op['security'] == [{'remoteSession': []}]
                    assert 'REMOTE_QUERY_TIMEOUT' in op['x-error-codes']
                    assert len(json.dumps(data, ensure_ascii=False).encode('utf-8')) <= 1048576
                    field = 'before' if kind == 'NativeMessagePage' else 'nextCursor'
                    assert (field in data) == data['hasMore']
                if key == patch:
                    change = request['body'];prior = example['x-before']
                    assert data['version'] == change['expectedVersion'] + 1 == prior['version'] + 1
                    assert data['deviceName'] == prior['deviceName']
                    assert data['remoteAccess'] == change['remoteAccess']
                    assert data['displayName'] == change['displayName']
                if key == ('POST', decide):
                    assert not (approval['remoteApprovalAllowed'] is False and request['body']['decision'] == 'approve'), 'A blocked high-risk approval cannot illustrate successful remote approve'
                if key[1].endswith('/cancellations'):
                    assert data['type'] == 'run.submit' and data['withdrawalState'] == 'requested'
                    assert data['withdrawalCommandId'] != data['commandId']
                    # This is the original command projection, not a new control receipt.
                if kind == 'RemoteSyncMessagePage':
                    assert all('messageSequence' in m and 'messageRevision' in m for m in data['items'])
                if kind == 'RemoteConversationSnapshot':
                    for item in data.get('approvals', []):
                        assert item['status'] == 'pending'
                        assert datetime.fromisoformat(item['expiresAt']) > datetime.fromisoformat(data['observedAt'])
                if kind == 'RemoteApiTokenIssueReplayView':
                    assert data['secretAvailable'] is False and 'secret' not in data


def check(api, registry, guidance, bundle):
    codes={e['code']:e for e in registry}
    assert set(guidance)==set(codes), 'Error guidance must match the registry exactly'
    assert api['info']['version']==(P/'VERSION').read_text().strip()
    ops=operations(api)
    tree=ast.parse((ROOT/'apps/server/server/app.py').read_text(encoding='utf-8'))
    routes=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ROUTES' for t in n.targets))
    runtime={(row[0],'/api/v2'+row[1]) for row in routes}
    planned={('PATCH','/api/v2/devices/{workerId}'),('DELETE','/api/v2/devices/{workerId}'),('GET','/api/v2/api-tokens'),('POST','/api/v2/api-tokens'),('DELETE','/api/v2/api-tokens/{tokenId}'),('GET','/api/v2/openapi.json'),
             ('GET','/api/v2/devices/{workerId}/native-sessions'),
             ('GET','/api/v2/native-sessions/{nativeSessionId}'),
             ('GET','/api/v2/native-sessions/{nativeSessionId}/messages'),
             ('POST','/api/v2/native-sessions/{nativeSessionId}/imports'),
             ('POST','/api/v2/devices/{workerId}/directory-listings'),
             ('POST','/api/v2/devices/{workerId}/workspaces')}
    assert set(ops) == runtime | planned | ATTACHMENT_OPERATIONS, 'Missing current/planned route or unexpected implementation scope'
    pat={('GET','/api/v2/devices'):'devices:read',('GET','/api/v2/devices/{workerId}'):'devices:read',('GET','/api/v2/devices/{workerId}/catalog'):'devices:read',('PATCH','/api/v2/devices/{workerId}'):'devices:manage',('DELETE','/api/v2/devices/{workerId}'):'devices:delete',('POST','/api/v2/devices/{workerId}/revocations'):'devices:delete'}
    ids=[]
    for key,op in ops.items():
        ids.append(op['operationId'])
        assert op.get('description') and op.get('x-request-example')
        assert set(op['x-error-codes']) <= set(codes)
        personal=any('personalAccessToken' in s for s in op['security'])
        assert personal == (key in pat)
        if personal:
            assert op['security']==[{'remoteSession':[]},{'personalAccessToken':[]}]
            assert op['x-required-pat-scopes']==[pat[key]]
        if key in ATTACHMENT_OPERATIONS:
            worker=key[1].startswith('/api/v2/worker/')
            assert op['security']==[{'workerDevice' if worker else 'remoteSession':[]}]
            if key[0]=='POST':
                assert op.get('x-streaming-upload') is True
                check_binary_request(op)
                if worker:assert 'REMOTE_DEVICE_SUSPENDED' not in op['x-error-codes']
                else:assert 'REMOTE_DEVICE_SUSPENDED' in op['x-error-codes']
        if key[0] in {'POST','PUT','PATCH','DELETE'}:
            assert any(p['name']=='Idempotency-Key' and p['required'] for p in op['parameters'])
        represented=set()
        for status,response in op['responses'].items():
            assert 'X-Request-Id' in response['headers']
            if op.get('x-binary-download') and status=='200':
                assert key in ATTACHMENT_OPERATIONS
                check_binary_response(response)
                continue
            media=response['content']['application/json']
            if key==('GET','/api/v2/openapi.json') and status=='200':
                assert 'example' in media
                continue
            assert media['examples']
            for ex in media['examples'].values():
                value=ex['value']
                assert value['requestId']==response['headers']['X-Request-Id']['example']
                assert ('data' in value) == value['success']
                assert ('error' in value) != value['success']
                if 'error' in value:
                    error=value['error'];entry=codes[error['code']]
                    assert int(status)==entry['http'] and error['retryable']==entry['retryable']
                    assert error['message']==guidance[error['code']]['message']
                    represented.add(error['code'])
        assert represented==set(op['x-error-codes'])
    assert len(ids)==len(set(ids))
    assert api['paths']['/api/v2/devices/{workerId}/revocations']['post']['deprecated'] is True
    def walk(node):
        if isinstance(node,dict):
            if '$ref' in node:
                ref=node['$ref'];assert ref.startswith('#/'),ref
                target=bundle
                for part in ref[2:].split('/'):target=target[part.replace('~1','/').replace('~0','~')]
            for value in node.values():walk(value)
        elif isinstance(node,list):
            for value in node:walk(value)
    walk(bundle)
    check_example_semantics(api)
    return len(runtime),len(ops)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');args=parser.parse_args()
    api=load(SOURCE);registry=load(P/'registry/error-codes.yaml')['errors'];guidance=load(P/'remote/http-error-guidance.yaml')['errors']
    bundle=bundled(api,registry);runtime,total=check(api,registry,guidance,bundle)
    expected=json.dumps(bundle,ensure_ascii=False,indent=2,sort_keys=True)+'\n'
    text=GUIDE.read_text(encoding='utf-8')
    for name,block in table_blocks(api,registry,guidance).items():
        pattern=f'<!-- BEGIN {name} -->.*?<!-- END {name} -->'
        assert re.search(pattern,text,re.S),name
        text=re.sub(pattern,lambda _:f'<!-- BEGIN {name} -->\n{block}\n<!-- END {name} -->',text,flags=re.S)
    if args.write:
        BUNDLE.write_text(expected,encoding='utf-8',newline='\n');GUIDE.write_text(text,encoding='utf-8',newline='\n')
    else:
        assert BUNDLE.read_text(encoding='utf-8')==expected,'Public bundle drift; run --write'
        assert GUIDE.read_text(encoding='utf-8')==text,'Guide table drift; run --write'
    print(f'API contract verified: {runtime} current + {total-runtime} planned HTTP operations; {len(registry)} error codes; self-contained bundle; examples/auth/request IDs consistent')

if __name__=='__main__':main()
