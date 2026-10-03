"""Desktop supervisor environment and bounded stdio-v1 control reader."""
from dataclasses import dataclass
from pathlib import Path
import asyncio
import os
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


def watch_parent(stream, loop, stopped):
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
        try:
            loop.call_soon_threadsafe(stopped.set)
        except RuntimeError:
            pass  # Event loop has already stopped for another reason.
    thread = threading.Thread(target=read, name='hub-parent-control', daemon=True)
    thread.start()
    return thread


async def serve_with_parent(server, listener, application, stream):
    stopped = asyncio.Event()
    watch_parent(stream, asyncio.get_running_loop(), stopped)

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
