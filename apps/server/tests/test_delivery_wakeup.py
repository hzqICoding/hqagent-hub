from contextlib import contextmanager
import time
from types import SimpleNamespace

import pytest

from server.common import stamp
from server.repository import UnitOfWork


def test_enqueue_wakes_within_one_second_without_idle_transactions(env, paired, monkeypatch):
    count = 0
    original = env.service.repo.transaction

    @contextmanager
    def counted():
        nonlocal count
        count += 1
        with original() as tx:
            yield tx

    monkeypatch.setattr(env.service.repo, 'transaction', counted)
    with paired.connect():
        baseline = count
        time.sleep(0.65)
        assert count - baseline <= 1  # at most initial dispatch; no 100ms polling
        started = time.perf_counter()
        receipt = paired.send(paired.conv)
        assert paired.receive()['commandId'] == receipt['commandId']
        assert time.perf_counter() - started < 1.0
        baseline = count
        time.sleep(0.4)
        assert count - baseline <= 1


def test_delivery_notifications_only_after_commit_and_never_rollback(env, paired):
    with env.service.repo.transaction() as tx:
        owner = env.service.security.session(tx, env.alice.cookie)['owner']
    notifications = []
    env.service.connections[(owner, paired.worker)] = SimpleNamespace(wake=lambda: notifications.append('committed'))
    try:
        with pytest.raises(RuntimeError):
            with env.service.repo.transaction() as tx:
                env.service.notify(tx, owner, paired.worker)
                assert notifications == []
                raise RuntimeError('rollback')
        assert notifications == []
        with env.service.repo.transaction() as tx:
            env.service.notify(tx, owner, paired.worker)
            env.service.notify(tx, owner, paired.worker)  # coalesced per destination
            assert notifications == []
        assert notifications == ['committed']
    finally:
        del env.service.connections[(owner, paired.worker)]


def test_delivery_filters_completed_outbox_and_expiry_targets_worker(env, paired, monkeypatch):
    with env.service.repo.transaction() as tx:
        owner = env.service.security.session(tx, env.alice.cookie)['owner']
        # Poison noncandidate JSON: candidate queries must filter before decoding.
        tx.db.execute("INSERT INTO records(owner,kind,id,worker,store,parent,body,outbox_done) VALUES(?,?,?,?,?,?,?,?)",
                      (owner, 'outbox', 'done-history', paired.worker, paired.store, paired.conv, 'not-json', 1))
        tx.db.execute("INSERT INTO records(owner,kind,id,worker,store,parent,body,command_status,due_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (owner, 'command', 'finished-history', paired.worker, paired.store, paired.conv, 'not-json', 'completed', stamp(env.clock() - 1)))
        tx.db.execute("INSERT INTO records(owner,kind,id,worker,store,parent,body,command_status,due_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (owner, 'command', 'other-worker', 'other', paired.store, paired.conv, 'not-json', 'queued', stamp(env.clock() - 1)))
        env.service.expire(tx, owner, paired.worker)
        assert tx.pending_outbox(owner, paired.worker, paired.store) == []
    # The normal delivery path must not fall back to decoding historical rows.
    with paired.connect():
        assert paired.ack['commandDelivery'] == 'ready'


def test_periodic_fallback_delivers_if_notification_is_lost(env, paired, monkeypatch):
    # Production remains 5 seconds; shorten only the timer to keep this test bounded.
    monkeypatch.setattr('server.worker.FALLBACK_INTERVAL', 0.15)
    with paired.connect():
        with env.service.repo.transaction() as tx:
            owner = env.service.security.session(tx, env.alice.cookie)['owner']
        connection = env.service.connections[(owner, paired.worker)]
        monkeypatch.setattr(connection, 'wake', lambda: None)
        receipt = paired.send(paired.conv)
        assert paired.receive()['commandId'] == receipt['commandId']
