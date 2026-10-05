import asyncio
import json
import os
import time
import threading
from types import SimpleNamespace

import pytest
from protocol.generated.python import RemoteNativeImportInput, SendLocalMessageInput, SessionStatus, TaskActionInput
from core.errors import HubError
from orchestrator.sessions import SessionManager
from remote_support import System, FakeRemoteServer, until
from runtime.remote.queries import QueryChannel
from storage.local_chat import now
from test_r3_native import fixture_history, setup_native, indexed_listing
from test_r3_wire import query


async def imported(system,tmp_path):
    root=tmp_path/'records'; path=fixture_history(root,tmp_path)
    native=setup_native(system,root)
    item=(await indexed_listing(native)).items[0]
    value=RemoteNativeImportInput(terminalClosedConfirmed=True,expectedIndexVersion=item.index_version,sourceRevision=item.source_revision)
    view=await native.import_session(item.native_session_id,value,'import','request')
    return native,item,value,view,path


def test_import_is_idempotent_and_failed_commit_is_atomic(tmp_path):
    async def scenario():
        system=System(tmp_path)
        try:
            native,item,value,view,path=await imported(system,tmp_path)
            second=await native.import_session(item.native_session_id,value,'import','request')
            third=await native.import_session(item.native_session_id,value,'different-key','request')
            assert view.id==second.id==third.id and len(system.chat.repository.messages(view.id))==2
            with system.db.locked_connection() as db:
                assert db.execute("SELECT COUNT(*) FROM events WHERE type='native.closure.confirmed'").fetchone()[0]==1
            with pytest.raises(HubError) as error:
                await native.import_session(item.native_session_id,value.model_copy(update={'source_revision':'0'*64}),'import','request')
            assert error.value.code=='IDEMPOTENCY_MISMATCH'
            other=tmp_path/'other'; fixture_history(other,tmp_path,identifier='00000000-0000-4000-8000-000000000002')
            from adapters.history import FileHistory
            native.plugins.append(FileHistory('codex',other,runtime_id='agent'))
            target=(await indexed_listing(native)).items[0]
            original=native.audit
            def crash(*args,**kwargs):
                raise RuntimeError('synthetic commit failure')
            native.audit=crash
            with pytest.raises(RuntimeError):
                await native.import_session(target.native_session_id,RemoteNativeImportInput(terminalClosedConfirmed=True,
                    expectedIndexVersion=target.index_version,sourceRevision=target.source_revision),'fail','request')
            native.audit=original
            assert len(system.chat.repository.conversations())==1
            assert native.row(target.native_session_id)['conversation_id'] is None
        finally:
            await system.close()
    asyncio.run(scenario())


def test_exact_native_session_lock_is_shared_across_session_managers_and_restart(tmp_path):
    async def scenario():
        system=System(tmp_path,hold=True)
        try:
            native,item,value,view,path=await imported(system,tmp_path)
            receipt=system.chat.send(view.id,SendLocalMessageInput(clientMessageId='queue',text='queue',sessionMode='continue'),'queue')
            await native.task_input(system.chat.repository.run_record(receipt.run_id))
            await native.prepare_session(native.row(item.native_session_id)["session_id"],"synthetic-task","synthetic-node","seed")
            manager=system.tasks.runtime.sessions
            session=await manager.repository.get(native.row(item.native_session_id)['session_id'])
            another=SessionManager(manager.repository,manager.adapters)
            results=await asyncio.gather(manager.resume(session,'one',None),another.resume(session,'two',None),return_exceptions=True)
            assert sum(not isinstance(r,BaseException) for r in results)==1
            assert len(system.adapter.resumed)==1 and system.adapter.resumed[0].external_session_id=='00000000-0000-4000-8000-000000000001'
            # Even if a stale UI/session label says idle, the persistent writer
            # prevents a second manager or a restarted owner from taking it.
            await manager.repository.save(session.model_copy(update={'status':SessionStatus.IDLE}))
            with pytest.raises(HubError) as conflict:
                await another.resume(session,'third',None)
            assert conflict.value.code=='NATIVE_SESSION_WRITER_CONFLICT'
            from runtime.native.service import NativeService
            replacement=NativeService(system.repo,system.chat,system.link,plugins=native.plugins,probe=lambda _:'unknown')
            with pytest.raises(HubError) as recovered:
                await replacement.acquire_session(session.id,'after restart')
            assert recovered.value.code=='NATIVE_SESSION_WRITER_CONFLICT'
            assert len(system.adapter.resumed)==1
        finally:
            await system.close()
    asyncio.run(scenario())


