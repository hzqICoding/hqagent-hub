import asyncio
import json
import os
import time
from types import SimpleNamespace

import pytest
from protocol.generated.python import NativeMessagePage, LocalConversationView

from adapters.history import FileHistory
from remote_support import System
from test_r3_native import fixture_history, setup_native


@pytest.mark.parametrize('agent', ['claude','codex'])
def test_long_history_keeps_canonical_workspace_across_cwd_and_patch_changes(tmp_path,agent):
    async def scenario():
        system=System(tmp_path)
        try:
            root=tmp_path/'records'
            path=fixture_history(root,tmp_path,agent,version='2.1.261' if agent=='claude' else '0.153.4')
            changed=tmp_path/'later-cwd'; changed.mkdir()
            rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
            new_version='2.1.284' if agent=='claude' else '0.153.5'
            long_text='long public text '+('汉😀'*18000)+'\nAPI_KEY=HIDDEN_CREDENTIAL\n<thinking>PRIVATE_THOUGHT</thinking>'
            if agent=='claude':
                rows[1].update(cwd=str(changed),version=new_version)
                rows[1]['message']['content'][0]['text']=long_text
            else:
                rows.insert(2,{'type':'turn_context','payload':{'cwd':str(changed),'cli_version':new_version}})
                rows[3]['payload']['content'][0]['text']=long_text
            path.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
            os.utime(path,(time.time()-60,time.time()-60))
            native=setup_native(system,root,agent)
            plugin=native.plugins[0]
            source=plugin.inspect(path)
            assert source.readable and source.cwd==tmp_path.resolve()
            assert new_version in plugin.capabilities()['observedVersions']
            assert plugin.list([SimpleNamespace(id='changed-only',path=str(changed))])==[]
            assert plugin.list([SimpleNamespace(id='canonical',path=str(tmp_path))])[0][1]=='canonical'
            item=(await native.listing()).items[0]
            assert item.workspace_id=='workspace'
            response=await system.local.get(f'/api/v2/native-sessions/{item.native_session_id}/messages?limit=100')
            assert response.status_code==200,response.text
            page=NativeMessagePage.model_validate(response.json()['data'])
            assert len(page.items)>2
            assert ''.join(part.text for part in page.items if part.role=='assistant')==source.messages[1]['text']
            assert 'HIDDEN_CREDENTIAL' not in response.text and 'PRIVATE_THOUGHT' not in response.text
            imported=await system.local.post(f'/api/v2/native-sessions/{item.native_session_id}/imports',json={
                'terminalClosedConfirmed':True,'expectedIndexVersion':item.index_version,'sourceRevision':item.source_revision},
                headers={'Origin':'http://127.0.0.1','Idempotency-Key':'mixed-history'})
            assert imported.status_code==201,imported.text
            view=LocalConversationView.model_validate(imported.json()['data'])
            assert view.workspace_id=='workspace'
            binding=native.row(view.id,conversation=True)
            assert json.loads(binding['source_json'])['cwd']==str(tmp_path.resolve())
            stored=system.chat.repository.messages(view.id)
            assert stored[1].text==source.messages[1]['text']
            assert not system.adapter.started and not system.adapter.resumed
        finally:
            await system.close()
    asyncio.run(scenario())
