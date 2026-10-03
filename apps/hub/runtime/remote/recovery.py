"""Operator-requested replica rebuild; never bypasses a server identity freeze."""
from core.errors import HubError


class SyncRecovery:
    def __init__(self, repo, sync):
        self.repo, self.sync = repo, sync

    def request(self):
        if not self.repo.check_continuity():
            raise HubError('REMOTE_STORE_CHANGED', '本机存储仍需对账，不能重新同步')
        with self.repo.database.transaction() as tx:
            link = self.repo.get('link', tx)['view']
            identity = self.repo.get('identity', tx)
            pending = self.repo.get('sync-recovery', tx) or {}
            if (link['state'] == 'paired' and pending.get('store') == identity['store']
                    and pending.get('phase') in {'requested', 'waiting_reset_ack', 'backfilling'}):
                return {'requested': True}
            if (link['state'] != 'frozen' or link.get('lastErrorCode') != 'REMOTE_SYNC_CONFLICT'
                    or identity.get('wireRevision', 1) < 3 or identity.get('reconciliationRequired')):
                raise HubError('CONFLICT', '仅允许修复本机同步冲突冻结；其他冻结必须先完成对账')
            if not self.sync.settings().mirror_enabled:
                raise HubError('REMOTE_SYNC_DISABLED', '请先在本机启用同步')
            self.repo.put('sync-recovery', {'store': identity['store'], 'phase': 'requested'}, tx)
            # Permit one new handshake. Reset is deferred until that handshake
            # explicitly says ready; an actual server freeze remains binding.
            value = {**link, 'state': 'paired', 'connectionStatus': 'offline'}
            value.pop('lastErrorCode', None)
            self.repo.set_view(tx, value)
            self.repo.seal(tx)
        return {'requested': True}

    def on_hello(self, hello):
        with self.repo.database.transaction() as tx:
            pending = self.repo.get('sync-recovery', tx) or {}
            identity = self.repo.get('identity', tx)
            if pending.get('store') != identity['store'] or pending.get('phase') != 'requested':
                return
            if hello['commandDelivery'] != 'ready':
                code = hello.get('reason', {}).get('code') or 'REMOTE_STORE_CHANGED'
                pending.update(phase='blocked', code=code)
                self.repo.put('sync-recovery', pending, tx)
                view = self.repo.get('link', tx)['view']
                self.repo.set_view(tx, {**view, 'state': 'frozen', 'connectionStatus': 'offline', 'lastErrorCode': code})
                self.repo.seal(tx)
            else:
                settings = self.repo.get('sync-settings', tx)
                if not settings['mirrorEnabled']:
                    pending['phase'] = 'cancelled'
                    self.repo.put('sync-recovery', pending, tx)
                    self.repo.seal(tx)
                    return
                settings.update(version=settings['version'] + 1, syncGeneration=settings['syncGeneration'] + 1)
                self.repo.put('sync-settings', settings, tx)
                tx.after_commit(self.sync.cancel_queries)
                tx.after_commit(self.sync.chat.attachments.sync.cancel_pending)
                tx.connection.execute("UPDATE local_attachments SET sync_json='{}'")
                self.sync.reset(tx)
                pending.update(phase='waiting_reset_ack', generation=settings['syncGeneration'])
                self.repo.put('sync-recovery', pending, tx)
                self.repo.seal(tx)
                return
        raise HubError(code, '服务端仍冻结此设备，未执行同步重建')
