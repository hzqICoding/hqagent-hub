"""Independent watchdog can locate a blocked event-loop thread."""
import asyncio
import logging
import os
import sys
import threading
import time

from core.diagnostics import emit, exception_fields, frame_stack


class LoopMonitor:
    def __init__(self, *, interval=.5, threshold=.3, stack_after=1.0, enabled=None):
        self.enabled = os.environ.get('HQAGENT_LOOP_MONITOR', '1') != '0' if enabled is None else enabled
        self.interval, self.threshold, self.stack_after = interval, threshold, stack_after
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.task = self.thread = None
        self.due = 0
        self.reported = False

    def start(self):
        if not self.enabled or self.task is not None:
            return
        self.loop = asyncio.get_running_loop()
        self.thread_id = threading.get_ident()
        self.previous_handler = self.loop.get_exception_handler()
        self.loop.set_exception_handler(self._exception)
        self.due = time.monotonic() + self.interval
        self.task = asyncio.create_task(self._heartbeat())
        self.thread = threading.Thread(target=self._watch, name='hub-loop-watchdog', daemon=True)
        self.thread.start()

    def _exception(self, loop, context):
        error = context.get('exception')
        emit('loop.exception', level=logging.ERROR, **(exception_fields(error) if isinstance(error, BaseException) else {}))
        # Default exception formatting can include Task repr, arguments and body.

    async def _heartbeat(self):
        while True:
            await asyncio.sleep(self.interval)
            stamp = time.monotonic()
            with self.lock:
                lag = max(0, stamp - self.due)
                self.due, self.reported = stamp + self.interval, False
            if lag >= self.threshold:
                emit('loop.lag', level=logging.WARNING, lagMs=lag * 1000)

    def _watch(self):
        while not self.stop_event.wait(min(.1, self.interval / 2)):
            with self.lock:
                stalled = time.monotonic() - (self.due - self.interval)
                if stalled < self.stack_after or self.reported:
                    continue
                self.reported = True
            frame = sys._current_frames().get(self.thread_id)
            try:
                emit('loop.blocked', level=logging.WARNING, lagMs=stalled * 1000,
                     threadId=self.thread_id, stack=frame_stack(frame))
            finally:
                del frame

    async def close(self):
        self.stop_event.set()
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.loop.set_exception_handler(self.previous_handler)
        if self.thread is not None:
            self.thread.join(timeout=.2)
