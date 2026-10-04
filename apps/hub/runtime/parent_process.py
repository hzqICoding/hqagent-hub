"""Desktop supervisor environment and bounded stdio-v1 control reader."""
from dataclasses import dataclass
from pathlib import Path
import asyncio
import os
import sys
import threading


@dataclass(frozen=True)
class ParentProcess:
    runtime_dir: Path | None = None
    instance_id: str | None = None
    stdio: bool = False

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        control = env.get('HQAGENT_PARENT_CONTROL')
        if control not in {None, 'stdio-v1'}:
            raise ValueError('不支持的 HQAGENT_PARENT_CONTROL')
        runtime = env.get('HQAGENT_RUNTIME_DIR')
        if runtime is not None and (not runtime or not Path(runtime).is_absolute()):
            raise ValueError('HQAGENT_RUNTIME_DIR 必须为绝对目录')
        instance = env.get('HQAGENT_INSTANCE_ID')
        if instance is not None and not 8 <= len(instance) <= 256:
            raise ValueError('HQAGENT_INSTANCE_ID 长度必须为8至256字符')
        return cls(Path(runtime).resolve() if runtime else None, instance, control == 'stdio-v1')


def take_parent_stdin():
    """Detach the control pipe before any reader or child process is started.

    Windows subprocess startup duplicates STD_INPUT_HANDLE when stdin is not
    supplied. That duplication can block behind a synchronous pipe read. Keep
    only a private, non-inheritable copy for the control thread and replace both
    the CRT fd and the Win32 standard handle with NUL. POSIX children see /dev/null
    too, and the private descriptor is close-on-exec.
    """
    if sys.stdin is None:
        raise ValueError('stdio-v1 需要桌面壳提供 stdin 管道')
    kernel = None
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        import msvcrt
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetStdHandle.argtypes = (wintypes.DWORD,)
        kernel.GetStdHandle.restype = wintypes.HANDLE
        kernel.SetStdHandle.argtypes = (wintypes.DWORD, wintypes.HANDLE)
        kernel.SetStdHandle.restype = wintypes.BOOL
        original = kernel.GetStdHandle(wintypes.DWORD(-10))
        if original not in (None, ctypes.c_void_p(-1).value):
            # Embedders may supply a Win32 handle distinct from the CRT fd 0.
            # Detaching fd 0 alone must not leave that original pipe inheritable.
            os.set_handle_inheritable(original, False)
    control_fd = os.dup(sys.stdin.fileno())
    try:
        os.set_inheritable(control_fd, False)
        null_fd = os.open(os.devnull, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
        try:
            # Only NUL is inheritable. On POSIX fd 0 must survive exec so a
            # default-stdin child receives EOF rather than an invalid descriptor.
            os.dup2(null_fd, 0, inheritable=True)
        finally:
            os.close(null_fd)
        if kernel is not None:
            if not kernel.SetStdHandle(wintypes.DWORD(-10), wintypes.HANDLE(msvcrt.get_osfhandle(0))):
                raise ctypes.WinError(ctypes.get_last_error())
        return os.fdopen(control_fd, 'r', encoding='utf-8', errors='replace', newline=None)
    except BaseException:
        os.close(control_fd)
        raise


def watch_parent(stream, loop, stopped, *, close_stream=False):
    """A daemon, not the default executor: blocked stdin must not hang exit."""
    def read():
        oversized = False
        try:
            while True:
                line = stream.readline(4096)
                if not line:
                    break  # EOF: parent is gone.
                if not line.endswith('\n'):
                    oversized = True
                    continue
                if not oversized and line.strip() == 'shutdown':
                    break
                oversized = False
        except (OSError, ValueError):
            pass  # Lost pipe has the same lifetime semantics as EOF.
        finally:
            if close_stream:
                try:
                    stream.close()  # Only its reader closes a potentially blocked stream.
                except (OSError, ValueError):
                    pass
        try:
            loop.call_soon_threadsafe(stopped.set)
        except RuntimeError:
            pass  # Event loop has already stopped for another reason.
    thread = threading.Thread(target=read, name='hub-parent-control', daemon=True)
    try:
        thread.start()
    except BaseException:
        if close_stream:
            stream.close()
        raise
    return thread


async def serve_with_parent(server, listener, application, stream, *, owned_stream=False):
    stopped = asyncio.Event()
    watch_parent(stream, asyncio.get_running_loop(), stopped, close_stream=owned_stream)

    async def shutdown():
        await stopped.wait()
        server.should_exit = True
        application.app.state.shutting_down = True
        application.local_chat.begin_shutdown()
        worker = application.app.state.remote_worker
        worker.closed = True  # Close the command admission gate before any await.
        try:
            application.drain.set_maintenance(True, '桌面壳退出，Hub 正在停止')
        finally:
            await worker.disconnect()

    watcher = asyncio.create_task(shutdown())
    try:
        await server.serve(sockets=[listener])
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
