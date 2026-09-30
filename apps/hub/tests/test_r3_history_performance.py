"""Synthetic large-file budgets plus work counters, independent of machine speed."""
import asyncio
import json
import os
import time
import threading

import pytest

from core.errors import HubError
from remote_support import System, FakeRemoteServer, until
from storage.local_chat import now
from test_r3_native import setup_native


def large_history(root, workspace, count=12000):
    root.mkdir(parents=True)
    vendor='00000000-0000-4000-8000-000000000099'
    path=root/'large.jsonl'
    stamp=now()
    def record(number,text):
        return {'type':'user' if number==0 else 'assistant','sessionId':vendor,'cwd':str(workspace),
            'version':'2.1.284','uuid':f'record-{number}','parentUuid':f'record-{number-1}' if number else None,
            'timestamp':stamp,'message':{'role':'user' if number==0 else 'assistant','content':text}}
    with path.open('w',encoding='utf-8') as out:
        for i in range(count):
            out.write(json.dumps(record(i,'Index title' if i==0 else 'BODY_NOT_IN_CACHE '+('x'*2100)))+'\n')
    (root.parent/'history.jsonl').write_text(json.dumps({'sessionId':vendor,'project':str(workspace),
        'display':'synthetic interactive provenance','timestamp':1})+'\n',encoding='utf-8')
    os.utime(path,(time.time()-60,time.time()-60))
    return path,record


def test_large_metadata_index_incremental_pages_restart_and_concurrent_apis(tmp_path):
    async def scenario():
        system=System(tmp_path)
        try:
            path,record=large_history(tmp_path/'records',tmp_path)
            size=path.stat().st_size
            assert 28_000_000<size<34_000_000
            native=setup_native(system,path.parent,'claude')
            started=time.perf_counter()
            cold=await system.local.get('/api/v2/native-sessions?limit=5')
            assert cold.status_code==200 and cold.json()['data']['items']==[]
            assert time.perf_counter()-started<2  # No cold scan in the request.
            other=await system.local.get('/api/v2/conversations')
            assert other.status_code==200 and time.perf_counter()-started<3
            await asyncio.wait_for(native.scan_job,45)
            cold_seconds=time.perf_counter()-started
            assert cold_seconds<40  # Relaxed CI wall budget; exact work checks below.
            index=native.index_for(native.plugins[0])
            parsed=index.parsed_bytes
            assert size<=parsed<size+10_000
            assert index.normalized_records==0
            started=time.perf_counter()
            hot=await system.local.get('/api/v2/native-sessions?limit=5')
            assert time.perf_counter()-started<2
            item=hot.json()['data']['items'][0]
            assert item['format']['status']=='readable'
            assert index.parsed_bytes==parsed and index.normalized_records==0
            started=time.perf_counter()
            page=await native.read(item['nativeSessionId'],limit=20)
            read_seconds=time.perf_counter()-started
            assert read_seconds<3
            assert len(page.items)==20 and page.has_more
            assert index.parsed_bytes==parsed
            assert index.normalized_records==20 and index.page_parsed_bytes<100_000
            with system.db.locked_connection() as db:
                persisted=db.execute('SELECT metadata_json FROM native_history_indexes').fetchone()[0]
            assert 'BODY_NOT_IN_CACHE' not in persisted
            assert 'offsets' in persisted and 'first_title_location' in persisted
            assert 'Index title' in persisted  # Bounded title metadata is intentional.
            from test_r3_wire import query
            async with FakeRemoteServer(revision=3) as server:
                await system.pair(server,start=True)
                started=time.perf_counter()
                await server.send(query(system,server,'query.native.messages',{'nativeSessionId':item['nativeSessionId'],'limit':20},'large-page'))
                await until(lambda:any(f.get('queryId')=='large-page' and f['type']=='query.result.segment' for f in server.frames))
                assert time.perf_counter()-started<5
                assert not any(f.get('queryId')=='large-page' and f['type']=='query.failed' for f in server.frames)
                assert not any('query.result' in raw for raw in system.repo.frames())

            extra=(json.dumps(record(12000,'APPENDED_VISIBLE_TEXT'))+'\n').encode()
            with path.open('ab') as stream:stream.write(extra)
            os.utime(path,(time.time()-60,time.time()-60))
            await native.scan()
            assert index.parsed_bytes-parsed==len(extra)
            updated=(await native.listing()).items[0]
            assert updated.source_revision!=item['sourceRevision'] and updated.index_version>item['indexVersion']
            continued=await native.read(item['nativeSessionId'],before=page.before,limit=20)
            assert continued.source_revision==page.source_revision
            assert 'APPENDED_VISIBLE_TEXT' not in continued.model_dump_json()
            source=await asyncio.to_thread(native.source,native.row(item['nativeSessionId']))
            confirmation=native.confirm(source,'before-rewrite')
            before=index.parsed_bytes
            stamp=path.stat()
            raw=path.read_bytes().replace(b'Index title',b'Other title',1)
            path.write_bytes(raw)
            os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            await native.scan()  # Even identical stat size/mtime cannot hide a rewritten prefix.
            assert index.parsed_bytes-before>=len(raw)
            with pytest.raises(HubError) as changed:
                await native.read(item['nativeSessionId'],before=page.before)
            assert changed.value.code=='NATIVE_SESSION_CHANGED'
            new_source=await asyncio.to_thread(native.source,native.row(item['nativeSessionId']))
            with pytest.raises(HubError) as stale:
                native.check(native.row(item['nativeSessionId']),new_source,confirmation)
            assert stale.value.code=='NATIVE_SESSION_CHANGED'
            await system.close()
            system=System(tmp_path)
            native=setup_native(system,path.parent,'claude')
            started=time.perf_counter()
            # Persistent offsets are available without a full background scan.
            cold_page=await native.read(item['nativeSessionId'],limit=20)
            assert len(cold_page.items)==20 and time.perf_counter()-started<3
            await native.scan()
            restored=native.index_for(native.plugins[0])
            assert restored.parsed_bytes==0
            assert restored.normalized_records==20
            print(f'SYNTHETIC bytes={size} index={cold_seconds:.3f}s read20={read_seconds:.3f}s parsed_initial={parsed} append_parsed={len(extra)} restart_parsed=0')
        finally:
            await system.close()
    asyncio.run(scenario())


