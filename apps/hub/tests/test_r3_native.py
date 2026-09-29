import asyncio
import json
import os
import time
from pathlib import Path

import pytest
from protocol.generated.python import RemoteNativeImportInput, SendLocalMessageInput
from adapters.history import FileHistory
from core.errors import HubError
from remote_support import System, until
from storage.local_chat import now


def fixture_history(root, workspace, agent="codex", *, version=None, source="cli", text="remember public context", identifier="00000000-0000-4000-8000-000000000001"):
    root.mkdir(parents=True, exist_ok=True)
    path = root / "synthetic.jsonl"
    if agent == "codex":
        records = [{"type": "session_meta", "payload": {"id": identifier, "cwd": str(workspace),
            "timestamp": now(), "cli_version": version or "0.153.4", "source": source}},
            {"type": "response_item", "timestamp": now(), "payload": {"type": "message", "role": "user",
                "content": [{"type": "input_text", "text": text}]}},
            {"type": "response_item", "timestamp": now(), "payload": {"type": "message", "role": "assistant",
                "content": [{"type": "output_text", "text": "public answer"}]}},
            {"type": "response_item", "payload": {"type": "reasoning", "text": "PRIVATE_THOUGHT"}}]
    else:
        records = [{"sessionId": identifier, "cwd": str(workspace), "timestamp": now(), "version": version or "2.1.283",
            "type": role, "uuid": str(i), "parentUuid": str(i-1) if i else None, "isSidechain": False,
            "message": {"role": role, "content": [{"type": "text", "text": text if role == "user" else "public answer"},
                                                     {"type": "thinking", "thinking": "PRIVATE_THOUGHT"}]}}
            for i, role in enumerate(("user", "assistant"))]
        (root.parent / "history.jsonl").write_text(json.dumps({"sessionId": identifier, "project": str(workspace),
            "timestamp": 1000, "display": "synthetic interactive input"}) + "\n", encoding="utf-8")
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    os.utime(path, (time.time()-60, time.time()-60))
    return path


def setup_native(system, path, agent="codex"):
    plugin = FileHistory(agent, path, runtime_id="agent", secrets_provider=system.worker.native.secrets)
    system.worker.native.plugins = [plugin]
    system.worker.native.probe = lambda _id: "unknown"
    return system.worker.native


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_local_offline_history_import_and_precise_resume(tmp_path, agent):
    async def scenario():
        system = System(tmp_path)
        try:
            root = tmp_path / "records"
            fixture_history(root, tmp_path, agent)
            native = setup_native(system, root, agent)
            response = await system.local.get("/api/v2/native-sessions")
            assert response.status_code == 200, response.text
            assert response.headers["cache-control"] == "no-store"
            item = response.json()["data"]["items"][0]
            identifier = item["nativeSessionId"]
            assert item["activity"]["activity"] == "unknown" and item["format"]["status"] == "readable"
            before = system.db.connection.total_changes
            body = await system.local.get(f"/api/v2/native-sessions/{identifier}/messages")
            assert body.status_code == 200, body.text
            assert "PRIVATE_THOUGHT" not in body.text
            assert system.db.connection.total_changes == before
            imported = await system.local.post(f"/api/v2/native-sessions/{identifier}/imports", json={
                "terminalClosedConfirmed": True, "expectedIndexVersion": item["indexVersion"], "sourceRevision": item["sourceRevision"]},
                headers={"Idempotency-Key": "import", "Origin": "http://127.0.0.1"})
            assert imported.status_code == 201, imported.text
            conv = imported.json()["data"]
            assert conv["conversationKind"] == "native" and "sceneId" not in conv
            assert len(system.chat.repository.messages(conv["id"])) == 2 and not system.adapter.started
            assert (await native.listing()).items == []
            await system.chat.start()
            sent = system.chat.send(conv["id"], SendLocalMessageInput(clientMessageId="continue", text="continue", sessionMode="continue"), "continue")
            await until(lambda: system.chat.repository.run_record(sent.run_id)["status"] in {"succeeded", "failed"})
            record = system.chat.repository.run_record(sent.run_id)
            assert record["status"] == "succeeded", record["error"]
            assert len(system.adapter.resumed) == 1 and not system.adapter.started
            assert system.adapter.resumed[0].external_session_id == "00000000-0000-4000-8000-000000000001"
            assert system.chat.repository.view(record).scene_snapshot is None
        finally:
            await system.close()
    asyncio.run(scenario())


def test_plugin_scope_provenance_version_and_secrets(tmp_path):
    root = tmp_path / "codex"
    source = fixture_history(root, tmp_path, text="Authorization: Bearer hidden\nuser token prose\nAPI_KEY=secret\n<thinking>unfinished")
    from types import SimpleNamespace
    plugin = FileHistory("codex", root, runtime_id="agent")
    workspaces = [SimpleNamespace(path=str(tmp_path), id="workspace")]
    history = plugin.list(workspaces)[0][0]
    assert "hidden" not in str(history.messages) and "unfinished" not in str(history.messages)
    assert "user token prose" in str(history.messages)
    assert plugin.list([SimpleNamespace(path=str(tmp_path / "another"), id="no")]) == []
    assert plugin.list(workspaces, {("agent", "00000000-0000-4000-8000-000000000001")}) == []
    fixture_history(root, tmp_path, source="vscode")
    assert plugin.list(workspaces) == []
    fixture_history(root, tmp_path, version="999.0")
    item = plugin.list(workspaces)[0][0]
    assert not item.readable and item.reason


