"""Owned PI RPC process. No stdout/stderr payload is logged or forwarded raw."""
import asyncio
import json
import uuid

from adapters.process import terminate_process_tree


class PiRPC:
    def __init__(self, process, event, lost):
        self.process, self.event, self.lost = process, event, lost
        self.pending = {}
        self.write_lock = asyncio.Lock()
        self.close_lock = asyncio.Lock()
        self.jobs = set()
        self.expected_close = False
        self.terminated_by_owner = False
        self.idle = True
        self.reader = asyncio.create_task(self._read())
        self.stderr = asyncio.create_task(self._stderr())

    async def write(self, value):
        async with self.write_lock:
            self.process.stdin.write((json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n').encode())
            await self.process.stdin.drain()

    async def request(self, kind, *, timeout=10, **payload):
        identifier = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self.pending[identifier] = (kind, future)
        try:
            await self.write({'id': identifier, 'type': kind, **payload})
            return await asyncio.wait_for(future, timeout)
        finally:
            self.pending.pop(identifier, None)

    async def _read(self):
        try:
            while raw := await self.process.stdout.readline():
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError('invalid RPC record')
                if value.get('type') == 'response':
                    pending = self.pending.get(value.get('id'))
                    if pending and not pending[1].done():
                        if value.get('command') != pending[0] or not value.get('success'):
                            pending[1].set_exception(RuntimeError('PI RPC command failed'))
                        else:
                            pending[1].set_result(value.get('data') or {})
                else:
                    if len(self.jobs) >= 64:
                        if value.get('type') == 'extension_ui_request' and isinstance(value.get('id'), str):
                            await self.write({'type': 'extension_ui_response', 'id': value['id'], 'cancelled': True})
                        else:
                            await self.lost()
                        continue
                    job = asyncio.create_task(self.event(value))
                    self.jobs.add(job)
                    job.add_done_callback(self._job_done)
        except (ValueError, OSError):
            pass
        finally:
            for _, future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(ConnectionError('PI transport closed'))
            if not self.expected_close:
                await self.lost()

    def _job_done(self, task):
        self.jobs.discard(task)
        if not task.cancelled() and task.exception() is not None:
            # Unknown protocol handling errors fail the process; never continue
            # after a guard callback crashed, or reflect arbitrary PI text.
            job = asyncio.create_task(self.lost())
            self.jobs.add(job)
            job.add_done_callback(self.jobs.discard)

    async def _stderr(self):
        try:
            while await self.process.stderr.read(65536):
                pass
        except OSError:
            pass

    async def force_close(self):
        async with self.close_lock:
            return await self._close()

    async def _close(self):
        self.expected_close = True
        stopped = self.process.returncode is not None
        if not stopped and self.idle:
            self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), 1)
                stopped = True
            except TimeoutError:
                pass
        if not stopped:
            stopped = await terminate_process_tree(self.process)
            self.terminated_by_owner = stopped
        if not stopped or self.process.returncode is None:
            return False
        tasks = [self.reader, self.stderr, *self.jobs]
        tasks = [t for t in tasks if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        return True
