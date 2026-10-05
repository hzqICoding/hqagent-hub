"""Metadata-only ownership diagnostics for the single SQLite connection lock."""
import asyncio
import logging
import sys
import threading
import time
import weakref

from core.diagnostics import emit, frame_stack


_locks = weakref.WeakSet()
_registry_lock = threading.Lock()


def waiting_owner(thread_id):
    # Never acquire a database lock from the watchdog thread. Owner snapshots
    # are replaced, not mutated; no frames/locals/SQL are retained.
    with _registry_lock:
        locks = tuple(_locks)
    for lock in locks:
        owner = lock.owner if thread_id in lock.waiters else None
        if owner is not None:
            return lock.owner_fields(owner)
    return {}


class DatabaseLock:
    def __init__(self, threshold=.3):
        self._lock = threading.RLock()
        self.threshold = threshold
        self.owner = None
        self.depth = 0
        self.waiters = {}
        with _registry_lock:
            _locks.add(self)

    def owned_by_current_thread(self):
        owner = self.owner
        return owner is not None and owner['threadId'] == threading.get_ident()

    @staticmethod
    def owner_fields(owner):
        return dict(ownerThreadId=owner['threadId'], ownerIsLoopThread=owner['isLoopThread'],
                    ownerHoldMs=(time.monotonic() - owner['acquired']) * 1000,
                    ownerStack=owner['stack'])

    def acquire(self):
        thread_id = threading.get_ident()
        try:
            asyncio.get_running_loop()
            is_loop = True
        except RuntimeError:
            is_loop = False
        start = time.monotonic()
        if not self._lock.acquire(blocking=False):
            self.waiters[thread_id] = True
            try:
                if is_loop and not self._lock.acquire(timeout=self.threshold):
                    owner = self.owner
                    emit('db.lock.wait', level=logging.WARNING, waitMs=(time.monotonic() - start) * 1000,
                         threadId=thread_id, stack=frame_stack(sys._getframe(1), limit=20),
                         **(self.owner_fields(owner) if owner else {}))
                    self._lock.acquire()
                elif not is_loop:
                    self._lock.acquire()
            finally:
                self.waiters.pop(thread_id, None)
        acquired = time.monotonic()
        if self.depth == 0:
            self.owner = dict(threadId=thread_id, acquired=acquired, isLoopThread=is_loop,
                              stack=frame_stack(sys._getframe(1), limit=20))
        self.depth += 1
        return True

    def release(self):
        owner = self.owner
        # Only the owning thread may alter metadata, matching RLock semantics.
        if owner is None or owner['threadId'] != threading.get_ident():
            raise RuntimeError('cannot release unowned database lock')
        self.depth -= 1
        final = self.depth == 0
        hold = time.monotonic() - owner['acquired']
        if final:
            self.owner = None
        self._lock.release()
        if final and hold >= self.threshold:
            emit('db.lock.slow', level=logging.WARNING, holdMs=hold * 1000,
                 threadId=owner['threadId'], isLoopThread=owner['isLoopThread'], stack=owner['stack'])

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()