def test_activity_confirmation_cannot_override_live_process_and_changes_expire_confirmation(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            root = tmp_path / "records"
            path = fixture_history(root, tmp_path)
            native = setup_native(system, root)
            item = (await native.listing()).items[0]
            value = RemoteNativeImportInput(terminalClosedConfirmed=True, expectedIndexVersion=item.index_version, sourceRevision=item.source_revision)
            native.probe = lambda _id: "present"
            with pytest.raises(HubError) as active:
                await native.import_session(item.native_session_id, value, "import", "request")
            assert active.value.code == "NATIVE_SESSION_ACTIVE"
            assert not system.chat.repository.conversations()
            native.probe = lambda _id: "unknown"
            view = await native.import_session(item.native_session_id, value, "import", "request")
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"type": "event_msg", "payload": {"type": "task_complete"}}) + "\n")
            os.utime(path, (time.time()-60, time.time()-60))
            with pytest.raises(HubError) as changed:
                system.chat.send(view.id, SendLocalMessageInput(clientMessageId="stale", text="stale", sessionMode="continue"), "stale")
            assert changed.value.code == "NATIVE_SESSION_CHANGED"
            assert not system.adapter.resumed
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('agent', ['claude','codex'])
def test_unknown_blocks_and_damaged_records_are_unsupported_not_empty_history(tmp_path,agent):
    root=tmp_path/'records'
    path=fixture_history(root,tmp_path,agent)
    plugin=FileHistory(agent,root)
    data=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    message=data[0]['message'] if agent=='claude' else data[1]['payload']
    message['content']=[{'type':'future-private-block','text':'MUST_NOT_GUESS'}]
    path.write_text(''.join(json.dumps(r)+'\n' for r in data),encoding='utf-8')
    from types import SimpleNamespace
    values=plugin.list([SimpleNamespace(id='workspace',path=str(tmp_path))])
    assert len(values)==1 and not values[0][0].readable and values[0][0].reason
    assert 'MUST_NOT_GUESS' not in str(values[0][0].messages)
    message['content']=['not-a-block-object']
    path.write_text(''.join(json.dumps(r)+'\n' for r in data),encoding='utf-8')
    assert not plugin.inspect(path).readable
    fixture_history(root,tmp_path,agent)
    with path.open('a',encoding='utf-8') as stream:
        stream.write('{invalid-json}\n')
    values=plugin.list([SimpleNamespace(id='workspace',path=str(tmp_path))])
    assert len(values)==1 and not values[0][0].readable


def test_claude_provenance_and_sidechains_are_never_inferred_from_filename(tmp_path):
    root=tmp_path/'projects'; path=fixture_history(root,tmp_path,'claude')
    plugin=FileHistory('claude',root)
    from types import SimpleNamespace
    scopes=[SimpleNamespace(id='workspace',path=str(tmp_path))]
    assert plugin.list(scopes)
    (root.parent/'history.jsonl').unlink()
    assert not plugin.list(scopes) and plugin.diagnostics
    fixture_history(root,tmp_path,'claude')
    path.write_text(path.read_text().replace('"isSidechain": false','"isSidechain": true'),encoding='utf-8')
    assert not plugin.list(scopes)


def test_tool_summaries_never_include_arguments_or_output_and_time_basis_is_explicit(tmp_path):
    root=tmp_path/'records'; path=fixture_history(root,tmp_path)
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    rows[0]['payload'].pop('timestamp')
    rows.extend([
        {'type':'response_item','payload':{'type':'message','role':'user',
            'content':[{'type':'input_text','text':'<environment_context>PRIVATE_ENV_PATH</environment_context>'}]}},
        {'type':'response_item','payload':{'type':'message','role':'assistant','channel':'analysis',
            'content':[{'type':'output_text','text':'PRIVATE_ANALYSIS_CHANNEL'}]}},
        {'type':'response_item','payload':{'type':'function_call','name':'exec_command','call_id':'synthetic-call','arguments':'SECRET_ARGUMENT'}},
        {'type':'response_item','payload':{'type':'function_call_output','call_id':'synthetic-call','output':'SECRET_STDOUT'}},
    ])
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
    source=FileHistory('codex',root).inspect(path)
    summaries=[m for m in source.messages if m['role']=='tool_summary']
    assert len(summaries)==2 and all('exec_command' in m['text'] for m in summaries)
    assert 'SECRET_ARGUMENT' not in str(source.messages) and 'SECRET_STDOUT' not in str(source.messages)
    assert 'PRIVATE_ANALYSIS_CHANNEL' not in str(source.messages)
    assert 'PRIVATE_ENV_PATH' not in str(source.messages)
    assert source.created_time_basis=='file_stat' and source.updated_time_basis=='file_stat'


def test_unidentifiable_records_report_local_capability_gap_without_echoing_content(tmp_path):
    async def scenario():
        system=System(tmp_path)
        try:
            root=tmp_path/'records'; root.mkdir()
            (root/'unknown.jsonl').write_text('UNREADABLE_PRIVATE_CONTENT\n',encoding='utf-8')
            setup_native(system,root)
            response=await system.local.get('/api/v2/native-sessions')
            assert response.status_code==422
            assert response.json()['error']['code']=='NATIVE_SESSION_UNSUPPORTED'
            assert 'UNREADABLE_PRIVATE_CONTENT' not in response.text
            assert response.headers['cache-control']=='no-store'
        finally:
            await system.close()
    asyncio.run(scenario())
