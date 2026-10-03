"""Offline Windows bundle smoke. Isolated data; never prints descriptor secrets."""
import argparse
import ctypes
from ctypes import wintypes
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def processes():
    class Entry(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD),
                    ('pid', wintypes.DWORD), ('heap', ctypes.c_size_t),
                    ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                    ('parent', wintypes.DWORD), ('priority', wintypes.LONG),
                    ('flags', wintypes.DWORD), ('exe', wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        item = Entry()
        item.size = ctypes.sizeof(item)
        result = {}
        valid = kernel.Process32FirstW(snapshot, ctypes.byref(item))
        while valid:
            result[item.pid] = item.parent
            valid = kernel.Process32NextW(snapshot, ctypes.byref(item))
        return result
    finally:
        kernel.CloseHandle(snapshot)


def descendants(mapping, roots):
    found = set(roots)
    while True:
        added = {pid for pid, parent in mapping.items() if parent in found}
        if added <= found:
            return found
        found |= added


def get(port, path, token=None, origin=None):
    client = HTTPConnection('127.0.0.1', port, timeout=1)
    try:
        headers = {}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if origin:
            headers['Origin'] = origin
        client.request('GET', path, headers=headers)
        response = client.getresponse()
        return response.status, json.loads(response.read())
    finally:
        client.close()


def smoke(exe, work, control):
    data = Path(tempfile.mkdtemp(prefix=control + '-', dir=work))
    env = dict(os.environ)
    for key in ('HQAGENT_HUB_DATA_DIR', 'PYTHONHOME', 'PYTHONPATH'):
        env.pop(key, None)
    env.update(LOCALAPPDATA=str(data / 'local'), HOME=str(data), USERPROFILE=str(data),
               HQAGENT_RUNTIME_DIR=str(data / 'shell-runtime'), HQAGENT_INSTANCE_ID='smoke-desktop-' + control,
               HQAGENT_PARENT_CONTROL='stdio-v1', HQAGENT_CODEX_PATH=str(data / 'missing'),
               HQAGENT_CLAUDE_PATH=str(data / 'missing'), PYTHONDONTWRITEBYTECODE='1',
               PATH=str(Path(os.environ['SystemRoot']) / 'System32'))
    descriptor = data / 'shell-runtime' / 'hub.json'
    started = time.perf_counter()
    process = subprocess.Popen([str(exe)], cwd=exe.parent, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    seen = {process.pid}
    secret = None
    try:
        while time.perf_counter() - started < 40:
            seen = descendants(processes(), seen)
            code = process.poll()
            if code is not None:
                if code & 0xffffffff == 0xc0000142:
                    raise RuntimeError('0xC0000142: stop; local resources exhausted')
                errors = process.stderr.read().decode('utf-8', errors='replace')
                raise RuntimeError('Bundle exited before health: ' + str(code) + '\n' + errors)
            if descriptor.exists():
                info = json.loads(descriptor.read_text(encoding='utf-8'))
                secret = info['token']
                try:
                    status, health = get(info['port'], '/healthz')
                    if status == 200:
                        break
                except OSError:
                    pass
            time.sleep(0.05)
        else:
            raise RuntimeError('Bundle cold-start health timeout')
        elapsed = time.perf_counter() - started
        assert info['instanceId'] == env['HQAGENT_INSTANCE_ID']
        assert info['pid'] == process.pid == health['pid']
        assert 1024 <= info['port'] <= 65535 and info['baseUrl'] == f"http://127.0.0.1:{info['port']}"
        root = data / 'local' / 'HQAgent-Hub'
        assert (root / 'data' / 'hub.db').is_file()
        assert not (root / 'runtime' / 'hub.json').exists()
        assert get(info['port'], '/api/v1/bootstrap', secret, 'http://tauri.localhost')[0] == 200
        assert get(info['port'], '/api/v1/remote/link', secret, 'https://tauri.localhost')[0] == 200
        assert get(info['port'], '/api/v1/remote/link', secret, 'https://evil.example')[0] == 403
        stopping = time.perf_counter()
        if control == 'shutdown':
            process.stdin.write(b'shutdown\n')
            process.stdin.flush()
        else:
            process.stdin.close()
            process.stdin = None
        assert process.wait(timeout=15) == 0
        stop_seconds = time.perf_counter() - stopping
        output, errors = process.communicate()
        assert secret.encode() not in output + errors
        assert b'Local connection code' not in output
        assert not descriptor.exists() and not (root / 'runtime' / 'hub.lock').exists()
        current = processes()
        assert not (descendants(current, seen) & current.keys()), 'Residual child process'
        print(json.dumps({'control': control, 'health': 'ok', 'protocolVersion': health['protocolVersion'],
                          'coldStartSeconds': round(elapsed, 3), 'exitSeconds': round(stop_seconds, 3),
                          'exitCode': process.returncode, 'descriptorRemoved': True, 'residualChildren': 0}))
    finally:
        if process.stdin is not None:
            process.stdin.close()
        if process.poll() is None:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('Windows bundle smoke requires Windows')
    exe = args.exe.resolve(strict=True)
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    def inventory():
        return {str(p.relative_to(exe.parent)): (p.stat().st_size, p.stat().st_mtime_ns)
                for p in exe.parent.rglob('*') if p.is_file()}
    before = inventory()
    for control in ('shutdown', 'eof'):
        smoke(exe, work, control)
    assert inventory() == before, 'Runtime changed installation contents'
    size = sum(value[0] for value in before.values())
    print(json.dumps({'bundleFiles': len(before), 'bundleBytes': size, 'bundleMiB': round(size / 1024**2, 2),
                      'installationUnchanged': True}))


if __name__ == '__main__':
    main()
