import hashlib
import json

from protocol.generated import python as dto
from r15_support import Worker2
from server.common import digest, stamp, uid


class Worker3(Worker2):
    def hello(self, **changes):
        return super().hello(**(dict(wireRevision=3) | changes))

    def receive(self):
        frame = self.ws.receive_json()
        getattr(dto, {1:'RemoteServerOutboundFrame',2:'RemoteV2ServerOutboundFrame',3:'RemoteV3ServerOutboundFrame'}[frame['wireRevision']]).model_validate(frame)
        return frame

    def event(self, kind, seq=None, **fields):
        self.seq = self.seq + 1 if seq is None else seq
        frame = dict(type=kind, wireRevision=3, workerId=self.worker, workerStoreId=self.store,
                     workerEpoch=self.epoch, eventId=uid(), seq=self.seq, occurredAt=stamp(self.env.clock()), **fields)
        dto.RemoteV3WorkerOutboundFrame.model_validate(frame)
        return frame

    def catalog(self, **changes):
        return super().catalog(**(dict(authorizedRoots=[dict(rootId='root',displayName='Projects',version=1)]) | changes))

    def index(self, local='native', **changes):
        payload = dict(nativeSessionId=local, workspaceId='ws', agentType='codex', title='Safe native title',
                       createdAt=stamp(self.env.clock()),updatedAt=stamp(self.env.clock()),indexVersion=1,sourceRevision='a'*64,
                       format=dict(status='readable',readerId='synthetic-v1'),
                       activity=dict(activity='unknown',observedAt=stamp(self.env.clock()),processMatch='unknown',recentlyModified=False))
        payload.update(changes)
        frame = self.event('native.index.upserted', syncGeneration=1,payload=payload)
        result = self.emit(frame)
        assert result['type'] == 'worker.events_ack', result
        items = self.browser.get('/devices/'+self.worker+'/native-sessions').json()['data']['items']
        return next(v for v in items if v['title'] == payload['title']), frame

    def received(self, frame):
        event = self.event('command.received', commandId=frame['commandId'], commandDigest=digest(frame), deliverBy=frame['deliverBy'],
                           receivedAt=stamp(self.env.clock()), **({'conversationId':frame['conversationId']} if 'conversationId' in frame else {}))
        assert self.emit(event)['type'] == 'worker.events_ack'
        return event

    def accepted(self, frame):
        return self.emit(self.event('command.accepted',commandId=frame['commandId'],receivedAt=stamp(self.env.clock()),status='accepted',
                                    **({'conversationId':frame['conversationId']} if 'conversationId' in frame else {})))

    def query_frames(self, query, value, width=1000):
        raw = json.dumps(value,ensure_ascii=False,separators=(',',':'))
        parts = [raw[i:i+width] for i in range(0,len(raw),width)]
        return [dict(type='query.result.segment',wireRevision=3,queryId=query['queryId'],requestId=query['requestId'],connectionId=query['connectionId'],
                     workerId=self.worker,workerStoreId=self.store,workerEpoch=self.epoch,resultType=query['type'][6:],
                     segmentIndex=i,segmentCount=len(parts),totalUtf8Bytes=len(raw.encode()),contentSha256=hashlib.sha256(raw.encode()).hexdigest(),text=part) for i,part in enumerate(parts)]

    def answer(self, query, value):
        for frame in self.query_frames(query,value):
            dto.RemoteV3WorkerOutboundFrame.model_validate(frame)
            self.ws.send_json(frame)


def native_page(local='native', text='ephemeral-private-body'):
    return dict(nativeSessionId=local,sourceRevision='a'*64,snapshotCursor='opaque-native-cursor-1234',hasMore=False,items=[dict(
        messageId='m',role='assistant',text=text,segmentIndex=0,segmentCount=1,totalUtf8Bytes=len(text.encode()),contentSha256=hashlib.sha256(text.encode()).hexdigest())])

def directory_page():
    return dict(rootId='root',rootVersion=1,directoryToken='worker-signed-current-folder',entries=[dict(name='child-private-name',isGitRepository=False,directoryToken='worker-signed-child-folder')],hasMore=False)
