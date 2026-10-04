import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from protocol.generated.python import RemoteNativeImportInput, NativeMessagePage, DirectoryListingInput, LocalAuthorizedRootsInput
from runtime.remote.queries import QueryChannel
from runtime.workspaces import WorkspaceService
from storage.workspaces import WorkspaceRepository
from storage.local_chat import now
from remote_support import System, FakeRemoteServer, until, command_events
from test_r3_native import setup_native, fixture_history, indexed_listing


def future(seconds=9):
    return (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat().replace('+00:00','Z')


def resource(system, kind, payload, identifier='resource'):
    return {"type":kind,"wireRevision":3,"commandId":identifier,"targetWorkerId":"worker-test",
        "expectedWorkerStoreId":system.repo.get('identity')['store'],"createdAt":now(),"expiresAt":future(25),
        "deliverBy":future(25),"requestId":"request-test","payload":payload}


def permission(frame, receipt):
    return {"type":"command.delivery_granted","wireRevision":3,
        **{k:frame[k] for k in ('commandId','targetWorkerId','expectedWorkerStoreId','deliverBy')},
        "commandDigest":receipt['commandDigest'],"receivedEventId":receipt['eventId'],"grantedAt":now()}


def query(system, server, kind, payload, identifier='query'):
    return {"type":kind,"wireRevision":3,"queryId":identifier,"requestId":"query-request",
        "connectionId":server.connection_id,"targetWorkerId":"worker-test",
        "expectedWorkerStoreId":system.repo.get('identity')['store'],"workerEpoch":system.repo.get('identity')['epoch'],
        "expiresAt":future(),"payload":payload}


def test_revision3_index_ephemeral_read_and_granted_import(tmp_path):
    async def scenario():
        system=System(tmp_path)
        try:
            root=tmp_path/'records'; fixture_history(root,tmp_path,text='long public input '+ '汉😀'*18000)
            native=setup_native(system,root)
            async with FakeRemoteServer(revision=3) as server:
                await system.pair(server,start=True)
                assert server.hellos[-1]['wireRevision']==3
                await until(lambda:any(f['type']=='native.index.upserted' for f in server.frames))
                item=next(f['payload'] for f in server.frames if f['type']=='native.index.upserted')
                assert len(item['title'])<=120
                await server.send(query(system,server,'query.native.messages',{'nativeSessionId':item['nativeSessionId'],'limit':100}))
                await until(lambda:any(f['type']=='query.result.segment' for f in server.frames))
                await until(lambda:len([f for f in server.frames if f['type']=='query.result.segment'])==next(f['segmentCount'] for f in server.frames if f['type']=='query.result.segment'))
                segments=sorted([f for f in server.frames if f['type']=='query.result.segment'],key=lambda f:f['segmentIndex'])
                raw=''.join(f['text'] for f in segments)
                assert hashlib.sha256(raw.encode()).hexdigest()==segments[0]['contentSha256']
                NativeMessagePage.model_validate_json(raw)
                assert all('seq' not in f and 'eventId' not in f for f in segments)
                with system.db.locked_connection() as db:
                    assert not db.execute("SELECT 1 FROM remote_outbox WHERE frame_json LIKE '%query.result.segment%'").fetchone()
                    assert not db.execute("SELECT 1 FROM local_messages").fetchone()
                payload={"nativeSessionId":item['nativeSessionId'],"sourceRevision":item['sourceRevision'],
                    "expectedIndexVersion":item['indexVersion'],"confirmation":native.confirm(native.source(native.row(item['nativeSessionId'])),'request-test')}
                frame=resource(system,'native.import',payload)
                await server.send(frame)
                await until(lambda:command_events(server,'resource','command.received'))
                assert not system.chat.repository.conversations()
                receipt=command_events(server,'resource','command.received')[-1]
                await server.send(permission(frame,receipt))
                await until(lambda:command_events(server,'resource','command.completed'))
                done=command_events(server,'resource','command.completed')[-1]
                assert 'resultRef' not in done and 'conversationId' not in done
                assert done['resourceRef']['nativeSessionId']==item['nativeSessionId']
                await until(lambda:any(f['type']=='sync.message.segment' for f in server.frames))
                assert not system.adapter.started
                assert len(system.chat.repository.conversations())==1
                await server.send(permission(frame,receipt))
                await asyncio.sleep(.1)
                assert len(system.chat.repository.conversations())==1 and not server.errors
                submit={"type":"run.submit","wireRevision":3,"commandId":"native-followup",
                    "conversationId":"public-native-route","localConversationId":done['resourceRef']['conversationId'],
                    "conversationSeq":1,"targetWorkerId":"worker-test","expectedWorkerStoreId":system.repo.get('identity')['store'],
                    "createdAt":now(),"expiresAt":future(25),"deliverBy":future(25),"payload":{
                        "clientMessageId":"native-followup","text":"continue native","workspaceId":"workspace",
                        "conversationKind":"native","agentType":"codex","nativeSessionId":item['nativeSessionId'],"sessionMode":"continue"}}
                await server.send(submit)
                await until(lambda:command_events(server,'native-followup','command.received'))
                approval=permission(submit,command_events(server,'native-followup','command.received')[-1])
                approval['conversationId']=submit['conversationId']
                await server.send(approval)
                await until(lambda:command_events(server,'native-followup','command.completed') or command_events(server,'native-followup','command.failed'))
                assert command_events(server,'native-followup','command.completed')
                assert len(system.adapter.resumed)==1 and not system.adapter.started
                assert system.adapter.resumed[0].external_session_id=='00000000-0000-4000-8000-000000000001'
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_revision2_defers_native_history_then_revision3_backfills(tmp_path):
    async def scenario():
        system=System(tmp_path)
        try:
            root=tmp_path/'records'; fixture_history(root,tmp_path,text='native-private-before-rev3')
            native=setup_native(system,root)
            item=(await indexed_listing(native)).items[0]
            conv=await native.import_session(item.native_session_id,RemoteNativeImportInput(
                terminalClosedConfirmed=True,expectedIndexVersion=item.index_version,sourceRevision=item.source_revision),'import','request')
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server,start=True)
                await until(lambda:system.repo.get('sync-work')['phase']=='synced')
                assert server.requested_revisions[:2]==[5,2]
                assert system.repo.get('link')['view']['lastErrorCode']=='REMOTE_REVISION_REQUIRED'
                assert 'native-private-before-rev3' not in json.dumps(server.frames)
                assert not any(f.get('payload',{}).get('conversationKind')=='native' for f in server.frames)
                await system.worker.stop()
                server.revision=3
                await system.worker.start()
                await until(lambda:system.repo.get('identity').get('wireRevision')==3)
                await until(lambda:any(f['type']=='sync.message.segment' and f['payload']['conversationId']==conv.id for f in server.frames))
                assert all(f['wireRevision']==3 for f in server.frames if f['type']=='sync.message.segment')
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_directory_query_and_registration_reuse_workspace_service(tmp_path, monkeypatch):
    monkeypatch.setenv('GIT_CEILING_DIRECTORIES', str(tmp_path))
    async def scenario():
        system=System(tmp_path)
        try:
            system.worker.native.plugins=[]
            system.chat.ports.workspaces=WorkspaceService(WorkspaceRepository(system.db))
            selected=tmp_path/'projects'/'plain'; selected.mkdir(parents=True)
            root=system.worker.roots.replace(LocalAuthorizedRootsInput(expectedVersion=1,roots=[{
                'path':str(selected.parent),'displayName':'projects'}]),'roots').roots[0]
            async with FakeRemoteServer(revision=3) as server:
                await system.pair(server,start=True)
                await server.send(query(system,server,'query.directory.list',{'rootId':root.root_id,'rootVersion':1}))
                await until(lambda:any(f['type'] in {'query.result.segment','query.failed'} for f in server.frames))
                assert not [f for f in server.frames if f['type']=='query.failed'], [f['error'] for f in server.frames if f['type']=='query.failed']
                page=json.loads(''.join(f['text'] for f in server.frames if f['type']=='query.result.segment'))
                assert [e['name'] for e in page['entries']]==['plain']
                frame=resource(system,'workspace.register',{'rootId':root.root_id,'rootVersion':1,'directoryToken':page['entries'][0]['directoryToken']})
                await server.send(frame)
                await until(lambda:command_events(server,'resource','command.received'))
                await server.send(permission(frame,command_events(server,'resource','command.received')[-1]))
                await until(lambda:command_events(server,'resource','command.completed'))
                workspace=await system.chat.ports.workspaces.get_workspace(command_events(server,'resource','command.completed')[-1]['resourceRef']['workspaceId'])
                assert not workspace.capabilities.can_run_write_tasks and workspace.vcs=='none'
                assert not (selected/'.git').exists() and not server.errors
                with system.db.locked_connection() as db:
                    audits=[json.loads(r[0]) for r in db.execute("SELECT payload_json FROM events WHERE type='remote.directory.audited'")]
                assert any(a['operation']=='workspace.register' and a['requestId']==frame['requestId'] and a['resultCode']=='OK' for a in audits)
        finally:
            await system.close()
    asyncio.run(scenario())
