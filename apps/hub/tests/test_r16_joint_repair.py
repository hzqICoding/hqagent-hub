import asyncio
import json
import subprocess
from types import SimpleNamespace

import pytest

from protocol.generated.python import AgentResult, AdapterFailure, ResumeRequest
from adapters.codex_adapter import CodexAdapter
from adapters.tests.test_contract_rules import task_spec


class ScriptedProcess:
    """Synthetic App Server JSON-RPC, including deliberately late process EOF."""
    def __init__(self, index):
        self.index = index
        self.pid = 900000 + index
        self.returncode = None
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.stdin = self
        self.requests = []
        self.thread_id = None
        self.after_turn_start = None

    def send(self, value):
        self.stdout.feed_data((json.dumps(value) + '\n').encode())

    def write(self, raw):
        request = json.loads(raw)
        self.requests.append(request)
        if 'id' not in request:
            return
        method, params = request['method'], request.get('params', {})
        result = {}
        if method in {'thread/start', 'thread/resume'}:
            self.thread_id = params.get('threadId', f'synthetic-thread-{self.index}')
            result = {'thread': {'id': self.thread_id}}
        elif method == 'turn/start':
            result = {'turn': {'id': f'turn-{self.index}'}}
        self.send({'id': request['id'], 'result': result})
        if method == 'turn/start':
            self.send({'method': 'turn/started', 'params': {'turn': result['turn']}})
            if self.after_turn_start:
                self.after_turn_start()

    async def drain(self):
        pass

    async def wait(self):
        return self.returncode or 0

    def item(self, value):
        self.send({'method': 'item/completed', 'params': {
            'threadId': self.thread_id, 'turnId': f'turn-{self.index}', 'item': value}})

    def complete(self, summary):
        self.item({'id': 'final', 'type': 'agentMessage', 'phase': 'final_answer',
                   'text': json.dumps({'status': 'done', 'summary': summary, 'changedFiles': []})})
        self.send({'method': 'turn/completed', 'params': {
            'threadId': self.thread_id, 'turn': {'id': f'turn-{self.index}', 'status': 'completed'}}})


class ScriptedRunner:
    def __init__(self):
        self.processes = []

    def find(self, name):
        return name

    async def start(self, *args, **kwargs):
        for old in self.processes:
            if old.returncode is not None and not old.stdout.at_eof():
                old.stdout.feed_eof()
                old.stderr.feed_eof()
        process = ScriptedProcess(len(self.processes) + 1)
        self.processes.append(process)
        return process


def test_resumed_app_server_waits_for_final_turn_and_ignores_old_disconnect(tmp_path, monkeypatch):
    async def scenario():
        runner = ScriptedRunner()
        adapter = CodexAdapter(runner=runner)
        async def preflight(spec):
            return None
        async def terminate(process):
            process.returncode = -9
            # Real wait() can complete before the stdout reader observes EOF.
            return True
        monkeypatch.setattr(adapter, '_preflight', preflight)
        monkeypatch.setattr('adapters.codex_adapter.terminate_process_tree', terminate)
        spec = task_spec(tmp_path)
        handle = await adapter.start(spec)
        assert not isinstance(handle, AdapterFailure)
        runner.processes[0].complete('first final')
        async for _ in adapter.stream_events(handle.session_id):
            pass
        assert (await adapter.collect_result(handle.session_id)).summary == 'first final'
        await adapter.resume(ResumeRequest(sessionId=handle.session_id,
            externalSessionId=handle.external_session_id, taskSpec=spec, message='continue'))
        second = runner.processes[1]
        second.item({'id': 'progress', 'type': 'agentMessage', 'phase': 'commentary',
                     'text': 'I will read the input file before answering.'})
        async def collect():
            async for _ in adapter.stream_events(handle.session_id):
                pass
            return await adapter.collect_result(handle.session_id)
        result = asyncio.create_task(collect())
        await asyncio.sleep(0.02)
        assert not result.done(), 'old EOF or intermediate message ended the resumed turn'
        second.item({'id': 'read', 'type': 'commandExecution', 'command': 'cat README.md',
                     'status': 'completed', 'exitCode': 0})
        await asyncio.sleep(0.02)
        assert not result.done()
        second.complete('resumed final')
        value = await asyncio.wait_for(result, 1)
        assert isinstance(value, AgentResult) and value.summary == 'resumed final'
    asyncio.run(scenario())


