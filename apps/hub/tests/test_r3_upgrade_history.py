import asyncio
import json

from remote_support import System, until
from runtime.remote.wire import canonical
from test_r15_joint_server import RealPair, server_source, all_server_codecs
from test_r3_native import setup_native


async def phone_submit(pair, key):
    local = pair.legacy_ids[0]
    await until(lambda: pair.cloud_conversation(local) is not None and not pair.cloud_conversation(local).get('_busy'))
    public = pair.cloud_conversation(local)['conversationId']
    response = await pair.browser.post('/conversations/'+public+'/messages', json={
        'clientMessageId':key, 'text':'synthetic upgrade input', 'sessionMode':'new'}, headers={'Idempotency-Key':key})
    assert response.status_code == 202, response.text
    return response.json()['data']['commandId']


async def drained(pair):
    await until(lambda: pair.system.repo.get('sync-work')['phase']=='synced' and not pair.system.repo.frames())


def test_persisted_unknown_and_finished_accepted_automatically_upgrade_real_server(tmp_path, monkeypatch, all_server_codecs):
    async def scenario():
        from server import wire
        monkeypatch.setattr(wire,'CODECS',{r:c for r,c in all_server_codecs.items() if r<=2})
        async with RealPair(tmp_path,revision=2) as pair:
            await drained(pair)
            submit=await phone_submit(pair,'historical-submit')
            delivery=pair.system.worker.delivery
            await until(lambda: delivery.row(submit) and delivery.row(submit)['state']=='completed')
            completed=json.loads(delivery.row(submit)['result_json'])
            run=pair.system.chat.repository.run_record(delivery.row(submit)['run_id'])
            assert run['status']=='succeeded'
            await drained(pair)
            with pair.service.repo.transaction() as tx:
                public_run=tx.get(pair.owner,'command',submit)['resultRef']['runId']
            original_observation=pair.system.tasks.control_observation
            monkeypatch.setattr(pair.system.tasks,'control_observation',lambda _id:{
                'evidenceAvailable':True,'recoveryRequired':True,
                'unresolvedCancellation':{'cancellations':[{'outcome':'not_found','orphanProcessIds':[424242]}]}})
            unknown={}
            for index in range(2):
                response=await pair.browser.post('/runs/'+public_run+'/commands',json={'action':'cancel'},
                    headers={'Idempotency-Key':f'unknown-{index}'})
                assert response.status_code==202,response.text
                identifier=response.json()['data']['commandId']
                await until(lambda: delivery.row(identifier) and delivery.row(identifier)['state']=='unconfirmed')
                unknown[identifier]=delivery.row(identifier)['result_json']
            monkeypatch.setattr(pair.system.tasks,'control_observation',original_observation)
            await drained(pair)
            await pair.system.worker.stop()
            accepted=next(f for f in pair.sent if f['type']=='command.accepted' and f['commandId']==submit)
            # Persist the old split-ledger shape: final journal/Inbox but stale
            # accepted delivery cache, after its final event was ACKed/pruned.
            with pair.system.db.transaction() as tx:
                tx.connection.execute("UPDATE remote2_delivery SET state='accepted',result_json=? WHERE command_id=?",(canonical(accepted),submit))
                tx.connection.execute("UPDATE remote_inbox SET receipt_json=? WHERE command_id=?",(canonical(accepted),submit))
                pair.system.repo.seal(tx)
            await pair.system.close()
            pair.system=System(tmp_path)
            setup_native(pair.system,tmp_path/'empty-native')
            pair.system.worker.connector=pair.connect
            await pair.system.chat.start()
            await pair.system.worker.start()
            await until(lambda: pair.system.worker.delivery.row(submit)['state']=='completed')
            restored=pair.system.worker.delivery.row(submit)
            assert json.loads(restored['result_json'])==completed
            assert pair.system.repo.inbox(submit)['status']=='completed'
            await drained(pair)
            before=len(pair.sent)
            # No restart, re-pair or force-switch: the old online device must
            # probe again after the server gains R3.
            monkeypatch.setattr(wire,'CODECS',all_server_codecs)
            pair.system.worker.next_revision2_probe=0
            await until(lambda: pair.system.repo.get('identity')['wireRevision']==3,timeout=12)
            await drained(pair)
            assert pair.system.repo.get('identity')['upgradeFence']['server'] is not None
            assert not pair.system.adapter.started and not pair.system.adapter.resumed
            assert not any(f.get('commandId') in {submit,*unknown} for f in pair.sent[before:])
            for identifier,result in unknown.items():
                row=pair.system.worker.delivery.row(identifier)
                assert row['state']=='unconfirmed' and row['result_json']==result
                with pair.service.repo.transaction() as tx:
                    command=tx.get(pair.owner,'command',identifier)
                    assert command['status']=='accepted' and command['controlResult']['outcome']=='unconfirmed'
                    assert command['controlResult']['orphanProcessIds']==[424242]
            retry=await pair.browser.post('/runs/'+public_run+'/commands',json={'action':'retry'},
                headers={'Idempotency-Key':'must-still-reconcile'})
            assert retry.status_code==202,retry.text
            retry_id=retry.json()['data']['commandId']
            await until(lambda: pair.system.worker.delivery.row(retry_id) and pair.system.worker.delivery.row(retry_id)['state']=='unconfirmed')
            assert not pair.system.adapter.started and not pair.system.adapter.resumed
    asyncio.run(scenario())


def test_actual_granted_execution_blocks_upgrade_until_its_final_result(tmp_path,monkeypatch,all_server_codecs):
    async def scenario():
        from server import wire
        monkeypatch.setattr(wire,'CODECS',{r:c for r,c in all_server_codecs.items() if r<=2})
        async with RealPair(tmp_path,revision=2) as pair:
            await drained(pair)
            pair.system.adapter.release.clear()
            command=await phone_submit(pair,'in-flight')
            delivery=pair.system.worker.delivery
            await until(lambda: bool(pair.system.adapter.started) and delivery.row(command)['state']=='accepted')
            await drained(pair)
            monkeypatch.setattr(wire,'CODECS',all_server_codecs)
            pair.system.worker.next_revision2_probe=0
            assert pair.system.worker.can_upgrade() is False
            await asyncio.sleep(.5)
            assert pair.system.repo.get('identity')['wireRevision']==2
            pair.system.adapter.release.set()
            await until(lambda: delivery.row(command)['state']=='completed')
            await until(lambda: pair.system.repo.get('identity')['wireRevision']==3,timeout=12)
            final=json.loads(delivery.row(command)['result_json'])
            assert final['wireRevision']==2 and final['type']=='command.completed'
            assert len(pair.system.adapter.started)==1
    asyncio.run(scenario())
