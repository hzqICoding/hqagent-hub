import json

import pytest

from adapters.history import FileHistory
from test_r3_native import fixture_history


@pytest.mark.parametrize('agent,version,readable', [
    ('claude','2.1.261',True), ('claude','2.1.284',True), ('claude','2.1.999',True),
    ('claude','2.1.251',True), ('claude','2.1.260',True), ('claude','2.1.288',True),
    ('claude','2.1.250',False), ('claude','2.2.0',True), ('claude','3.0.0',False),
    ('codex','0.153.4',True), ('codex','0.153.5',True), ('codex','0.153.999',True),
    ('codex','0.98.0',True), ('codex','0.111.0',True), ('codex','0.116.0',True),
    ('codex','0.133.0',True), ('codex','0.144.2',True), ('codex','0.144.4',True),
    ('codex','0.146.0',True), ('codex','0.147.0',True), ('codex','0.159.2',True),
    ('codex','0.159.99',True), ('codex','0.160.0',True), ('codex','0.97.9',False),
    ('codex','0.153.3',True), ('codex','0.154.0',True), ('codex','1.0.0',False),
])
def test_census_range_and_future_minor_report_actual_version(tmp_path,agent,version,readable):
    root=tmp_path/'records'
    path=fixture_history(root,tmp_path,agent,version=version)
    plugin=FileHistory(agent,root)
    source=plugin.inspect(path)
    assert source.readable is readable
    if readable:
        assert [m['text'] for m in source.messages]==['remember public context','public answer']
    else:
        assert source.reason==plugin.version_rejection(version) and not source.messages
    capability=plugin.capabilities()
    assert capability['verifiedSeries']==({'series':'2.1.251–2.1.288','minimumPatch':251}
        if agent=='claude' else {'series':'0.98.0–0.159.2','minimumPatch':0})
    assert capability['observedVersions']==[version]
    assert capability['versionPolicy']=='census-range-and-same-major-future-record-structure-v1'
    assert f'实际版本={version}' in capability['versionDiagnostics'][-1]
    assert 'remember public context' not in str(capability)
    if readable and not plugin.verified_version(version):
        assert source.reason==plugin.compatible_reason
        assert plugin.compatible_reason in capability['versionDiagnostics'][-1]


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
        target[field]={'id':'00000000-0000-4000-8000-000000000003','cwd':'relative-invalid-cwd','version':'3.0.0' if agent=='claude' else '1.0.0'}[broken]
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
