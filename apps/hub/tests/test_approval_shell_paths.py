import os
from pathlib import Path

import pytest

from adapters.path_guard import PathGuard


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows PowerShell approval wrapper')


@pytest.fixture
def guard(tmp_path, monkeypatch):
    monkeypatch.setattr('adapters.path_guard.shutil.which', lambda name:
                        r'C:\Program Files\PowerShell\7\pwsh.exe' if name == 'pwsh.exe' else None)
    return PathGuard(str(tmp_path), ['**'])


def wrap(script):
    return '"C:\\Program Files\\PowerShell\\7\\pwsh.exe" -Command "' + script + '"'


def test_native_node_marker_command_checks_target_not_powershell_installation(guard, tmp_path):
    target = (tmp_path / 'approval-rejected.txt').as_posix()
    command = wrap(f"node -e \\\"require('node:fs').writeFileSync('{target}','APPROVAL_TEST',{{flag:'wx'}})\\\"")
    assert guard.inspect_tool_call('shell', {'command': command}) == []
    assert not (tmp_path / 'approval-rejected.txt').exists()


def test_quoted_write_target_with_spaces_is_preserved(guard, tmp_path):
    target = str(tmp_path / 'a folder' / 'marker file.txt')
    assert guard.inspect_tool_call('shell', {'command': wrap(f"Set-Content -LiteralPath '{target}' -Value ok")}) == []


def test_external_target_is_still_rejected(guard):
    target = r'C:\Private Folder\marker.txt'
    assert guard.inspect_tool_call('shell', {'command': wrap(f"Set-Content -LiteralPath '{target}' -Value no")}) == [target]


def test_script_cannot_write_to_trusted_launcher(guard):
    target = r'C:\Program Files\PowerShell\7\pwsh.exe'
    assert guard.inspect_tool_call('shell', {'command': wrap(f"Set-Content -LiteralPath '{target}' -Value no")}) == [target]


def test_arbitrary_launcher_and_encoded_command_are_not_exempted(guard):
    unknown = r'C:\Untrusted Folder\pwsh.exe'
    assert unknown in guard.inspect_tool_call('shell', {'command': f'"{unknown}" -Command "echo ok"'})
    command = '"C:\\Program Files\\PowerShell\\7\\pwsh.exe" -EncodedCommand ZQBjAGgAbwA='
    assert guard.inspect_tool_call('shell', {'command': command})


def test_unresolved_write_still_fails_closed(guard):
    assert guard.inspect_tool_call('shell', {'command': wrap('Set-Content -LiteralPath $target -Value no')}) == ['<unresolved shell write target>']