def test_background_index_does_not_block_other_api_and_shutdown_joins_thread(tmp_path,monkeypatch):
    async def scenario():
        from adapters.history import check_cancelled
        from test_r3_native import fixture_history
        system=System(tmp_path)
        entered=threading.Event()
        try:
            root=tmp_path/'records'; fixture_history(root,tmp_path)
            native=setup_native(system,root)
            index=native.index_for(native.plugins[0])
            original=index._decode
            main_thread=threading.get_ident()
            def paused(raw):
                assert threading.get_ident()!=main_thread
                entered.set()
                while True:
                    check_cancelled()
                    time.sleep(.005)
                return original(raw)
            monkeypatch.setattr(index,'_decode',paused)
            cold=await system.local.get('/api/v2/native-sessions')
            assert cold.status_code==200 and not cold.json()['data']['items']
            await until(entered.is_set)
            started=time.perf_counter()
            replies=await asyncio.gather(*[system.local.get('/api/v2/conversations') for _ in range(4)])
            assert all(r.status_code==200 for r in replies) and time.perf_counter()-started<1
            await asyncio.wait_for(native.stop(),2)
            with system.db.locked_connection() as db:
                assert not db.execute('SELECT 1 FROM native_history_indexes').fetchone()
        finally:await system.close()
    asyncio.run(scenario())


def test_rewrite_during_paged_read_is_rejected_before_returning_body(tmp_path,monkeypatch):
    async def scenario():
        from test_r3_native import fixture_history
        system=System(tmp_path)
        entered=threading.Event(); release=threading.Event()
        try:
            root=tmp_path/'records'; path=fixture_history(root,tmp_path)
            native=setup_native(system,root)
            await native.scan()
            item=(await native.listing()).items[0]
            index=native.index_for(native.plugins[0]); original=index.normalized
            def paused(*args):
                entered.set()
                assert release.wait(2)
                return original(*args)
            monkeypatch.setattr(index,'normalized',paused)
            job=asyncio.create_task(native.read(item.native_session_id,limit=1))
            await until(entered.is_set)
            path.write_text(path.read_text(encoding='utf-8').replace('public answer','edited answer'),encoding='utf-8')
            release.set()
            with pytest.raises(HubError) as changed:await job
            assert changed.value.code=='NATIVE_SESSION_CHANGED'
        finally:
            release.set()
            await system.close()
    asyncio.run(scenario())
