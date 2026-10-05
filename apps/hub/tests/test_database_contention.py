import asyncio
import json
import sqlite3
import threading
import time

import pytest

from core.diagnostics import configure_logging, emit
from runtime.loop_monitor import LoopMonitor
from storage.database import Database
from remote_support import System, until
from test_r3_native import fixture_history, setup_native


def test_lock_owner_wait_and_watchdog_logs_are_metadata_only(tmp_path):
    async def scenario():
        log = configure_logging(tmp_path)
        db = Database(tmp_path / 'hub.db')
        monitor = LoopMonitor(interval=.02, threshold=.02, stack_after=.12)
        acquired = threading.Event()
        diagnosed_while_held = threading.Event()
        def holder():
            private = 'BODY_TOKEN_TICKET_COOKIE_PRIVATE'
            with db.locked_connection():
                acquired.set()
                time.sleep(.5)
                log.flush()
                if 'db.lock.wait' in log.path.read_text('utf-8'):
                    diagnosed_while_held.set()
                assert private
        thread = threading.Thread(target=holder)
        try:
            thread.start()
            assert await asyncio.to_thread(acquired.wait, 5)
            monitor.start()
            with db.locked_connection() as connection:
                connection.execute('SELECT 1').fetchone()
            await asyncio.sleep(.03)
            emit('db.lock.slow', holdMs=301, threadId=1, isLoopThread=True,
                 stack=[{'file':'probe.py', 'line':7, 'function':'read', 'locals':'PRIVATE'}],
                 sql='SQL_PRIVATE', body='BODY_PRIVATE', token='SECRET_PRIVATE')
            log.flush()
            rows = [json.loads(line) for line in log.path.read_text('utf-8').splitlines()]
            slow = next(r for r in rows if r['event'] == 'db.lock.slow' and r['threadId'] == thread.ident)
            wait = next(r for r in rows if r['event'] == 'db.lock.wait')
            blocked = next(r for r in rows if r['event'] == 'loop.blocked')
            assert slow['holdMs'] >= 300 and not slow['isLoopThread']
            assert diagnosed_while_held.is_set()  # Diagnose a wait before it finishes.
            assert wait['waitMs'] >= 300 and wait['ownerThreadId'] == thread.ident
            assert blocked['ownerThreadId'] == thread.ident and not blocked['ownerIsLoopThread']
            assert any(f['function'] == 'holder' for f in blocked['ownerStack'])
            common = {'ts', 'level', 'logger', 'event'}
            assert set(slow) == common | {'holdMs', 'threadId', 'isLoopThread', 'stack'}
            assert set(wait) == common | {'waitMs', 'threadId', 'stack', 'ownerThreadId', 'ownerIsLoopThread', 'ownerHoldMs', 'ownerStack'}
            for row in (slow, wait, blocked):
                for key in ('stack', 'ownerStack'):
                    assert all(set(f) == {'file', 'line', 'function'} for f in row.get(key, []))
            assert 'PRIVATE' not in log.path.read_text('utf-8')
        finally:
            thread.join(timeout=3)
            await monitor.close()
            db.close()
            log.close()
    asyncio.run(scenario())


def test_idle_hub_periodic_tasks_do_not_block_loop_behind_two_second_db_holder(tmp_path):
    async def scenario():
        system = System(tmp_path)
        system.worker.native.plugins = []
        acquired = threading.Event()
        def holder():
            with system.db.locked_connection():
                acquired.set()
                time.sleep(2)
        thread = threading.Thread(target=holder)
        try:
            # Exercise real lifespan, supervisor, approval expiry, remote link
            # polling and attachment maintenance, with no paired remote/model.
            async with system.application.app.router.lifespan_context(system.application.app):
                await system.worker.pi.refresh(cached=True)
                thread.start()
                assert await asyncio.to_thread(acquired.wait, 5)
                refresh = asyncio.create_task(system.worker.pi.refresh(cached=True))
                gaps = []
                for _ in range(43):
                    start = time.monotonic()
                    await asyncio.sleep(.05)
                    gaps.append(time.monotonic() - start)
                await refresh
                assert max(gaps) < .2, gaps
                assert not system.adapter.started
        finally:
            if thread.ident is not None:
                thread.join(timeout=3)
            await system.close()
    asyncio.run(scenario())


