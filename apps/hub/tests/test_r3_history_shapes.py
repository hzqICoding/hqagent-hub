import asyncio
import json
from collections import Counter

import pytest

from adapters.history import FileHistory, public_text
from remote_support import System
from test_r3_native import fixture_history, setup_native


def write_rows(path,rows):
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')


def test_synthetic_long_transcript_matches_structural_census_and_filters_private_metadata(tmp_path):
    root=tmp_path/'records'; path=fixture_history(root,tmp_path,'claude')
    template=json.loads(path.read_text(encoding='utf-8').splitlines()[0])
    counts={'user':2118,'assistant':3418,'attachment':1999,'system':236,'mode':572,
        'permission-mode':572,'bridge-session':576,'atis-latch':572,'ai-title':572,
        'last-prompt':573,'file-history-snapshot':137,'file-history-delta':149,'queue-operation':232,'cost-state':4}
    rows=[]; parent=None
    for kind,count in counts.items():
        for i in range(count):
            identifier=f'record-{len(rows)}'
            row={'type':kind,'sessionId':template['sessionId'],'uuid':identifier,'parentUuid':parent}
            if kind in {'user','assistant'}:
                row.update(cwd=str(tmp_path),version=('2.1.261','2.1.281','2.1.283')[i%3])
                if kind=='user':
                    if i<220:content='public user text'
                    elif i<2097:content=[{'type':'tool_result','tool_use_id':'call','content':'TOOL_OUTPUT_PRIVATE'}]
                    else:
                        content=[{'type':'text','text':'public user text'}]
                        if i<2103:content.append({'type':'image','source':{'data':'IMAGE_BYTES_PRIVATE'}})
                else:
                    if i<1042:content=[{'type':'thinking','thinking':'PRIVATE_THOUGHT'}]
                    elif i<2919:content=[{'type':'tool_use','id':'call','name':'Read','input':{'secret':'TOOL_ARGS_PRIVATE'}}]
                    else:content=[{'type':'text','text':'public answer'}]
                row['message']={'role':kind,'content':content}
            elif kind=='bridge-session':
                row.update(accountUuid='ACCOUNT_PRIVATE_UUID',organizationUuid='ORGANIZATION_PRIVATE_UUID')
            elif kind=='ai-title':
                row['aiTitle']='Preferred sk-TITLESECRET '+('标题😀'*60)
            else:
                row['content']='AUXILIARY_PRIVATE_BODY'
            rows.append(row); parent=identifier
    assert len(rows)==11730 and Counter(r['type'] for r in rows)==counts
    versions=['2.1.261']*3129+['2.1.281']*425+['2.1.283']*4217
    for index,row in enumerate(rows):
        if index<len(versions):row['version']=versions[index]
        else:row.pop('version',None)
    assert Counter(r.get('version') for r in rows)=={None:3959,'2.1.261':3129,'2.1.281':425,'2.1.283':4217}
    # A valid shared parent is not required to be the immediately prior message.
    rows[2120]['parentUuid']=rows[2118]['uuid']
    rows[2].update(isMeta=True,message={'role':'user','content':'INTERNAL_META_PRIVATE'})
    rows[3].update(isVisibleInTranscriptOnly=True,message={'role':'user','content':'TRANSCRIPT_ONLY_PRIVATE'})
    rows[4].update(isCompactSummary=True,isMeta=True,message={'role':'user','content':'COMPACT_BODY_PRIVATE'})
    # Sidechain identity and bodies cannot contaminate the main stream.
    rows.append({**template,'uuid':'side','parentUuid':parent,'sessionId':'other-sidechain',
                 'isSidechain':True,'message':{'role':'user','content':'SIDECHAIN_PRIVATE'}})
    rows.append({'type':'future-private-record','uuid':'future','parentUuid':'unknown-private-parent',
                 'message':{'role':'assistant','content':'UNKNOWN_RECORD_PRIVATE'}})
    rows.append({**template,'uuid':'placeholder','parentUuid':parent,'message':{'role':'user','content':[
        {'type':'future-private-block','text':'UNKNOWN_BLOCK_PRIVATE'}]}})
    rows.append({**template,'type':'system','uuid':'system-message','parentUuid':'placeholder',
                 'message':{'role':'system','content':'SYSTEM_INSTRUCTIONS_PRIVATE'}})
    write_rows(path,rows)
    plugin=FileHistory('claude',root)
    source=plugin.inspect(path)
    assert source.readable,source.reason
    text=json.dumps(source.messages,ensure_ascii=False)
    assert '[图片]' in text and '[不支持的内容块]' in text and '对话已压缩' in text and '[系统消息]' in text
    assert any(m['role']=='tool_summary' and '历史返回记录' in m['text'] for m in source.messages)
    assert all(token not in text for token in ('PRIVATE','TITLESECRET','ACCOUNT_PRIVATE_UUID','ORGANIZATION_PRIVATE_UUID'))
    assert source.title==public_text(next(r['aiTitle'] for r in reversed(rows) if r['type']=='ai-title'))[:120] and len(source.title)==120
    assert source.structure_counts['unknownRecords']==1
    assert source.structure_counts['unknownBlocks']==1 and source.structure_counts['sidechainRecords']==1
    assert source.structure_counts['internalMessages']==2
    assert 'PRIVATE' not in json.dumps(plugin.capabilities())