@pytest.mark.parametrize('cancel_failure', [None, 'start', 'refused', 'orphan'])
def test_actual_adapter_probe_opens_separate_cancel_session_and_reports_failure(tmp_path, monkeypatch, cancel_failure):
    from runtime.attachments import verification
    async def scenario():
        class ProbeRunner(ScriptedRunner):
            async def start(self, *args, **kwargs):
                if cancel_failure == 'start' and len(self.processes) == 3:
                    raise OSError('private-native-error-must-not-be-recorded')
                process = await super().start(*args, **kwargs)
                if process.index < 4:
                    def complete():
                        process.item({'id': 'progress', 'type': 'agentMessage', 'phase': 'commentary', 'text': 'reading inputs'})
                        process.item({'id': 'tool', 'type': 'commandExecution', 'command': 'cat input.txt', 'status': 'completed', 'exitCode': 0})
                        process.complete(' '.join(self.colors if process.index == 3 else self.colors[:4]) + ' ' + self.nonce)
                    process.after_turn_start = complete
                return process
        runner = ProbeRunner()
        adapter = CodexAdapter(runner=runner)
        original_cancel = adapter.cancel
        async def cancel(request):
            result = await original_cancel(request)
            if adapter.registry.get(request.session_id).process.index == 4:
                if cancel_failure == 'refused':
                    return result.model_copy(update={'outcome': 'refused'})
                if cancel_failure == 'orphan':
                    return result.model_copy(update={'orphan_process_ids': [901234]})
            return result
        async def preflight(spec):
            return None
        async def detect():
            return SimpleNamespace(detected_version='0.159.2')
        async def terminate(process):
            process.returncode = -9
            return True
        synthetic = verification.synthetic_inputs
        def inputs(path):
            values, runner.colors, runner.nonce = synthetic(path)
            return values, runner.colors, runner.nonce
        monkeypatch.setattr(adapter, '_preflight', preflight)
        monkeypatch.setattr(adapter, 'detect', detect)
        monkeypatch.setattr(adapter, 'cancel', cancel)
        monkeypatch.setattr(verification, 'synthetic_inputs', inputs)
        monkeypatch.setattr('adapters.codex_adapter.terminate_process_tree', terminate)
        record = await verification.verify_images(tmp_path, 'codex', adapter=adapter)
        assert all(record['probes'][key] for key in ('new', 'resume', 'mixed-five', 'error'))
        assert record['probes']['cancel'] is (cancel_failure is None)
        assert record['passed'] is (cancel_failure is None)
        if cancel_failure == 'start':
            assert record['diagnostics']['cancel.start']['result'] == 'adapter_failure'
            assert record['diagnostics']['cancel.start']['kind'] == 'transport_error'
            assert record['diagnostics']['cancel.start']['startupStage'] == 'process.start'
            assert 'cancel.stop' not in record['diagnostics']
        else:
            assert len(runner.processes) == 4
            assert runner.processes[3].thread_id != runner.processes[0].thread_id
            assert record['diagnostics']['cancel.stop']['outcome'] == ('refused' if cancel_failure == 'refused' else 'force_killed')
            assert record['diagnostics']['cancel.stop']['orphanProcessIds'] == ([901234] if cancel_failure == 'orphan' else [])
        assert 'private-native-error' not in json.dumps(record)
        assert all(p.returncode is not None for p in runner.processes)
    asyncio.run(scenario())


