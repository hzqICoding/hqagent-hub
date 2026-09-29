"""Native metadata privacy erasure and fencing; no query text is ever stored."""
import json

from .common import digest


class NativeRepository:
    def remove_native_workspaces(self, owner, worker, store, allowed, through_seq):
        for row in self.db.execute("SELECT event_id,body,generation,last_seq FROM sync_log WHERE owner=? AND worker=? AND store=? AND event_type='native.index.upserted' AND body IS NOT NULL", (owner,worker,store)).fetchall():
            event=json.loads(row[1])
            if event['payload']['workspaceId'] not in allowed:
                local=event['payload']['nativeSessionId']
                self.native_fence(owner,worker,store,local,row[2],through_seq)
                self.db.execute('UPDATE sync_log SET body=NULL,redacted=1 WHERE owner=? AND worker=? AND store=? AND event_id=?',(owner,worker,store,row[0]))

    def erase_native(self, owner, worker, store, local=None, generation=None):
        for value in self.list(owner, 'native-index', worker=worker, store=store):
            if (local is None or value['_localId'] == local) and (generation is None or value['_generation'] <= generation):
                self.remove_record(owner, 'native-index', value['nativeSessionId'])
        args = [owner, worker, store]
        extra = ''
        if local is not None:
            extra += ' AND conversation=?'; args.append('native:' + local)
        if generation is not None:
            extra += ' AND generation<=?'; args.append(generation)
        self.db.execute("UPDATE sync_log SET body=NULL,evidence=NULL,redacted=1 WHERE owner=? AND worker=? AND store=? AND event_type='native.index.upserted'" + extra, args)

    def native_fence(self, owner, worker, store, local, generation, seq):
        key = digest([worker, store, local])
        prior = self.get(owner, 'native-fence', key)
        if prior and (prior['generation'], prior['seq']) >= (generation, seq): return
        self.put(owner, 'native-fence', key, dict(generation=generation, seq=seq), worker=worker, store=store)
