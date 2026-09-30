import asyncio
import json
import time

import pytest

from core.errors import HubError
from remote_support import System, FakeRemoteServer, until
from runtime.remote.deadline import DeliveryClock
from storage.local_chat import now
from test_r3_native import setup_native, fixture_history
from test_r3_wire import resource, permission
from test_r15_joint_server import RealPair, server_source


@pytest.mark.parametrize('condition',['cold-index','uncalibrated'])
def test_resource_not_ready_is_not_mislabeled_delivery_expired(tmp_path,monkeypatch,condition):
    async def scenario():
        system=System(tmp_path)
        try:
            root=tmp_path/'records'; fixture_history(root,tmp_path,'claude')
            native=setup_native(system,root,'claude'); await native.scan()
            item=(await native.listing()).items[0]
            source=await native.io(native.source,native.row(item.native_session_id))
            proof=native.confirm(source,'request-test')
            async with FakeRemoteServer(revision=3) as server:
                await system.pair(server,start=True)
                await system.worker.stop()
                ticks=[100.0]
                clock=DeliveryClock(monotonic=lambda:ticks[0],wall=lambda:ticks[0])
                system.worker.delivery.clock=clock
                clock.calibrate(now(),ticks[0])
                if condition=='uncalibrated':clock.invalidate()
                else:
                    native.indexes={}
                    with system.db.transaction() as tx:
                        tx.connection.execute('DELETE FROM native_history_indexes')
                    index=native.index_for(native.plugins[0]); original=index.refresh
                    def slow_refresh(*args,**kwargs):
                        ticks[0]+=31
                        return original(*args,**kwargs)
                    monkeypatch.setattr(index,'refresh',slow_refresh)
                    # Retry recovery is tested separately; isolate admission.
                    monkeypatch.setattr(native,'request_scan',lambda:None)
                frame=resource(system,'native.import',{'nativeSessionId':item.native_session_id,
                    'expectedIndexVersion':item.index_version,'sourceRevision':item.source_revision,'confirmation':proof})
                observed=[]; original_check=clock.check
                def checked(value):
                    try:return original_check(value)
                    except HubError as error:
                        observed.append((ticks[0],error.code,error.message));raise
                monkeypatch.setattr(clock,'check',checked)
                began=time.perf_counter()
                result,_=await system.worker.resources.receive(frame)
                print('ADMISSION_DIAGNOSTIC',condition,'elapsed_s',round(time.perf_counter()-began,4),
                    'logical_elapsed_s',ticks[0]-100,'clock_errors',observed)
                assert result['error']['code']=='REMOTE_STATE_NOT_READY'
                assert result['error']['retryable'] is True
                assert json.loads(system.worker.resources.row(frame['commandId'])['receipt_json'])=={}
                assert not system.adapter.started and not system.chat.repository.conversations()
                if condition=='cold-index':
                    monkeypatch.setattr(index,'refresh',original)
                    await native.scan()
                clock.calibrate(now(),ticks[0])
                replay,_=await system.worker.resources.receive(frame)
                assert replay==result  # Retrying one command ID cannot change its verdict.
                retry={**frame,'commandId':'new-ready-import'}
                receipt,_=await system.worker.resources.receive(retry)
                assert receipt['type']=='command.received'
                accepted,_=await system.worker.resources.receive(permission(retry,receipt))
                assert accepted['type']=='command.accepted'
                await until(lambda:system.worker.resources.row(retry['commandId'])['state']=='completed')
                assert not system.adapter.started and not system.adapter.resumed
        finally:await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('point',['first-arrival','after-source-check','late-grant'])
