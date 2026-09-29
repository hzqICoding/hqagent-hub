import asyncio
import json

import pytest

from remote_support import System, FakeRemoteServer, until
from test_r15_worker import local_conversation, command, receive, grant
from test_r3_native import setup_native


@pytest.mark.parametrize('sequence,state', [(1,'provisional'),(2,'waiting')])
def test_ungranted_live_receipt_blocks_upgrade_even_with_drained_outbox(tmp_path,sequence,state):
    async def scenario():
        system=System(tmp_path)
        try:
            local=await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server,start=True)
                frame=command(system,'live-receipt',local.id,seq=sequence)
                await server.send(frame)
                await until(lambda: system.worker.delivery.row('live-receipt') is not None)
                await until(lambda: system.repo.get('sync-work')['phase']=='synced' and not system.repo.frames())
                assert system.worker.delivery.row('live-receipt')['state']==state
                assert not system.worker.can_upgrade()
                assert not system.adapter.started
        finally:
            await system.close()
    asyncio.run(scenario())


def test_reconnect_discards_only_superseded_staging_then_drains_real_fence(tmp_path):
    async def scenario():
        system=System(tmp_path)
        setup_native(system,tmp_path/'empty-native')
        try:
            await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server,start=True)
                await until(lambda: system.repo.get('sync-work')['phase']=='synced' and not system.repo.frames())
                await system.worker.stop()
                with system.db.transaction() as tx:
                    system.worker.sync.capture(tx)
                    old=system.repo.get('sync-work',tx)['backfillId']
                    system.repo.seal(tx)
                with system.db.transaction() as tx:
                    system.worker.sync.capture(tx)
                    current=system.repo.get('sync-work',tx)['backfillId']
                    assert current!=old
                    assert {r[0] for r in tx.connection.execute('SELECT backfill_id FROM remote_sync_items')}=={current}
                    # Recreate the pre-fix abandoned snapshot alongside the
                    # current full snapshot, without changing any Outbox bytes.
                    tx.connection.execute("INSERT INTO remote_sync_items(backfill_id,kind,resource_id,conversation_id,payload_json,revision) "
                        "SELECT ?,kind,resource_id,conversation_id,payload_json,revision FROM remote_sync_items LIMIT 1",(old,))
                    system.repo.seal(tx)
                original=system.repo.frames()
                system.worker.sync.prepare()
                assert system.repo.frames()==original
                with system.db.locked_connection() as db:
                    assert {r[0] for r in db.execute('SELECT backfill_id FROM remote_sync_items')}=={current}
                assert not system.worker.can_upgrade()
                # Current staging and reliable events still block until the
                # real peer has consumed them and ACKed the complete marker.
                server.auto_ack=False
                await system.worker.start()
                await until(lambda: bool(system.repo.frames()))
                assert not system.worker.can_upgrade()
                server.auto_ack=True
                await system.worker.stop()
                await system.worker.start()
                await until(lambda: system.repo.get('sync-work')['phase']=='synced' and not system.repo.frames())
                assert system.worker.can_upgrade()
                assert not server.errors
        finally:
            await system.close()
    asyncio.run(scenario())


def test_terminal_run_with_uncertain_effects_reports_unknown_instead_of_staying_accepted(tmp_path,monkeypatch):
    async def scenario():
        system=System(tmp_path,hold=True)
        try:
            local=await local_conversation(system)
            async with FakeRemoteServer(revision=2) as server:
                await system.pair(server,start=True)
                frame=command(system,'terminal-unknown',local.id)
                receipt=await receive(server,frame)
                await server.send(grant(frame,receipt))
                await until(lambda: bool(system.adapter.started))
                bridge=system.worker.delivery
                monkeypatch.setattr(bridge,'_observation',lambda _record:{'recoveryRequired':True,
                    'unresolvedCancellation':{'cancellations':[{'outcome':'not_found','orphanProcessIds':[424242]}]}})
                assert not system.worker.can_upgrade()
                system.adapter.release.set()
                await until(lambda: bridge.row(frame['commandId'])['state']=='unconfirmed')
                event=json.loads(bridge.row(frame['commandId'])['result_json'])
                assert event['type']=='command.control_result'
                assert event['controlResult']['outcome']=='unconfirmed'
                assert event['controlResult']['executionMayStillBeRunning'] is True
                assert event['controlResult']['orphanProcessIds']==[424242]
                await until(lambda: system.repo.get('sync-work')['phase']=='synced' and not system.repo.frames())
                assert system.worker.can_upgrade()
                assert not any(f['type']=='command.completed' and f.get('commandId')==frame['commandId'] for f in server.frames)
        finally:
            await system.close()
    asyncio.run(scenario())