def test_source_snapshot_append_is_stable_but_changed_prefix_is_rejected(tmp_path):
    async def scenario():
        system=System(tmp_path)
        try:
            root=tmp_path/'records'; path=fixture_history(root,tmp_path,text='x'*40000)
            native=setup_native(system,root); item=(await indexed_listing(native)).items[0]
            first=await native.read(item.native_session_id,limit=1)
            assert first.has_more
            with path.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({'type':'event_msg','payload':{'type':'task_complete'}})+'\n')
            second=await native.read(item.native_session_id,before=first.before,limit=1)
            assert second.source_revision==first.source_revision
            assert second.items[0].segment_index==0 and second.items[0].segment_count==3
            path.write_text(path.read_text().replace('public answer','changed answer'),encoding='utf-8')
            with pytest.raises(HubError) as error:
                await native.read(item.native_session_id,before=second.before)
            assert error.value.code=='NATIVE_SESSION_CHANGED'
        finally:
            await system.close()
    asyncio.run(scenario())


def test_native_cancel_and_retry_keep_exact_session_instead_of_starting_another(tmp_path):
    async def scenario():
        system=System(tmp_path,hold=True)
        try:
            native,item,value,view,path=await imported(system,tmp_path)
            await system.chat.start()
            first=system.chat.send(view.id,SendLocalMessageInput(clientMessageId='first',text='first',sessionMode='continue'),'first')
            await until(lambda:system.chat.repository.run_record(first.run_id)['task_id'] is not None)
            await system.chat.control(first.run_id,TaskActionInput(action='cancel'),'cancel')
            retry=await system.chat.control(first.run_id,TaskActionInput(action='retry'),'retry')
            assert retry.id!=first.run_id
            assert len(system.adapter.resumed)==2 and not system.adapter.started
            assert system.adapter.resumed[0].session_id==system.adapter.resumed[1].session_id
            assert system.adapter.resumed[0].external_session_id==system.adapter.resumed[1].external_session_id
            system.adapter.release.set()
            await until(lambda:system.chat.repository.run_record(retry.id)['status']=='succeeded')
        finally:
            await system.close()
    asyncio.run(scenario())


def test_known_tool_turn_updates_binding_watermark_but_foreign_changes_do_not(tmp_path):
    async def scenario():
        system=System(tmp_path)
        try:
            native,item,value,view,path=await imported(system,tmp_path)
            receipt=system.chat.send(view.id,SendLocalMessageInput(clientMessageId='seed',text='seed',sessionMode='continue'),'seed')
            await native.task_input(system.chat.repository.run_record(receipt.run_id))
            await native.prepare_session(native.row(item.native_session_id)["session_id"],"synthetic-task","synthetic-node","seed")
            manager=system.tasks.runtime.sessions
            session=await manager.repository.get(native.row(item.native_session_id)['session_id'])
            await manager.resume(session,'owned turn',None)
            with path.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({'type':'response_item','timestamp':now(),'payload':{'type':'message','role':'user',
                    'content':[{'type':'input_text','text':'owned turn'}]}})+'\n')
            await manager.finish(session.id)
            row=native.row(item.native_session_id)
            assert json.loads(row['source_json'])['owned_revision']==native.source(row).revision
            native.check(row,native.source(row))  # No fresh user checkbox for this attributed append.
            with path.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({'type':'event_msg','payload':{'type':'external'}})+'\n')
            os.utime(path,(time.time()-60,time.time()-60))
            with pytest.raises(HubError) as error:
                native.check(native.row(item.native_session_id),native.source(row))
            assert error.value.code=='NATIVE_SESSION_CHANGED'
        finally:
            await system.close()
    asyncio.run(scenario())


