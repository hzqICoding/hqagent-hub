"""Offline measurement: python tests/probe_database_locks.py <new empty directory>.

Starts the real Hub lifespan with fake Agent execution, 80 synthetic history
files and real OS process observation. Prints durations/counts only; it neither
reads user history nor pairs a remote server. Use the same fixture before/after.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

hub = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(hub), str(hub / 'tests')]
from remote_support import System
from test_r3_native import fixture_history, setup_native
from runtime.native.activity import process_match
from core.diagnostics import configure_logging
from runtime.loop_monitor import LoopMonitor
import storage.locking as locking


async def main():
    root = Path(sys.argv[1])
    root.mkdir(parents=True)
    log = configure_logging(root)
    records = []
    original = locking.emit
    def capture(event, **fields):
        if event == 'db.lock.slow':
            records.append(fields)
        if fields.get('holdMs', 0) >= 300 or event != 'db.lock.slow':
            original(event, **fields)
    locking.emit = capture
    system = System(root)
    system.db._lock.threshold = 0
    native = setup_native(system, root / 'records')
    native.probe = process_match  # Real OS process metadata observation; no Agent execution.
    for number in range(80):
        fixture_history(root / 'records' / str(number), root,
                        identifier=f'00000000-0000-4000-8000-{number:012d}')
    monitor = LoopMonitor()
    latencies = []
    running = True
    async def tick():
        while running:
            start = time.monotonic()
            await asyncio.sleep(.05)
            latencies.append((time.monotonic()-start)*1000)
    ticker = asyncio.create_task(tick())
    monitor.start()
    try:
        async with system.application.app.router.lifespan_context(system.application.app):
            for phase in ('startup', 'steady'):
                records.clear()
                latencies.clear()
                start = time.monotonic()
                await native.scan()
                await system.worker.pi.refresh(cached=True)
                await system.local.get('/api/v1/bootstrap')
                await asyncio.sleep(.2)
                groups = {}
                for row in records:
                    stack = [f for f in row['stack'] if f['file'] not in {'database.py','locking.py','contextlib.py'}]
                    frame = stack[-1]
                    key = frame['file']+':'+frame['function']
                    groups[key] = max(groups.get(key, 0), row['holdMs'])
                print(json.dumps(dict(phase=phase, elapsedMs=round((time.monotonic()-start)*1000, 2),
                    maxSleepMs=round(max(latencies, default=0), 2), top=[(k,round(v,2)) for k,v in sorted(groups.items(),key=lambda p:-p[1])[:6]]), ensure_ascii=False), flush=True)
            with system.db.locked_connection() as db:
                print(json.dumps({'nativeCount':db.execute('SELECT COUNT(*) FROM native_sources').fetchone()[0]}), flush=True)
            assert not system.adapter.started
    finally:
        running = False
        await ticker
        await monitor.close()
        await system.close()
        log.close()

if __name__ == '__main__':
    asyncio.run(main())