def test_real_expiry_is_still_rejected_without_starting_import(tmp_path,monkeypatch,caplog,point):
    async def scenario():
        system=System(tmp_path)
        try:
            root=tmp_path/'records'; fixture_history(root,tmp_path,'claude')
            native=setup_native(system,root,'claude');await native.scan()
            item=(await native.listing()).items[0]
            proof=native.confirm(await native.io(native.source,native.row(item.native_session_id)),'request-test')
            async with FakeRemoteServer(revision=3) as server:
                await system.pair(server,start=True);await system.worker.stop()
                ticks=[100.0]
                clock=DeliveryClock(monotonic=lambda:ticks[0],wall=lambda:ticks[0])
                system.worker.delivery.clock=clock;clock.calibrate(now(),100)
                frame=resource(system,'native.import',{'nativeSessionId':item.native_session_id,
                    'expectedIndexVersion':item.index_version,'sourceRevision':item.source_revision,'confirmation':proof})
                if point=='first-arrival':ticks[0]+=26
                if point=='after-source-check':
                    original=native.ready_source
                    def elapsed(row):
                        result=original(row);ticks[0]+=26;return result
                    monkeypatch.setattr(native,'ready_source',elapsed)
                caplog.set_level('INFO',logger='runtime.remote.resources')
                result,_=await system.worker.resources.receive(frame)
                if point=='late-grant':
                    assert result['type']=='command.received'
                    grant=permission(frame,result);ticks[0]+=26
                    result,_=await system.worker.resources.receive(grant)
                assert result['type']=='command.rejected' and result['error']['code']=='REMOTE_DELIVERY_EXPIRED'
                assert not system.chat.repository.conversations() and not system.adapter.started
                stage='clock_after' if point=='after-source-check' else 'clock_before'
                assert f'stage={stage}' in caplog.text and 'code=REMOTE_DELIVERY_EXPIRED' in caplog.text
                assert item.native_session_id not in caplog.text and str(root) not in caplog.text
        finally:await system.close()
    asyncio.run(scenario())


def test_real_server_import_immediately_after_hub_restart_uses_persistent_index(tmp_path,monkeypatch):
    async def scenario():
        async with RealPair(tmp_path) as pair:
            root=tmp_path/'records'; fixture_history(root,tmp_path,'claude')
            native=setup_native(pair.system,root,'claude'); await native.scan()
            async def public_index():
                response=await pair.browser.get(f'/devices/{pair.worker_id}/native-sessions')
                assert response.status_code==200,response.text
                return response.json()['data']['items']
            deadline=time.monotonic()+8
            items=[]
            while not items and time.monotonic()<deadline:
                items=await public_index();await asyncio.sleep(.02)
            assert len(items)==1
            item=items[0]
            await pair.system.close()
            pair.system=System(tmp_path)
            native=setup_native(pair.system,root,'claude')
            # Exercise admission with a cold memory cache and no scan startup.
            # Durable offsets exist; no expensive source rebuild is necessary.
            monkeypatch.setattr(native,'request_scan',lambda:None)
            index=native.index_for(native.plugins[0]); original=index.refresh
            pre_admission_refresh=[]
            def tracked(*args,**kwargs):
                with pair.system.db.locked_connection() as db:
                    admitted=db.execute("SELECT 1 FROM native_commands WHERE state IN ('admitted','completed')").fetchone()
                if not admitted:pre_admission_refresh.append(True)
                return original(*args,**kwargs)
            monkeypatch.setattr(index,'refresh',tracked)
            pair.system.worker.connector=pair.connect
            await pair.system.chat.start();await pair.system.worker.start()
            await until(lambda:pair.system.repo.get('link')['view']['connectionStatus']=='online')
            start=time.perf_counter()
            response=await pair.browser.post(f"/native-sessions/{item['nativeSessionId']}/imports",json={
                'terminalClosedConfirmed':True,'expectedIndexVersion':item['indexVersion'],'sourceRevision':item['sourceRevision']},
                headers={'Idempotency-Key':'immediate-restart-import'})
            assert response.status_code==202,response.text
            command=response.json()['data']['commandId']
            await until(lambda:pair.system.worker.resources.row(command) and pair.system.worker.resources.row(command)['state'] in {'completed','rejected','failed'})
            result=pair.system.worker.resources.row(command)
            assert result['state']=='completed',result['result_json']
            assert pre_admission_refresh==[]
            final=json.loads(result['result_json']); local=final['resourceRef']['conversationId']
            view=await pair.system.local.get('/api/v2/conversations')
            assert view.status_code==200,view.text
            local_view=next(v for v in view.json()['data'] if v['id']==local)
            assert local_view['conversationKind']=='native' and local_view['agentType']=='claude'
            assert 'kind' not in local_view
            await until(lambda:pair.cloud_conversation(local) is not None)
            cloud=await pair.browser.get('/conversations')
            conversation=next(v for v in cloud.json()['data']['items'] if v['conversationId']==pair.cloud_conversation(local)['conversationId'])
            assert conversation['conversationKind']=='native' and conversation['agentType']=='claude' and 'kind' not in conversation
            print('RESTART_IMPORT_COMPLETED elapsed_s',round(time.perf_counter()-start,4))
            assert not pair.system.adapter.started and not pair.system.adapter.resumed
    asyncio.run(scenario())
