"""Device administration, separate from Worker observations and execution facts."""
from .common import Fault, MAX_SEQ, digest, require


class DeviceManagement:
    def devices(self, tx, owner, cursor, limit, filters, audience='cookie'):
        scope = 'devices-v3:' + digest([audience, filters])
        try:
            start = self.position(tx, owner, scope, cursor) if cursor else 0
        except Fault as exc:
            if exc.code != 'REMOTE_CURSOR_INVALID':
                raise
            # Only an authenticated old cursor earns upgrade-expired semantics.
            self.position(tx, owner, 'page:device:', cursor)
            raise Fault('REMOTE_CURSOR_EXPIRED') from None
        rows = tx.ordered_records(owner, 'device', start)
        selected = []
        for ordinal, device in rows:
            if device.get('_deleted') or (device['status'] == 'revoked' and not filters['includeRevoked']):
                continue
            view = self.view(owner, 'device', device)
            if filters['remoteAccess'] is not None and view['remoteAccess'] != filters['remoteAccess']:
                continue
            if filters['online'] is not None and view['online'] != filters['online']:
                continue
            selected.append((ordinal, view))
            if len(selected) > limit:
                break
        result = dict(items=[v for _, v in selected[:limit]], hasMore=len(selected) > limit)
        if result['hasMore']:
            result['nextCursor'] = self.cursor(tx, owner, scope, selected[limit-1][0])
        return result

    def patch_device(self, tx, owner, worker, body):
        device = self.get(tx, owner, 'device', worker)
        require(device['status'] != 'revoked', 'REMOTE_DEVICE_REVOKED')
        require(bool(set(body) & {'remoteAccess', 'displayName'}))
        version = device.get('version', 1)
        if body['expectedVersion'] != version:
            raise Fault('CONFLICT', detail=dict(fields=['expectedVersion'], currentVersion=version))
        access = body.get('remoteAccess', device.get('remoteAccess', 'enabled'))
        alias = body.get('displayName', device.get('displayName', '')).strip()
        if access != device.get('remoteAccess', 'enabled') or alias != device.get('displayName', ''):
            require(version < MAX_SEQ, 'CONFLICT')
            if access != device.get('remoteAccess', 'enabled'):
                if access == 'suspended':
                    device['suspendedAt'] = self.now()
                    # The repository transaction also encloses received/grant.
                    # Existing safe-action windows are intentionally closed too.
                    for command in tx.ungranted_windows(owner, worker):
                        self.delivery_expired(tx, owner, command, 'REMOTE_DEVICE_SUSPENDED')
                else:
                    device.pop('suspendedAt', None)
            device.update(remoteAccess=access, version=version + 1)
            device.pop('displayName', None)
            if alias:
                device['displayName'] = alias
            self.save(tx, owner, 'device', worker, device, management=True)
            self.notify(tx, owner, worker)
        return self.view(owner, 'device', device)

    def delete_device(self, tx, owner, worker):
        self.get(tx, owner, 'device', worker)  # No response replay after deletion.
        self.revoke(tx, owner, worker)
        deleted = self.now()
        tx.delete_device_content(owner, worker, deleted)
        self.notify(tx, owner, worker)
        return dict(workerId=worker, deletedAt=deleted, executionMayStillBeRunning=True)
