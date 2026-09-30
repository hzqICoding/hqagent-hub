import os
from pathlib import Path
import shlex
import shutil

import pytest

from adapters.path_guard import PathGuard


@pytest.mark.parametrize('name',['bash','sh','zsh'])
def test_posix_wrapper_resolution_is_pure_and_requires_real_path_discovery(tmp_path,monkeypatch,name):
    launcher=tmp_path/'bin'/name
    env=tmp_path/'bin'/'env'
    monkeypatch.setattr('adapters.path_guard.shutil.which',lambda key: str(launcher) if key==name else str(env) if key=='env' else None)
    script="touch 'relative file.txt'"
    assert PathGuard._posix_payload(shlex.join([name,'-c',script]))==script
    assert PathGuard._posix_payload(shlex.join([str(env),'LANG=C',name,'-c',script]))==script
    assert PathGuard._posix_payload(shlex.join([str(tmp_path/'unknown'/name),'-c',script])) is None
    assert PathGuard._posix_payload(shlex.join(['env','PATH=/evil',name,'-c',script])) is None
    assert PathGuard._posix_payload(shlex.join([name,'-c',script,'extra'])) is None
    monkeypatch.setattr('adapters.path_guard.shutil.which',lambda _name:None)
    assert PathGuard._posix_payload(shlex.join([name,'-c',script])) is None


def test_relative_reads_and_home_escape_use_real_worktree_boundary(tmp_path):
    guard=PathGuard(str(tmp_path),[])
    assert guard.inspect_tool_call('Read',{'file_path':'inside.txt'})==[]
    assert guard.inspect_tool_call('Read',{'file_path':'../outside.txt'})
    assert guard.inspect_tool_call('Read',{'file_path':'~/.ssh'})


@pytest.fixture
def posix_guard(tmp_path):
    if os.name=='nt':pytest.skip('POSIX shell approval wrappers')
    shells=[name for name in ('bash','sh','zsh') if shutil.which(name)]
    assert shells
    return PathGuard(str(tmp_path),['**']),shells


def wrapped(shell,script):
    return shlex.join([shutil.which(shell),'-c',script])


def test_posix_inline_marker_checks_target_not_shell_installation(posix_guard,tmp_path):
    guard,shells=posix_guard
    script='node -e '+shlex.quote("require('node:fs').writeFileSync('"+str(tmp_path/'marker')+"','ok')")
    for shell in shells:
        assert guard.inspect_tool_call('shell',{'command':wrapped(shell,script)})==[]
    assert not (tmp_path/'marker').exists()


def test_posix_quoted_target_with_spaces_and_env_wrapper(posix_guard,tmp_path):
    guard,shells=posix_guard
    script='touch '+shlex.quote(str(tmp_path/'folder'/'space file'))
    for shell in shells:
        command=shlex.join([shutil.which('env'),'LANG=C',shell,'-c',script])
        assert guard.inspect_tool_call('shell',{'command':command})==[]


def test_posix_external_targets_still_rejected(posix_guard,tmp_path):
    guard,shells=posix_guard
    for target in ('/etc/passwd','~/.ssh','../outside'):
        assert guard.inspect_tool_call('Read',{'file_path':target})
        for shell in shells:
            assert guard.inspect_tool_call('shell',{'command':wrapped(shell,'touch '+shlex.quote(target))})
    outside=tmp_path.parent/'outside';outside.mkdir(exist_ok=True)
    (tmp_path/'escape').symlink_to(outside,target_is_directory=True)
    assert guard.inspect_tool_call('Read',{'file_path':'escape/private'})
    assert guard.inspect_tool_call('shell',{'command':wrapped(shells[0],'touch escape/private')})
    # POSIX C:/ is an ordinary relative filename, including symlink guards.
    assert guard.contains('C:/Windows/file')
    assert not guard.allows('C:/../../outside')
    (tmp_path/'C:').symlink_to(outside,target_is_directory=True)
    assert not guard.contains('C:/Windows/file')


def test_posix_cannot_write_to_trusted_launcher(posix_guard):
    guard,shells=posix_guard
    for shell in shells:
        target=shutil.which(shell)
        assert guard.inspect_tool_call('shell',{'command':wrapped(shell,'printf bad > '+shlex.quote(target))})==[target]


def test_posix_arbitrary_launcher_or_unknown_flags_not_exempted(posix_guard):
    guard,shells=posix_guard
    assert guard.inspect_tool_call('shell',{'command':"/untrusted/bash -c 'echo ok'"})
    for shell in shells:
        assert guard.inspect_tool_call('shell',{'command':shlex.join([shell,'--unknown','echo ok'])})


def test_posix_unresolved_write_fails_closed(posix_guard):
    guard,shells=posix_guard
    for shell in shells:
        for script in ('touch "$target"','cd /tmp; touch file','eval "touch file"','touch *','printf x >'):
            assert guard.inspect_tool_call('shell',{'command':wrapped(shell,script)})


@pytest.mark.skipif(os.name=='nt',reason='POSIX executable symlink and directory-fd semantics')
def test_posix_npm_symlink_uses_os_launcher_and_lease_detects_replacement(tmp_path):
    from adapters.process import executable_args
    from runtime.native.paths import directory_lease
    from core.errors import HubError
    binary=tmp_path/'real-cli';binary.write_text('#!/bin/sh\nexit 0\n');binary.chmod(0o700)
    shim=tmp_path/'cli';shim.symlink_to(binary)
    assert executable_args(str(shim),'--version')==[str(shim),'--version']
    target=tmp_path/'directory';target.mkdir()
    with pytest.raises(HubError) as error:
        with directory_lease(str(target)):
            target.rename(tmp_path/'moved')
            target.mkdir()
    assert error.value.code=='REMOTE_DIRECTORY_CHANGED'