def test_attachment_prompt_exact_paths_and_text_only_compatibility(tmp_path):
    from protocol.generated.python import AgentInputAttachment
    from adapters.prompt import build_task_prompt
    from adapters.attachment_input import file_prompt
    spec = task_spec(tmp_path).model_copy(update={'read_only': True})
    before = build_task_prompt(spec)
    assert before == '\n'.join([
        '你正在执行 HQAgent-Hub 分派的隔离任务。', '目标：完成测试任务',
        '角色：general_implementer', '会话用途：implement',
        '默认使用简体中文说明进度并输出结果；用户明确要求其他语言时按用户要求。代码、路径、API名和JSON字段名保持原样。',
        f'本轮授权根目录（实际工作目录）：{tmp_path}',
        '所有读取、搜索和修改均受上述根目录约束。配置、文档或依赖引用外部目录不代表获得访问授权；不要对外部目录调用Read/Glob/Grep，说明未验证部分即可。',
        '访问模式：只读，禁止修改文件', '只允许修改这些 glob：', '- apps/hub/adapters/**',
        '只在当前授权目录内读取，禁止任何文件修改。',
        '最后必须只返回符合给定 AgentResult JSON Schema 的对象。',
    ])
    path = r'C:\Users\synthetic user\inputs\readme.md'
    attachment = AgentInputAttachment(attachment={'attachmentId': 'file', 'fileName': 'readme.md',
        'kind': 'file', 'mimeType': 'text/plain', 'sizeBytes': 1, 'sha256': 'a' * 64}, localPath=path)
    prompt = build_task_prompt(spec.model_copy(update={'input_attachments': [attachment]}))
    assert path in prompt and path.replace('\\', '\\\\') not in prompt
    assert '额外允许读取' in prompt and '不得执行或修改' in prompt
    assert '不包括其所在目录的其他文件' in prompt
    assert '所有读取、搜索和修改均受上述根目录约束。' not in prompt
    assert '只在当前授权目录内读取，禁止任何文件修改。' not in prompt
    # Native/explicit resume can supply only the new turn message.
    resumed = file_prompt('continue', [attachment])
    assert path in resumed and '额外允许读取' in resumed
    assert build_task_prompt(spec.model_copy(update={'input_attachments': []})) == before
    assert file_prompt('unchanged', []) == 'unchanged'


def test_probe_images_are_large_distinct_and_visually_separated(tmp_path):
    from PIL import Image
    from runtime.attachments.verification import synthetic_inputs, recognizes
    values, colors, nonce = synthetic_inputs(tmp_path)
    assert len({tuple(colors[i:i + 4]) for i in range(0, 16, 4)}) == 4
    for value in values[:4]:
        with Image.open(value.local_path) as image:
            assert image.size == (512, 512)
            red, green, blue = image.convert('RGB').getpixel((256, 256))
            assert min(red, green, blue) > 240
    assert recognizes(' '.join(colors) + ' ' + nonce, colors, nonce)
    swapped = list(colors)
    swapped[2], swapped[3] = swapped[3], swapped[2]
    assert not recognizes(' '.join(swapped) + ' ' + nonce, colors, nonce)


def test_windows_descriptor_decoding_is_explicit_and_errors_remain_errors(tmp_path, monkeypatch):
    from runtime import descriptor
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        assert kwargs['check'] and kwargs['encoding'] == 'oem' and kwargs['errors'] == 'replace'
        return SimpleNamespace(stdout='"synthetic","S-1-5-21-123"')
    monkeypatch.setattr(descriptor.subprocess, 'run', run)
    assert descriptor._current_windows_sid() == 'S-1-5-21-123'
    def denied(*args, **kwargs):
        raise subprocess.CalledProcessError(5, args[0])
    monkeypatch.setattr(descriptor.subprocess, 'run', denied)
    with pytest.raises(subprocess.CalledProcessError):
        descriptor._current_windows_sid()


def test_subprocess_git_keeps_nonzero_exit_with_legacy_encoded_stderr(tmp_path, monkeypatch):
    import sys
    from security.worktrees import SubprocessGitRunner
    native_run = subprocess.run
    def child(args, **kwargs):
        return native_run([sys.executable, '-X', 'utf8', '-c',
            "import sys;sys.stdout.buffer.write(b'ok');sys.stderr.buffer.write(bytes([0xd2,0xd1,0xb4,0xa6,0xc0,0xed]));sys.exit(7)"], **kwargs)
    monkeypatch.setattr('security.worktrees.subprocess.run', child)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        SubprocessGitRunner().run(['status'], cwd=tmp_path)
    assert caught.value.returncode == 7
    assert caught.value.stdout == 'ok'
    assert isinstance(caught.value.stderr, str) and caught.value.stderr
