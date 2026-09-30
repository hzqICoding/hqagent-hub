import json

import pytest

from adapters.history import FileHistory
from test_r3_native import fixture_history


@pytest.mark.parametrize('agent,version,readable', [
    ('claude','2.1.261',True), ('claude','2.1.284',True), ('claude','2.1.999',True),
    ('claude','2.1.260',False), ('claude','2.2.0',False), ('claude','3.0.0',False),
    ('codex','0.153.4',True), ('codex','0.153.5',True), ('codex','0.153.999',True),
    ('codex','0.153.3',False), ('codex','0.154.0',False), ('codex','1.0.0',False),
])
def test_verified_series_uses_minimum_patch_and_reports_actual_version(tmp_path,agent,version,readable):
    root=tmp_path/'records'
    path=fixture_history(root,tmp_path,agent,version=version)
    plugin=FileHistory(agent,root)
    source=plugin.inspect(path)
    assert source.readable is readable
    if readable:
        assert [m['text'] for m in source.messages]==['remember public context','public answer']
    else:
        assert source.reason=='该 CLI 版本尚未验证' and not source.messages
    capability=plugin.capabilities()
    assert capability['verifiedSeries']==({'series':'2.1.x','minimumPatch':261} if agent=='claude' else {'series':'0.153.x','minimumPatch':4})
    assert capability['observedVersions']==[version]
    assert capability['versionPolicy']=='verified-series-minimum-patch-and-record-structure'
    assert f'实际版本={version}' in capability['versionDiagnostics'][-1]
    assert 'remember public context' not in str(capability)


@pytest.mark.parametrize('agent', ['claude','codex'])
@pytest.mark.parametrize('broken', ['id','cwd','version','block','json'])
def test_new_patch_still_requires_consistent_record_identity_and_shapes(tmp_path,agent,broken):
    root=tmp_path/'records'
    path=fixture_history(root,tmp_path,agent,version='2.1.284' if agent=='claude' else '0.153.5')
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    if broken in {'id','cwd','version'}:
        if agent=='codex':
            extra=json.loads(json.dumps(rows[0])); rows.append(extra)
            target=extra['payload']; field={'id':'id','cwd':'cwd','version':'cli_version'}[broken]
        else:
            target=rows[1]; field={'id':'sessionId','cwd':'cwd','version':'version'}[broken]
        target[field]={'id':'00000000-0000-4000-8000-000000000003','cwd':'relative-invalid-cwd','version':'2.2.0' if agent=='claude' else '0.154.0'}[broken]
    if broken=='block':
        target=rows[1]['payload'] if agent=='codex' else rows[1]['message']
        target['content']=[{'type':'text','text':{'invalid':'PRIVATE_BROKEN_BODY'}}]
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows)+('broken-json\n' if broken=='json' else ''),encoding='utf-8')
    source=FileHistory(agent,root).inspect(path)
    assert not source.readable and not source.messages
    assert source.reason and source.reason!='该 CLI 版本尚未验证'
    assert 'PRIVATE_BROKEN_BODY' not in source.reason
    if broken in {'id','cwd','version'}:
        assert field in source.reason
