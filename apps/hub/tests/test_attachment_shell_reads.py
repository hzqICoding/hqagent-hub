import hashlib
import os
import shlex
from pathlib import Path

import pytest
from protocol.generated.python import AgentInputAttachment
from adapters.path_guard import PathGuard


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path / 'worktree'
    root.mkdir()
    directory = tmp_path / 'private inputs'
    directory.mkdir()
    file = directory / 'input.txt'
    file.write_bytes(b'synthetic attachment')
    (directory / 'other.txt').write_bytes(b'not granted')
    value = AgentInputAttachment(attachment={
        'attachmentId': 'input', 'fileName': 'input.txt', 'kind': 'file',
        'mimeType': 'text/plain', 'sizeBytes': file.stat().st_size,
        'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}, localPath=str(file))
    return root, file, value


def quote(path, platform):
    return "'" + str(path) + "'" if platform == 'nt' else shlex.quote(str(path))


@pytest.mark.parametrize('platform,command', [
    ('nt', 'Get-Content -LiteralPath {file}'), ('nt', 'Get-Content -Raw -LiteralPath {file}'),
    ('nt', 'Get-Content -LiteralPath {file} -Raw -Encoding UTF8'),
    ('nt', 'Get-Content -Path {file} -Encoding UTF8'),
    ('nt', 'type {file}'), ('nt', 'type "{raw}"'), ('nt', 'cat {file}'),
    ('posix', 'cat {file}'), ('posix', 'head -n 5 {file}'),
])
def test_exact_attachment_shell_read_is_not_a_write_grant(inputs, platform, command):
    root, file, value = inputs
    guard = PathGuard(str(root), [], platform=platform, input_attachments=[value])
    text = command.format(file=quote(file, platform), raw=str(file))
    assert guard.inspect_tool_call('shell', {'command': text}) == []
    assert not guard.allows(str(file)) and guard.contains(str(file))
    file.write_bytes(b'corrupted')
    assert guard.inspect_tool_call('shell', {'command': text})


@pytest.mark.parametrize('platform', ['nt', 'posix'])
@pytest.mark.parametrize('command', [
    'Remove-Item {file}', 'Set-Content {file} text', 'Out-File {file}',
    'rm {file}', 'mv {file} local.txt', 'cp local.txt {file}', 'tee {file}',
    'echo x > {file}', 'echo x 2>> {file}', 'echo x &> {file}',
    'cat {file} > local.txt', 'cat {file} | tee local.txt',
    'cat {other}', 'Get-ChildItem {directory}', 'cat {wildcard}',
    'cat {traversal}', 'python -c "open({file}).read()"',
])
def test_attachment_shell_exception_rejects_writes_neighbors_and_uncertain_forms(inputs, platform, command):
    root, file, value = inputs
    guard = PathGuard(str(root), ['**'], platform=platform, input_attachments=[value])
    text = command.format(
        file=quote(file, platform), other=quote(file.with_name('other.txt'), platform),
        directory=quote(file.parent, platform), wildcard=quote(file.parent / '*', platform),
        traversal=quote(file.parent / '..' / file.parent.name / file.name, platform))
    assert guard.inspect_tool_call('shell', {'command': text})


@pytest.mark.parametrize('platform', ['nt', 'posix'])
def test_attachment_directory_does_not_gain_access_when_inside_worktree(inputs, platform):
    root, file, value = inputs
    guard = PathGuard(str(root.parent), ['**'], platform=platform, input_attachments=[value])
    for path in (file.parent, file.with_name('other.txt'), file.parent / '*'):
        assert guard.inspect_tool_call('shell', {'command': 'cat ' + quote(path, platform)})
    relative = file.relative_to(root.parent)
    assert guard.inspect_tool_call('shell', {'command': 'cat ' + quote(relative, platform)}) == []
    assert guard.inspect_tool_call('shell', {'command': 'tee ' + quote(relative, platform)})


@pytest.mark.parametrize('shell', ['bash', 'sh', 'zsh'])
def test_installed_posix_shell_and_env_wrappers(inputs, monkeypatch, shell):
    root, file, value = inputs
    executables = {name: str(root / name) for name in ('env', 'bash', 'sh', 'zsh')}
    monkeypatch.setattr('adapters.path_guard.shutil.which', executables.get)
    guard = PathGuard(str(root), [], platform='posix', input_attachments=[value])
    payload = 'head -n 5 ' + shlex.quote(str(file))
    for prefix in (f'{shell} -c ', f'env LC_ALL=C {shell} -c '):
        assert guard.inspect_tool_call('shell', {'command': prefix + shlex.quote(payload)}) == []
    monkeypatch.setattr('adapters.path_guard.shutil.which', lambda _: None)
    assert guard.inspect_tool_call('shell', {'command': f'{shell} -c ' + shlex.quote(payload)})


def test_posix_read_utility_names_are_case_sensitive(inputs):
    root, file, value = inputs
    guard = PathGuard(str(root), [], platform='posix', input_attachments=[value])
    assert guard.inspect_tool_call('shell', {'command': 'CAT ' + shlex.quote(str(file))})


@pytest.mark.parametrize('prefix', ['env FOO=x; bash -c ', 'env FOO=x&& bash -c ',
                                     'env LD_AUDIT=/outside/hook.so bash -c '])
def test_outer_operators_and_unproven_environment_cannot_inherit_read_grant(inputs, monkeypatch, prefix):
    root, file, value = inputs
    monkeypatch.setattr('adapters.path_guard.shutil.which', lambda name: str(root / name))
    guard = PathGuard(str(root), [], platform='posix', input_attachments=[value])
    command = prefix + shlex.quote('cat ' + shlex.quote(str(file)))
    assert guard.inspect_tool_call('shell', {'command': command})


def test_installed_powershell_wrapper_preserves_literal_path(inputs, monkeypatch):
    root, file, value = inputs
    executable = str(root / 'powershell.exe')
    monkeypatch.setattr('adapters.path_guard.shutil.which', lambda name: executable if name == 'powershell.exe' else None)
    guard = PathGuard(str(root), [], platform='nt', input_attachments=[value])
    command = f'"{executable}" -NoProfile -Command "Get-Content -LiteralPath \'{file}\'"'
    assert guard.inspect_tool_call('shell', {'command': command}) == []
    command = command.replace('Get-Content -LiteralPath', 'Remove-Item -LiteralPath')
    assert guard.inspect_tool_call('shell', {'command': command})


def test_symbolic_alias_is_not_an_attachment_grant(inputs, monkeypatch):
    root, file, value = inputs
    alias = file.with_name('alias.txt')
    try:
        alias.symlink_to(file)
    except OSError:
        # Windows may lack symlink privilege; still exercise the exact identity
        # and symlink checks. POSIX CI takes the real filesystem branch.
        resolve, is_symlink = Path.resolve, Path.is_symlink
        monkeypatch.setattr(Path, 'resolve', lambda p, *a, **kw: file if p == alias else resolve(p, *a, **kw))
        monkeypatch.setattr(Path, 'is_symlink', lambda p: p == alias or is_symlink(p))
    guard = PathGuard(str(root), [], input_attachments=[value])
    assert not guard.contains(str(alias))
    assert guard.inspect_tool_call('shell', {'command': 'cat ' + quote(alias, os.name)})


@pytest.mark.parametrize('platform', ['nt', 'posix'])
def test_without_attachments_never_enters_the_new_exception(inputs, platform, monkeypatch):
    root, file, _ = inputs
    guard = PathGuard(str(root), [], platform=platform)
    def forbidden(*args):
        pytest.fail('Attachment-free commands entered the new exception')
    monkeypatch.setattr(guard, '_attachment_shell_read', forbidden)
    assert guard.inspect_tool_call('shell', {'command': 'echo hello'}) == []
    outside = 'C:/outside/input.txt' if platform == 'nt' else '/outside/input.txt'
    assert guard.inspect_tool_call('shell', {'command': 'cat ' + quote(outside, platform)})
