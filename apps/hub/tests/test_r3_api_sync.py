import asyncio
import json

import pytest
from protocol.generated.python import LocalNativeSessionPage, LocalAuthorizedRootsInput, DirectoryListingInput
from remote_support import System, FakeRemoteServer, until, command_events, TOKEN
from test_remote_cookie_routes import login, ORIGIN
from test_r3_native import fixture_history, setup_native
from test_r3_wire import resource, permission
from test_r15_sync import settings


def test_local_native_cookie_and_bearer_routes_work_without_pairing_or_sync(tmp_path):
    async def scenario():
        system=System(tmp_path)
        try:
            root=tmp_path/'records'; fixture_history(root,tmp_path)
            native=setup_native(system,root)
            settings(system,False,'local-off')
            await login(system)
            listed=await system.local.get('/api/v2/native-sessions')
            page=LocalNativeSessionPage.model_validate(listed.json()['data'])
            item=page.items[0]
            invalid=await system.local.get('/api/v2/native-sessions?agentType=unknown-agent')
            assert invalid.status_code==422 and invalid.headers['cache-control']=='no-store'
            invalid=await system.local.get('/api/v2/native-sessions/'+item.native_session_id+'/messages?sourceRevision=invalid')
            assert invalid.status_code==422 and invalid.headers['cache-control']=='no-store'
            for prefix,headers in (('/api/v2',{}),('/api/v1',{'Authorization':'Bearer '+TOKEN})):
                for tail in ('', '/'+item.native_session_id, '/'+item.native_session_id+'/messages'):
                    response=await system.local.get(prefix+'/native-sessions'+tail,headers=headers)
                    assert response.status_code==200 and response.headers['cache-control']=='no-store'
                    assert TOKEN not in response.text and 'workerOnline' not in response.text
            payload={'terminalClosedConfirmed':True,'expectedIndexVersion':item.index_version,'sourceRevision':item.source_revision}
            for prefix,headers in (('/api/v2',{}),('/api/v1',{'Authorization':'Bearer '+TOKEN})):
                path=prefix+'/native-sessions/'+item.native_session_id+'/imports'
                missing_origin=await system.local.post(path,json=payload,headers={**headers,'Idempotency-Key':'same'})
                assert missing_origin.status_code==403
                missing_key=await system.local.post(path,json=payload,headers={**headers,'Origin':ORIGIN})
                assert missing_key.status_code==422
                good=await system.local.post(path,json=payload,headers={**headers,'Origin':ORIGIN,'Idempotency-Key':'same'})
                assert good.status_code==201,good.text
                assert good.headers['cache-control']=='no-store'
                assert good.headers['x-request-id']==good.json()['requestId']
                assert good.json()['data']['conversationKind']=='native'
            assert not system.adapter.started and len(system.chat.repository.conversations())==1
            system.local.cookies.clear()
            for tail in ('', '/'+item.native_session_id, '/'+item.native_session_id+'/messages'):
                unauth=await system.local.get('/api/v2/native-sessions'+tail)
                assert unauth.status_code==401 and unauth.headers['cache-control']=='no-store'
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('operation',['off','revoke','workspace'])
def test_native_index_erasure_and_sync_switch_do_not_delete_local_source(tmp_path,operation):
    async def scenario():
        system=System(tmp_path)
        try:
            root=tmp_path/'records'; source=fixture_history(root,tmp_path)
            native=setup_native(system,root)
            async with FakeRemoteServer(revision=3) as server:
                await system.pair(server,start=True)
                await until(lambda:any(f['type']=='native.index.upserted' for f in server.frames))
                if operation=='off':
                    settings(system,False,'off')
                    await until(lambda:any(f['type']=='sync.reset' for f in server.frames))
                    start=len(server.frames)
                    await asyncio.sleep(.3)
                    assert not [f for f in server.frames[start:] if f['type']=='native.index.upserted']
                    assert (await native.listing()).items  # Local-only access is independent.
                elif operation=='revoke':
                    await server.ws.close(code=4403)
                    await until(lambda:system.repo.get('link')['view']['state']=='revoked')
                    with system.db.locked_connection() as db:
                        assert not any(json.loads(r[0]).get('type')=='native.index.upserted' for r in db.execute('SELECT frame_json FROM remote_outbox'))
                else:
                    system.ports.workspaces.items=[]
                    await until(lambda:any(f['type']=='native.index.deleted' for f in server.frames),timeout=8)
                    assert next(f for f in server.frames if f['type']=='native.index.deleted')['reason']=='workspace_removed'
                    assert not (await native.listing()).items
                assert source.is_file() and not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_removed_root_rejects_resource_grant_without_registering_workspace(tmp_path):
    async def scenario():
        system=System(tmp_path)
        try:
            system.worker.native.plugins=[]
            path=tmp_path/'authorized'; path.mkdir()
            root=system.worker.roots.replace(LocalAuthorizedRootsInput(expectedVersion=1,roots=[{'path':str(path),'displayName':'root'}]),'set').roots[0]
            selected=system.worker.roots.listing(DirectoryListingInput(rootId=root.root_id,rootVersion=1),'request')
            async with FakeRemoteServer(revision=3) as server:
                await system.pair(server,start=True)
                # Pairing rotates store; get a reference from the new binding.
                selected=system.worker.roots.listing(DirectoryListingInput(rootId=root.root_id,rootVersion=1),'request')
                frame=resource(system,'workspace.register',{'rootId':root.root_id,'rootVersion':1,'directoryToken':selected.directory_token})
                await server.send(frame)
                await until(lambda:command_events(server,'resource','command.received'))
                system.worker.roots.replace(LocalAuthorizedRootsInput(expectedVersion=2,roots=[]),'remove')
                await server.send(permission(frame,command_events(server,'resource','command.received')[-1]))
                await until(lambda:command_events(server,'resource','command.rejected'))
                assert command_events(server,'resource','command.rejected')[-1]['error']['code']=='REMOTE_ROOT_NOT_AUTHORIZED'
                with system.db.locked_connection() as db:
                    assert not db.execute('SELECT 1 FROM workspaces').fetchone()
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())
