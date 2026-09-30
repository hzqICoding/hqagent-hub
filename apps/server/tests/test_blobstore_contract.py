"""Backend-neutral acceptance suite. Add a factory parameter for each backend."""
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor

import pytest

from server.blobstore import BLOCK, LocalBlobStore, object_key
from server.common import Fault


@pytest.fixture(params=[LocalBlobStore], ids=['local'])
def backend(request, tmp_path):
    factory = request.param
    return factory, tmp_path / 'blobs', factory(tmp_path / 'blobs')


def write(store, data):
    hash_ = hashlib.sha256(data).hexdigest()
    stage = store.stage_write(io.BytesIO(data), len(data), hash_, expectedBytes=len(data))
    assert stage.size == len(data) and stage.sha256 == hash_ and stage.closed
    return stage, hash_


def test_write_read_size_and_delete(backend):
    _, _, store = backend
    data = b'contract content' * 10000
    stage, hash_ = write(store, data)
    assert not store.exists(hash_)
    assert store.commit(stage, hash_) == hash_
    assert store.commit(stage, hash_) == hash_
    assert list(store.iter_blobs()) == [hash_]
    assert store.size(hash_) == len(data)
    with store.open_read(hash_) as reader:
        assert reader.read() == data
    store.abort(stage)  # Abort of a consumed stage cannot delete the committed blob.
    assert store.exists(hash_)
    store.delete(hash_)
    store.delete(hash_)
    assert not store.exists(hash_) and list(store.iter_blobs()) == []
    with pytest.raises(FileNotFoundError):
        store.open_read(hash_)


@pytest.mark.parametrize('failure', ['hash', 'short', 'long', 'limit'])
def test_failed_stage_rolls_back_and_cannot_commit(backend, failure):
    _, _, store = backend
    data = b'abcdef'
    hash_ = hashlib.sha256(data).hexdigest()
    expected = '0' * 64 if failure == 'hash' else hash_
    expected_size = 7 if failure == 'short' else 5 if failure == 'long' else None
    limit = 5 if failure == 'limit' else 7
    stage = store.stage_write(None, limit, expected, expectedBytes=expected_size)
    with pytest.raises(Fault):
        stage.write(data)
        stage.finish()
    assert stage.closed
    store.abort(stage)
    store.purge_staging()
    with pytest.raises(Fault):
        store.commit(stage, expected)
    assert not store.exists(expected) and list(store.iter_blobs()) == []


def test_concurrent_identical_commit_and_losing_abort(backend):
    _, _, store = backend
    data = b'one physical object'
    stages = [write(store, data) for _ in range(4)]
    hash_ = stages[0][1]
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(store.commit, stage, hash_) for stage, _ in stages[:3]]
        store.abort(stages[3][0])
        assert [future.result() for future in futures] == [hash_] * 3
    assert list(store.iter_blobs()) == [hash_]
    with store.open_read(hash_) as reader:
        assert reader.read() == data


def test_delete_closes_reader_handles(backend):
    _, _, store = backend
    stage, hash_ = write(store, b'read lease')
    store.commit(stage, hash_)
    readers = [store.open_read(hash_), store.open_read(hash_)]
    assert readers[0].read(1) == b'r'
    store.delete(hash_)
    assert all(reader.closed for reader in readers)
    assert not store.exists(hash_)


def test_materialization_cleanup_and_live_stage_protection(backend):
    _, _, store = backend
    stage, hash_ = write(store, b'materialized')
    with store.materialize(stage) as source:
        assert source.read_bytes() == b'materialized'
        store.purge_staging()
        assert source.is_file()
    store.commit(stage, hash_)
    with pytest.raises(RuntimeError):
        with store.materialize(hash_) as temporary:
            assert temporary.read_bytes() == b'materialized'
            store.purge_staging()
            assert temporary.is_file()
            raise RuntimeError('consumer stopped')
    assert not temporary.exists()
    assert store.exists(hash_)


def test_crash_recovery_purges_staging_not_committed_data(backend):
    factory, root, store = backend
    stage, hash_ = write(store, b'committed')
    store.commit(stage, hash_)
    abandoned, _ = write(store, b'abandoned verified staging')
    # A completed but uncommitted stage owns no open writer; abandoning this
    # backend instance models a process exit without a cleanup callback.
    with store.materialize(abandoned) as abandoned_path:
        assert abandoned_path.exists()
    recovered = factory(root)
    recovered.purge_staging()
    assert not abandoned_path.exists()
    assert recovered.exists(hash_)
    with recovered.open_read(hash_) as reader:
        assert reader.read() == b'committed'


def test_stage_blocks_are_bounded(backend):
    _, _, store = backend
    stage = store.stage_write(None, BLOCK + 1, '0' * 64)
    with pytest.raises(Fault, match='ATTACHMENT_TOO_LARGE'):
        stage.write(b'x' * (BLOCK + 1))
    assert stage.closed


def test_content_key_is_independent_of_identity():
    hash_ = 'abcdef' + '0' * 58
    assert object_key(hash_) == f'cas/ab/cd/{hash_}'
    for invalid in ('../file', 'a' * 63, 'A' * 64):
        with pytest.raises(Fault):
            object_key(invalid)