def test_continuity_reads_identity_and_witness_under_one_database_lock(tmp_path):
    async def scenario():
        system=System(tmp_path)
        try:
            first_read,writer_done=threading.Event(),threading.Event()
            original=system.repo.get
            store=original('identity')['store']
            results=[]
            def paused_get(key,tx=None):
                value=original(key,tx)
                if key=='identity' and tx is None and threading.current_thread().name=='continuity-reader' and not first_read.is_set():
                    first_read.set()
                    writer_done.wait(.3)
                return value
            system.repo.get=paused_get
            def writer():
                assert first_read.wait(2)
                with system.db.transaction() as tx:
                    system.repo.seal(tx)
                writer_done.set()
            producer=threading.Thread(target=writer)
            reader=threading.Thread(target=lambda:results.append(system.repo.check_continuity()),name='continuity-reader')
            producer.start(); reader.start()
            reader.join(3); producer.join(3)
            assert not reader.is_alive() and not producer.is_alive()
            assert results==[True]
            assert original('identity')['store']==store
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('failure',['timeout','large','disconnect','reset'])
def test_ephemeral_query_faults_never_persist_body_or_allocate_outbox(tmp_path,failure):
    async def scenario():
        system=System(tmp_path)
        sent=[]
        try:
            root=tmp_path/'records'; fixture_history(root,tmp_path)
            native=setup_native(system,root)
            async with FakeRemoteServer(revision=3) as server:
                await system.pair(server,start=True)
                await until(lambda:system.repo.get('sync-work')['phase']=='synced')
                await system.worker.stop()
                # Exercise the channel with a live binding/time bound but no
                # reliable publisher running, so no background writes mask it.
                system.worker.closed=False
                system.worker.delivery.clock.calibrate(now(),system.worker.delivery.clock.monotonic())
                frame=query(system,server,'query.native.messages',{'nativeSessionId':(await indexed_listing(native)).items[0].native_session_id,'limit':50})
                async def send(value):
                    sent.append(value)
                channel=QueryChannel(system.worker,server.connection_id,send)
                system.worker.sync.cancel_queries=channel.cancel_pending
                entered=asyncio.Event()
                async def reading(*args,**kwargs):
                    entered.set()
                    if failure=='large':
                        return SimpleNamespace(model_dump=lambda **_: {'text':'x'*1048577})
                    await asyncio.Event().wait()
                native.read=reading
                if failure=='timeout':
                    from test_r3_wire import future
                    frame['expiresAt']=future(.1)
                before=system.db.connection.total_changes
                await channel.submit(frame)
                await asyncio.wait_for(entered.wait(),2)
                if failure=='disconnect':
                    await channel.close()
                elif failure=='reset':
                    from test_r15_sync import settings
                    settings(system,False,'reset-query')
                    before=system.db.connection.total_changes
                    await until(lambda: not channel.tasks)
                else:
                    await until(lambda:bool(sent),timeout=2,scale_timeout=False)
                    assert sent[-1]['error']['code']==('REMOTE_QUERY_TIMEOUT' if failure=='timeout' else 'REMOTE_QUERY_TOO_LARGE')
                assert system.db.connection.total_changes==before
                assert all('seq' not in f and 'eventId' not in f for f in sent)
                assert not any(f['type']=='query.result.segment' for f in sent)
                await channel.close()
        finally:
            await system.close()
    asyncio.run(scenario())
