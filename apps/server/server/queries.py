"""Bounded, connection-scoped query memory. Never enter the durable event ledger."""
import asyncio
import hashlib
import json
import time
from dataclasses import dataclass

from . import wire
from .common import Fault, canonical, require, stamp, uid, validated

QUERY_TIMEOUT = 10
MAX_QUERY_BYTES = 1048576


@dataclass
class QueryPlan:
    owner: str
    connection: object
    kind: str
    payload: dict
    request_id: str
    public_id: str | None = None


class Queries:
    def __init__(self, service):
        self.s = service
        self.pending = {}

    async def execute(self, plan, request):
        connection = plan.connection
        require(sum(p['plan'].owner == plan.owner for p in self.pending.values()) < 16 and
                sum(p['plan'].connection.worker == connection.worker and p['plan'].owner == plan.owner for p in self.pending.values()) < 4, 'REMOTE_RATE_LIMITED')
        with self.s.repo.transaction() as tx:
            self.s.recheck_query(tx, plan)
        from .http import CONTEXT
        remaining = QUERY_TIMEOUT - (time.monotonic() - CONTEXT.get().get('_started', time.monotonic()))
        require(remaining > 0, 'REMOTE_QUERY_TIMEOUT')
        identifier = uid(); future = asyncio.get_running_loop().create_future()
        item = dict(plan=plan, future=future, parts={}, metadata=None, size=0, deadline=time.monotonic()+remaining)
        self.pending[identifier] = item
        frame = wire.encode(dict(type='query.'+plan.kind, queryId=identifier, requestId=plan.request_id, connectionId=connection.identifier,
                    targetWorkerId=connection.worker, expectedWorkerStoreId=connection.store, workerEpoch=connection.epoch,
                    expiresAt=stamp(self.s.settings.clock()+remaining), payload=plan.payload), connection.revision)
        connection.transient.append(frame); connection.wake()
        async def disconnected():
            while True:
                if (await request.receive())['type'] == 'http.disconnect':
                    raise Fault('REMOTE_DEVICE_OFFLINE')
        watcher = asyncio.create_task(disconnected())
        try:
            done, _ = await asyncio.wait({future, watcher}, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
            require(done, 'REMOTE_QUERY_TIMEOUT')
            if watcher in done:
                watcher.result()
            value = future.result()
            with self.s.repo.transaction() as tx:
                require(self.s.security.session(tx, request.cookies.get('__Host-hqremote')) is not None, 'REMOTE_AUTH_REQUIRED')
                self.s.recheck_query(tx, plan)
                if plan.kind == 'native.messages':
                    value = dict(value, nativeSessionId=plan.public_id, items=[dict(part, messageId=self.s.security.mac('native-message-id', json.dumps([plan.owner, connection.worker, connection.store, plan.public_id, part['messageId']]))) for part in value['items']])
                require(len(canonical(value).encode()) <= MAX_QUERY_BYTES, 'REMOTE_QUERY_TOO_LARGE')
                require(time.monotonic() < item['deadline'], 'REMOTE_QUERY_TIMEOUT')
            return value
        finally:
            self.pending.pop(identifier, None)
            item['parts'].clear()
            connection.transient[:] = [f for f in connection.transient if f['queryId'] != identifier]
            watcher.cancel()
            try: await watcher
            except (asyncio.CancelledError, Fault): pass
            if not future.done(): future.cancel()
            elif not future.cancelled(): future.exception()

    def invalidate(self, owner, worker, store=None, code='REMOTE_DEVICE_OFFLINE', public_id=None, connection=None):
        for item in list(self.pending.values()):
            plan = item['plan']
            if plan.owner == owner and plan.connection.worker == worker and (store is None or plan.connection.store == store) and (public_id is None or plan.public_id == public_id) and (connection is None or plan.connection is connection):
                item['parts'].clear()
                if not item['future'].done(): item['future'].set_exception(Fault(code))

    def receive(self, connection, event):
        item = self.pending.get(event.get('queryId'))
        if not item or item['future'].done() or time.monotonic() >= item['deadline']:
            return
        plan = item['plan']
        if plan.connection is not connection or any(event.get(k) != v for k,v in dict(requestId=plan.request_id, connectionId=connection.identifier, workerId=connection.worker, workerStoreId=connection.store, workerEpoch=connection.epoch).items()):
            return  # Unknown/late/fenced results never affect reliable ACKs.
        try:
            if event['type'] == 'query.failed':
                validated(f'RemoteV{connection.revision}QueryFailed', event)
                raise Fault(event['error']['code'])  # Discard arbitrary Worker message.
            require(event.get('segmentCount',129) <= 128 and event.get('totalUtf8Bytes',MAX_QUERY_BYTES+1) <= MAX_QUERY_BYTES and len(event.get('text','')) <= 16000 and len(event.get('text','').encode()) <= 64000, 'REMOTE_QUERY_TOO_LARGE')
            event = validated(f'RemoteV{connection.revision}QueryResultSegment', event)
            require(event['resultType'] == plan.kind and event['segmentIndex'] < event['segmentCount'], 'REMOTE_SYNC_CONFLICT')
            metadata = [event[k] for k in ('segmentCount','totalUtf8Bytes','contentSha256','resultType')]
            require(item['metadata'] is None or item['metadata'] == metadata, 'REMOTE_SYNC_CONFLICT')
            item['metadata'] = metadata
            index, text = event['segmentIndex'], event['text']
            if index in item['parts']:
                require(item['parts'][index] == text, 'REMOTE_SYNC_CONFLICT')
                return
            item['size'] += len(text.encode())
            require(item['size'] <= MAX_QUERY_BYTES, 'REMOTE_QUERY_TOO_LARGE')
            require(item['size'] <= event['totalUtf8Bytes'], 'REMOTE_SYNC_CONFLICT')
            item['parts'][index] = text
            if len(item['parts']) != event['segmentCount']: return
            raw = ''.join(item['parts'][n] for n in range(event['segmentCount'])).encode()
            require(len(raw) == event['totalUtf8Bytes'] and hashlib.sha256(raw).hexdigest() == event['contentSha256'], 'REMOTE_SYNC_CONFLICT')
            value = validated('NativeMessagePage' if plan.kind == 'native.messages' else 'DirectoryListingPage', json.loads(raw))
            if plan.kind == 'native.messages':
                require(value['nativeSessionId'] == plan.payload['nativeSessionId'], 'REMOTE_TARGET_MISMATCH')
                require(not value['hasMore'] or 'before' in value, 'REMOTE_SYNC_CONFLICT')
                require(len(value['items']) <= plan.payload['limit'], 'REMOTE_SYNC_CONFLICT')
                for part in value['items']:
                    require(part['segmentIndex'] < part['segmentCount'] and len(part['text'].encode()) <= 64000, 'REMOTE_SYNC_CONFLICT')
                groups={}; previous=None
                for part in value['items']:
                    mid=part['messageId']
                    require(mid==previous or mid not in groups,'REMOTE_SYNC_CONFLICT')
                    group=groups.setdefault(mid,[])
                    if group:
                        require(part['segmentIndex']==group[-1]['segmentIndex']+1 and all(part.get(k)==group[0].get(k) for k in ('role','createdAt','segmentCount','totalUtf8Bytes','contentSha256')),'REMOTE_SYNC_CONFLICT')
                    group.append(part); previous=mid
                for group in groups.values():
                    if len(group)==group[0]['segmentCount']:
                        complete=''.join(p['text'] for p in group).encode()
                        require(len(complete)==group[0]['totalUtf8Bytes'] and hashlib.sha256(complete).hexdigest()==group[0]['contentSha256'],'REMOTE_SYNC_CONFLICT')
            else:
                require(value['rootId'] == plan.payload['rootId'] and value['rootVersion'] == plan.payload['rootVersion'], 'REMOTE_ROOT_NOT_AUTHORIZED')
                require(not value['hasMore'] or 'nextCursor' in value, 'REMOTE_SYNC_CONFLICT')
                require(len(value['entries']) <= plan.payload['limit'], 'REMOTE_SYNC_CONFLICT')
            item['parts'].clear()
            item['future'].set_result(value)
        except (Fault, ValueError, TypeError, KeyError, RecursionError) as exc:
            item['parts'].clear()
            item['future'].set_exception(exc if isinstance(exc, Fault) else Fault('REMOTE_SYNC_CONFLICT'))