def test_native_scan_batches_preserve_identity_order_and_versions(tmp_path, monkeypatch):
    async def scenario():
        system = System(tmp_path)
        native = setup_native(system, tmp_path / 'records')
        paths = [fixture_history(tmp_path / 'records' / str(n), tmp_path,
                    identifier=f'00000000-0000-4000-8000-{n:012d}') for n in range(35)]
        sizes, counts = [], []
        original = native._publish_indexes
        def publish(rows):
            sizes.append(len(rows))
            original(rows)
            # Each batch released the shared connection before the next OS probe.
            assert not system.db._lock.owned_by_current_thread()
            with system.db.locked_connection() as db:
                counts.append(db.execute('SELECT COUNT(*) FROM native_sources').fetchone()[0])
        def probe(_):
            assert not system.db._lock.owned_by_current_thread()
            return 'unknown'
        monkeypatch.setattr(native, '_publish_indexes', publish)
        native.probe = probe
        def snapshot():
            with system.db.locked_connection() as db:
                return [(r['binding_key'], r['native_id'], json.loads(r['index_json']))
                        for r in db.execute('SELECT * FROM native_sources ORDER BY rowid')]
        try:
            await native.scan()
            first = snapshot()
            assert counts == [16, 32, 35] and sizes == [16, 16, 3]
            assert len(first) == 35 and all(r[2]['indexVersion'] == 1 for r in first)
            await native.scan()
            assert snapshot() == first  # observedAt alone must not advance versions.
            with paths[17].open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'type':'response_item', 'payload':{'type':'message', 'role':'assistant',
                    'content':[{'type':'output_text', 'text':'synthetic update'}]}}) + '\n')
            await native.scan()
            changed = snapshot()
            assert [r[:2] for r in changed] == [r[:2] for r in first]
            assert sorted(r[2]['indexVersion'] for r in changed) == [1] * 34 + [2]
            assert not system.adapter.started
        finally:
            await system.close()
    asyncio.run(scenario())


def test_pi_async_snapshot_retries_instead_of_overwriting_new_tombstones(tmp_path, monkeypatch):
    async def scenario():
        system = System(tmp_path)
        pi = system.worker.pi
        captured, release = threading.Event(), threading.Event()
        original = pi._build_snapshot
        calls = 0
        def slow(inputs):
            nonlocal calls
            result = original(inputs)
            calls += 1
            if calls == 1:
                captured.set()
                assert release.wait(5)
            return result
        monkeypatch.setattr(pi, '_build_snapshot', slow)
        job = asyncio.create_task(pi.rebuild_async())
        try:
            assert await asyncio.to_thread(captured.wait, 5)
            with system.db.transaction() as tx:
                pi.remember_deleted(tx, ['synthetic-deleted-resource'])
            release.set()
            await job
            assert calls == 2 and pi.was_pi('synthetic-deleted-resource')
            def forbidden():
                raise AssertionError('unchanged cache must not acquire DB lock')
            monkeypatch.setattr(system.db, 'locked_connection', forbidden)
            pi.rebuild()
            await pi.rebuild_async()
            monkeypatch.undo()
        finally:
            release.set()
            await asyncio.gather(job, return_exceptions=True)
            await system.close()
    asyncio.run(scenario())


def test_read_cancellation_drains_thread_before_database_close(tmp_path):
    async def scenario():
        db = Database(tmp_path / 'hub.db')
        held, release, done = threading.Event(), threading.Event(), threading.Event()
        def holder():
            with db.locked_connection():
                held.set()
                release.wait(5)
        def reader():
            with db.locked_connection() as connection:
                connection.execute('SELECT 1').fetchone()
            done.set()
        thread = threading.Thread(target=holder)
        thread.start()
        assert await asyncio.to_thread(held.wait, 5)
        task = asyncio.create_task(db.read_async(reader))
        try:
            await until(lambda: bool(db._lock.waiters))
            task.cancel()
            await asyncio.sleep(.05)
            assert not task.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert done.is_set()
        finally:
            release.set()
            thread.join(timeout=3)
            db.close()
    asyncio.run(scenario())


def test_failed_begin_releases_only_its_own_lock_level(tmp_path):
    db = Database(tmp_path / 'hub.db')
    try:
        with db.transaction():
            with pytest.raises(sqlite3.OperationalError):
                with db.transaction():
                    pass
            assert db._lock.depth == 1
        assert db._lock.owner is None and db._lock.depth == 0
    finally:
        db.close()
