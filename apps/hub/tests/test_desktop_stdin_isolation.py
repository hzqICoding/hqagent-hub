"""Real process/pipe regressions; never touch installed data or model CLIs."""
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

import pytest


SCRIPT = r'''
import asyncio, os, subprocess, sys, threading, time
from runtime.parent_process import take_parent_stdin, watch_parent

async def run():
    alternate = None
    if os.name == 'nt':
        import ctypes, msvcrt
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetStdHandle.argtypes = (wintypes.DWORD,)
        kernel.GetStdHandle.restype = wintypes.HANDLE
        kernel.SetStdHandle.argtypes = (wintypes.DWORD, wintypes.HANDLE)
        kernel.SetStdHandle.restype = wintypes.BOOL
        if sys.argv[1] == 'shutdown':
            alternate = os.dup(0)
            os.set_inheritable(alternate, True)
            assert kernel.SetStdHandle(wintypes.DWORD(-10), msvcrt.get_osfhandle(alternate))
    control = take_parent_stdin()
    if alternate is not None:
        assert not os.get_inheritable(alternate)
        os.close(alternate)
    assert not os.get_inheritable(control.fileno())
    assert os.get_inheritable(0)  # The inherited descriptor is NUL, never control.
    assert os.read(0, 1) == b''
    assert sys.stdin.read(1) == ''
    if os.name == 'nt':
        assert kernel.GetStdHandle(wintypes.DWORD(-10)) == msvcrt.get_osfhandle(0)
    reading = threading.Event()
    stopped = asyncio.Event()
    class Stream:
        def readline(self, limit):
            reading.set()
            return control.readline(limit)
        def close(self):
            control.close()
    reader = watch_parent(Stream(), asyncio.get_running_loop(), stopped, close_stream=True)
    assert reading.wait(1)
    await asyncio.sleep(0.1)  # Reader stays blocked until this process's parent writes/closes.
    # Deliberately omit stdin and disable close_fds: verify even a future missed
    # call site cannot inherit the private control stream or steal its input.
    child = subprocess.run([sys.executable, '-B', '-c',
        'import sys; assert sys.stdin.buffer.read(1) == b""; print("CHILD_EOF")'],
        close_fds=False, capture_output=True, timeout=3)
    assert child.returncode == 0 and child.stdout.strip() == b'CHILD_EOF'
    assert not stopped.is_set() and reader.is_alive()
    print('ISOLATED', flush=True)
    if sys.argv[1] == 'server_exit':
        return  # Parent still holds its write end; blocked daemon must not hang exit.
    await asyncio.wait_for(stopped.wait(), 5)
    reader.join(1)
    assert not reader.is_alive() and control.closed
    print('STOPPED', flush=True)

asyncio.run(run())
'''


@pytest.mark.parametrize('control', ['shutdown', 'eof', 'server_exit'])
def test_private_control_is_not_inherited_by_child_and_never_blocks_exit(control):
    child = subprocess.Popen([sys.executable, '-B', '-c', SCRIPT, control],
        cwd=Path(__file__).resolve().parents[1], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    lines = queue.Queue()
    def read():
        lines.put(child.stdout.readline())
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        assert lines.get(timeout=6).strip() == b'ISOLATED'
        if control == 'shutdown':
            child.stdin.write(b'shutdown\n')
            child.stdin.flush()
        elif control == 'eof':
            child.stdin.close()
            child.stdin = None
        assert child.wait(timeout=6) == 0
        stdout, stderr = child.communicate(timeout=2)
        assert not stderr
        if control != 'server_exit':
            assert stdout.strip() == b'STOPPED'
    finally:
        if child.stdin is not None:
            child.stdin.close()
            child.stdin = None
        if child.poll() is None:
            try:
                child.wait(timeout=6)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)
        reader.join(1)
