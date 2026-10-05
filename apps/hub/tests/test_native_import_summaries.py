import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
import time

import pytest

from adapters.history import digest
from core.errors import HubError
from runtime.native.service import NativeService
from remote_support import System, Workspaces, FakeRemoteServer, until, command_events
from test_r3_native import fixture_history, setup_native
from test_r3_wire import resource, permission


def summary(text, index=0):
    return {'id': f'native-{index}', 'role': 'tool_summary', 'text': text,
            'createdAt': f'2026-09-05T12:00:{index:02d}Z'}


@pytest.mark.parametrize(('lines', 'expected'), [
    (['Bash：历史调用', 'Bash：历史返回记录'], '工具调用 ×1：Bash'),
    (['Bash：历史调用'], '工具调用 ×1：Bash'),
    (['Read：历史返回记录'], '工具调用 ×1：Read'),
    (['Bash：历史调用', 'Bash：历史调用', 'Bash：历史返回记录'], '工具调用 ×2：Bash ×2'),
    (['Bash：历史调用', 'Bash：历史返回记录', 'Bash：历史返回记录'], '工具调用 ×2：Bash ×2'),
    (['Read：历史调用', 'Bash：历史调用', 'Read：历史返回记录'], '工具调用 ×3：Read ×2、Bash'),
    (['Read：历史返回记录', 'Bash：历史调用', 'Read：历史调用', 'Read：历史返回记录'],
        '工具调用 ×3：Read ×2、Bash'),
    (['工具：历史搜索调用'], '工具调用 ×1：工具'),
])
def test_pair_and_orphan_counting_including_multiline_parts(lines, expected):
    messages = [summary(line, n) for n, line in enumerate(lines)]
    original = deepcopy(messages)
    mapped = NativeService._import_snapshot(messages, 'binding')
    assert len(mapped) == 1 and mapped[0]['text'] == expected
    assert mapped[0]['role'] == 'system'
    assert mapped[0]['createdAt'] == messages[0]['createdAt']
    assert mapped[0]['id'] == 'message_' + digest(['native-tool-summary', 'binding', messages[0]['id']])
    # Some readers put multiple tools in one Native message. Count their safe
    # lines in the same order, including pairs across message boundaries.
    assert NativeService._import_snapshot([summary('\n'.join(lines))], 'binding') == mapped
    assert NativeService._import_snapshot(messages, 'binding') == mapped
    assert NativeService._import_snapshot(messages, 'other-binding')[0]['id'] != mapped[0]['id']
    assert messages == original


def test_runs_do_not_cross_public_text_and_unknown_names_cannot_leak():
    public = {'id': 'user', 'role': 'user', 'text': '  完整文本\n\n工具调用 ×1：不是占位符\n'}
    assistant = {'id': 'assistant', 'role': 'assistant', 'text': '答复\n```text\nBash：历史调用\n```'}
    messages = [summary('Bash：历史调用'), public, summary('Bash：历史返回记录', 1), assistant,
                summary('[redacted]：历史调用', 2), summary('sk-PRIVATE /secret/path：历史返回记录', 3)]
    mapped = NativeService._import_snapshot(messages, 'binding')
    assert [m['text'] for m in mapped if m['role'] == 'system'] == [
        '工具调用 ×1：Bash', '工具调用 ×1：Bash', '工具调用 ×2：工具 ×2']
    assert mapped[1] == public and mapped[3] == assistant
    assert 'PRIVATE' not in str(mapped) and '/secret/path' not in str(mapped)
    assert NativeService._import_snapshot([], 'binding') == []
    assert NativeService._import_snapshot([public, assistant], 'binding') == [public, assistant]


def history_with_tools(root, workspace):
    path = fixture_history(root, workspace)
    head = json.loads(path.read_text('utf-8').splitlines()[0])
    rows = [head]
    def message(role, text):
        rows.append({'type': 'response_item', 'payload': {'type':'message', 'role':role,
            'content':[{'type': 'input_text' if role == 'user' else 'output_text', 'text':text}]}})
    def call(name, identifier):
        rows.append({'type':'response_item', 'payload':{'type':'function_call', 'name':name,
            'call_id':identifier, 'arguments':'PRIVATE_ARGUMENT /private/path'}})
    def result(identifier):
        rows.append({'type':'response_item', 'payload':{'type':'function_call_output',
            'call_id':identifier, 'output':'PRIVATE_TOOL_OUTPUT Bearer PRIVATE_CREDENTIAL'}})
    message('user', '  公开问题\n\n保留格式与内容。')
    for name, count in [('Bash', 14), ('Read', 4)]:
        for n in range(count):
            identifier = f'{name}-{n}'
            call(name, identifier)
            result(identifier)
    message('assistant', '完整答复\n```text\nRead：历史调用\n```\n')
    result('Read-3')  # A return without an adjacent call.
    call('Bash', 'orphan')
    message('user', '下一轮，继续。\n')
    call('Bash', 'single')
    result('single')
    call('sk-PRIVATE_TOOL_NAME /private/path', 'unknown')
    result('unknown')
    message('assistant', '最后的公开答复。')
    stamp = datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
    for n, row in enumerate(rows):
        row['timestamp'] = (stamp + timedelta(seconds=n)).isoformat().replace('+00:00', 'Z')
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), 'utf-8')
    os.utime(path, (time.time() - 60, time.time() - 60))
    return path