@pytest.mark.parametrize('boundary',['summary','system'])
def test_explicit_compact_boundary_allows_discarded_prefix_but_not_a_later_broken_link(tmp_path,boundary):
    root=tmp_path/'records'; path=fixture_history(root,tmp_path,'claude')
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    marker={**rows[0],'uuid':'compact','parentUuid':'discarded-prefix'}
    if boundary=='summary':marker['isCompactSummary']=True
    else:
        marker.update(type='system',subtype='compact_boundary',compactMetadata={})
        marker.pop('message')
    rows[1]['parentUuid']='compact'
    write_rows(path,[marker,rows[1]])
    plugin=FileHistory('claude',root)
    assert plugin.inspect(path).readable
    assert plugin.inspect(path).messages[0]['text']=='对话已压缩'
    rows[1]['parentUuid']='genuinely-missing'
    write_rows(path,[marker,rows[1]])
    assert not plugin.inspect(path).readable
    assert 'parentUuid' in plugin.inspect(path).reason


@pytest.mark.parametrize('agent',['claude','codex'])
@pytest.mark.parametrize('damage',['missing_message','role'])
def test_missing_message_or_illegal_role_remains_unsupported(tmp_path,agent,damage):
    root=tmp_path/'records'; path=fixture_history(root,tmp_path,agent)
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    row=rows[0] if agent=='claude' else rows[1]
    if damage=='missing_message':
        if agent=='claude':row.pop('message')
        else:row['payload']={'type':'message'}
    else:(row['message'] if agent=='claude' else row['payload'])['role']='illegal'
    write_rows(path,rows)
    assert not FileHistory(agent,root).inspect(path).readable


def test_event_and_item_extensions_are_ignored_without_exposing_payloads(tmp_path):
    root=tmp_path/'records'; path=fixture_history(root,tmp_path)
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    rows.extend([
        {'type':'future_record','payload':'UNKNOWN_RECORD_PRIVATE'},
        {'type':'event_msg','payload':{'type':'future_event','message':'UNKNOWN_EVENT_PRIVATE'}},
        {'type':'response_item','payload':{'type':'future_item','text':'UNKNOWN_ITEM_PRIVATE'}},
        {'type':'compacted','payload':{'message':'COMPACT_BODY_PRIVATE'}},
        {'type':'response_item','payload':{'type':'message','role':'user','content':[
            {'type':'input_image','data':'IMAGE_BYTES_PRIVATE'},{'type':'future_block','text':'UNKNOWN_BLOCK_PRIVATE'}]}}
    ])
    write_rows(path,rows)
    source=FileHistory('codex',root).inspect(path)
    assert source.readable,source.reason
    assert 'PRIVATE' not in json.dumps(source.messages)
    assert '[图片][不支持的内容块]' in str(source.messages)
    assert '对话已压缩' in str(source.messages)
    assert all(source.structure_counts[k]==1 for k in ('unknownRecords','unknownItems','unknownEvents','unknownBlocks'))


def test_preferred_title_is_sanitized_in_local_index_without_bridge_metadata(tmp_path):
    async def scenario():
        system=System(tmp_path)
        try:
            root=tmp_path/'records'; path=fixture_history(root,tmp_path,'claude')
            rows=[json.loads(line) for line in path.read_text().splitlines()]
            rows.extend([{'type':'bridge-session','accountUuid':'ACCOUNT_PRIVATE_UUID','organizationUuid':'ORG_PRIVATE_UUID'},
                {'type':'ai-title','sessionId':rows[0]['sessionId'],'aiTitle':'Preferred sk-TITLESECRET '+('界'*140)}])
            write_rows(path,rows)
            setup_native(system,root,'claude')
            await system.worker.native.scan()
            response=await system.local.get('/api/v2/native-sessions')
            assert response.status_code==200,response.text
            assert response.json()['data']['items'][0]['title']==public_text(rows[-1]['aiTitle'])[:120]
            assert all(secret not in response.text for secret in ('TITLESECRET','ACCOUNT_PRIVATE_UUID','ORG_PRIVATE_UUID'))
            with system.db.locked_connection() as db:
                persisted=''.join(r[0] for r in db.execute('SELECT index_json FROM native_sources'))
            assert 'PRIVATE_UUID' not in persisted
        finally:await system.close()
    asyncio.run(scenario())
