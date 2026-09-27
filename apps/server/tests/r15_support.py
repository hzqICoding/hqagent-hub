import hashlib

from protocol.generated import python as dto

from conftest import FakeWorker
from server.common import digest, stamp, uid


class Worker2(FakeWorker):
    def hello(self, **changes):
        frame = super().hello(wireRevision=2)
        frame.update(changes)
        return frame

    def emit(self, frame):
        self.ws.send_json(frame)
        while True:
            result = self.receive()
            if result['type'] == 'conversation.skip':
                if not hasattr(self, 'skips'):
                    self.skips = []
                self.skips.append(result)
                continue
            return result

    def receive(self):
        frame = self.ws.receive_json()
        getattr(dto, 'RemoteV2ServerOutboundFrame' if frame['wireRevision'] == 2 else 'RemoteServerOutboundFrame').model_validate(frame)
        return frame

    def event(self, kind, seq=None, **fields):
        self.seq = self.seq + 1 if seq is None else seq
        frame = dict(type=kind, wireRevision=2, workerId=self.worker, workerStoreId=self.store,
                     workerEpoch=self.epoch, eventId=uid(), seq=self.seq, occurredAt=stamp(self.env.clock()))
        frame.update(fields)
        dto.RemoteV2WorkerOutboundFrame.model_validate(frame)
        return frame

    def upsert(self, local='local', *, version=1, visibility='both', title='Computer conversation', generation=1, **changes):
        value = dict(conversationId=local, workspaceId='ws', sceneId='scene', sceneVersion=1, title=title,
                     createdAt=stamp(self.env.clock()), updatedAt=stamp(self.env.clock()), archived=False,
                     visibility=visibility, metadataVersion=version, authority='local')
        value.update(changes)
        event = self.event('sync.conversation.upserted', syncGeneration=generation, payload=value)
        assert self.emit(event)['type'] == 'worker.events_ack'
        with self.env.service.repo.transaction() as tx:
            owner = self.env.service.security.session(tx, self.browser.cookie)['owner']
            public = tx.sync_lookup(owner, self.worker, self.store, 'conversation', local)['public']
        return public

    def busy(self, ids=None, **changes):
        fields = dict(snapshotId=uid(), connectionId=self.ack['connectionId'], capturedAt=stamp(self.env.clock()), partIndex=0, partCount=1, conversationIds=ids or [])
        fields.update(changes)
        return self.emit(self.event('sync.busy.snapshot', **fields))

    def message(self, local, text, *, message=None, revision=1, sequence=1, index=0, parts=1, total=None, content_hash=None, generation=1, **changes):
        payload = dict(messageId=message or uid(), conversationId=local, messageSequence=sequence, messageRevision=revision,
                       role='assistant', createdAt=stamp(self.env.clock()), text=text, segmentIndex=index, segmentCount=parts,
                       totalUtf8Bytes=total if total is not None else len(text.encode()), contentSha256=content_hash or hashlib.sha256(text.encode()).hexdigest())
        payload.update(changes)
        return self.event('sync.message.segment', syncGeneration=generation, payload=payload)

    def received(self, frame):
        event = self.event('command.received', commandId=frame['commandId'], conversationId=frame['conversationId'], commandDigest=digest(frame), deliverBy=frame['deliverBy'], receivedAt=stamp(self.env.clock()))
        assert self.emit(event)['type'] == 'worker.events_ack'
        return event

    def accept(self, command, **fields):
        return self.emit(self.event('command.accepted', commandId=command['commandId'], conversationId=command['conversationId'], receivedAt=stamp(self.env.clock()), status='accepted', **fields))