def test_local_and_granted_remote_import_share_snapshot_and_binding_idempotency(tmp_path):
    async def scenario():
        root = tmp_path / 'records'
        history_with_tools(root, tmp_path)
        results = []
        for mode in ('local', 'remote'):
            system = System(tmp_path / mode)
            system.ports.workspaces = Workspaces(tmp_path)
            native = setup_native(system, root)
            try:
                await native.scan()
                item = (await native.listing()).items[0]
                identifier = item.native_session_id
                row = native.row(identifier)
                source = await native.io(native.source, row, full=True)
                original = deepcopy(source.messages)
                assert len(original) == 46  # 42 tool placeholders + four public messages.
                assert all('PRIVATE' not in m['text'] for m in original)
                assert sum(m['role'] == 'tool_summary' for m in original) == 42
                before = await native.read(identifier, limit=100)
                body = {'terminalClosedConfirmed': True, 'expectedIndexVersion': item.index_version,
                        'sourceRevision': item.source_revision}
                url = f'/api/v2/native-sessions/{identifier}/imports'
                if mode == 'local':
                    response = await system.local.post(url, json=body,
                        headers={'Idempotency-Key':'import', 'Origin':'http://127.0.0.1'})
                    assert response.status_code == 201
                    conversation = response.json()['data']['id']
                else:
                    async with FakeRemoteServer(revision=3) as server:
                        await system.pair(server, start=True)
                        frame = resource(system, 'native.import', {'nativeSessionId':identifier,
                            'sourceRevision':item.source_revision, 'expectedIndexVersion':item.index_version,
                            'confirmation':native.confirm(source, 'request-test')}, 'tool-import')
                        await server.send(frame)
                        await until(lambda: command_events(server, 'tool-import', 'command.received'))
                        receipt = command_events(server, 'tool-import', 'command.received')[-1]
                        await server.send(permission(frame, receipt))
                        await until(lambda: command_events(server, 'tool-import', 'command.completed'))
                        completed = command_events(server, 'tool-import', 'command.completed')[-1]
                        conversation = completed['resourceRef']['conversationId']
                        await until(lambda: any(f['type'] == 'sync.message.segment' and
                            f['payload']['conversationId'] == conversation for f in server.frames))
                        assert not server.errors
                    await system.worker.stop()
                def stored():
                    with system.db.locked_connection() as db:
                        return [dict(r) for r in db.execute(
                            'SELECT * FROM local_messages WHERE conversation_id=? ORDER BY sequence', (conversation,))]
                messages = stored()
                assert len(messages) == 7 and [m['sequence'] for m in messages] == list(range(1, 8))
                tools = [m for m in messages if m['role'] == 'system']
                assert [m['text'] for m in tools] == [
                    '工具调用 ×18：Bash ×14、Read ×4', '工具调用 ×2：Read、Bash', '工具调用 ×2：Bash、工具']
                assert [(m['role'], m['text'], m['created_at']) for m in messages if m['role'] != 'system'] == [
                    (m['role'], m['text'], m['createdAt']) for m in original if m['role'] != 'tool_summary']
                expected = native._import_snapshot(original, row['binding_key'])
                assert [m['message_id'] for m in tools] == [m['id'] for m in expected if m['role'] == 'system']
                assert [m['created_at'] for m in tools] == [m['createdAt'] for m in expected if m['role'] == 'system']
                for key in ('import', 'import', 'another-import-key'):
                    repeat = await system.local.post(url, json=body,
                        headers={'Idempotency-Key':key, 'Origin':'http://127.0.0.1'})
                    assert repeat.status_code == 201 and repeat.json()['data']['id'] == conversation
                    assert stored() == messages
                # Preview, its IDs/parts and its filtered content stay unmerged.
                index = native.index_for(native.plugin(row))
                entry = index.load(json.loads(row['source_json'])['path'])
                after_parts, position = await native.io(index.page, entry, None, 100)
                assert position is None
                assert after_parts == [m.model_dump(mode='json', by_alias=True, exclude_none=True) for m in before.items]
                assert (await native.io(native.source, row, full=True)).messages == original
                with pytest.raises(HubError) as imported:
                    await native.read(identifier, limit=100)
                assert imported.value.code == 'NOT_FOUND'  # Existing imported-preview fence.
                results.append(([(m['sequence'], m['role'], m['text'], m['created_at']) for m in messages],
                                [m['message_id'] for m in tools]))
                assert not system.adapter.started
            finally:
                await system.close()
        assert results[0] == results[1]
    asyncio.run(scenario())
