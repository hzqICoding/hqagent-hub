from dataclasses import replace
from unittest.mock import Mock

import pytest

from server.blobstore import BACKENDS, LocalBlobStore, create_blob_store
from server.config import Settings
from test_attachments import env, attachment_worker, upload


def test_backend_configuration_and_factory(tmp_path, monkeypatch):
    monkeypatch.setenv('HQREMOTE_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('HQREMOTE_BLOB_BACKEND', raising=False)
    assert Settings.from_env().blob_backend == 'local'
    monkeypatch.setenv('HQREMOTE_BLOB_BACKEND', 'unknown')
    with pytest.raises(ValueError, match='Unknown blob backend'):
        Settings.from_env()
    with pytest.raises(ValueError, match='Unknown blob backend'):
        Settings(tmp_path / 'database', b'x' * 32, blob_backend='unknown')


def test_business_uses_only_blobstore_interface(env, attachment_worker, monkeypatch):
    """An adapter intentionally hiding LocalBlobStore diagnostics detects leaks."""
    from server.attachments import Attachments

    class OpaqueBackend:
        def __init__(self, root):
            self._backend = LocalBlobStore(root)

        def __getattr__(self, name):
            if name not in {'stage_write', 'commit', 'open_read', 'delete', 'exists',
                            'size', 'abort', 'iter_blobs', 'purge_staging', 'materialize'}:
                raise AssertionError('Business attempted a backend-specific operation')
            return getattr(self._backend, name)

    monkeypatch.setitem(BACKENDS, 'opaque-test', OpaqueBackend)
    env.service.settings = replace(env.settings, blob_backend='opaque-test')
    env.service.attachments = Attachments(env.service)
    result = upload(env, attachment_worker.conv)
    assert result.status_code == 201
    identifier = result.json()['data']['attachment']['attachmentId']
    from test_attachments import content
    assert content(env, identifier).content == b'hello file'
    assert env.alice.request('DELETE', '/attachments/' + identifier).status_code == 200
    import io
    from PIL import Image
    image = io.BytesIO()
    Image.new('RGB', (10, 10), 'blue').save(image, format='PNG')
    result = upload(env, attachment_worker.conv, image.getvalue(), 'preview.png')
    assert result.status_code == 201
    assert result.json()['data']['attachment']['thumbnailStatus'] == 'ready'
    env.clock.advance(3600)
    env.service.attachments.maintain()


def test_maintenance_does_not_scan_every_five_seconds(env, attachment_worker, monkeypatch):
    from server.repository import UnitOfWork
    attachments = env.service.attachments
    original = UnitOfWork.due_attachments
    calls = []

    def tracked(tx, now):
        calls.append(now)
        return original(tx, now)

    monkeypatch.setattr(UnitOfWork, 'due_attachments', tracked)
    scan = Mock(wraps=attachments.store.iter_blobs)
    purge = Mock(wraps=attachments.store.purge_staging)
    monkeypatch.setattr(attachments.store, 'iter_blobs', scan)
    monkeypatch.setattr(attachments.store, 'purge_staging', purge)
    for _ in range(11):
        env.clock.advance(5)
        attachments.maintain()
    assert calls == [] and scan.call_count == purge.call_count == 0
    env.clock.advance(5)
    attachments.maintain()
    assert len(calls) == 1 and scan.call_count == purge.call_count == 0
    env.clock.advance(3540)
    attachments.maintain()
    assert len(calls) == 2 and scan.call_count == purge.call_count == 1


def test_flat_layout_remains_readable_and_new_writes_are_layered(tmp_path):
    import hashlib
    import io
    store = LocalBlobStore(tmp_path)
    data = b'legacy'
    hash_ = hashlib.sha256(data).hexdigest()
    (tmp_path / 'cas' / hash_).write_bytes(data)
    assert store.exists(hash_) and store.size(hash_) == len(data)
    with store.open_read(hash_) as reader:
        assert reader.read() == data
    stage = store.stage_write(io.BytesIO(data), len(data), hash_)
    store.commit(stage, hash_)
    assert (tmp_path / 'cas' / hash_[:2] / hash_[2:4] / hash_).is_file()
    assert list(store.iter_blobs()) == [hash_]
    store.delete(hash_)
    assert not store.exists(hash_)


def test_schema_four_migration_and_expiry_query_excludes_attached(tmp_path):
    import sqlite3
    from server.repository import MIGRATIONS, Repository
    from server.common import canonical, stamp

    path = tmp_path / 'old.sqlite3'
    now = 1800000000
    with sqlite3.connect(path) as connection:
        for revision in range(1, 5):
            connection.executescript(MIGRATIONS[revision])
        connection.execute('PRAGMA user_version=4')
        for identifier, state, expires in [('old', 'uploaded', now),
                                           ('future', 'uploaded', now + 1),
                                           ('history', 'attached', now - 1)]:
            body = dict(attachmentId=identifier, state=state, expiresAt=stamp(expires))
            connection.execute(
                'INSERT INTO records(owner,kind,id,worker,store,parent,body) VALUES(?,?,?,?,?,?,?)',
                ('owner', 'attachment', identifier, 'worker', 'store', 'conv', canonical(body)))
    repository = Repository(path)
    try:
        with repository.transaction() as tx:
            assert tx.db.execute('PRAGMA user_version').fetchone()[0] == 5
            assert [value['attachmentId'] for _, value in tx.due_attachments(now)] == ['old']
            assert tx.db.execute("SELECT attachment_due FROM records WHERE id='history'").fetchone()[0] is None
    finally:
        repository.close()
