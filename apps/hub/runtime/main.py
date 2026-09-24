from __future__ import annotations

import argparse
import asyncio
import os
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from protocol.generated.python import HubRuntimeDescriptor

from api.app import create_application
from core.constants import APP_VERSION, PROTOCOL_VERSION
from core.security import generate_startup_token
from runtime.composition import bind_ports, build_ports
from runtime.descriptor import RuntimeDescriptorFile
from runtime.instance import SingleInstanceLock
from runtime.paths import HubPaths


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HQAgent-Hub Local Hub")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--environment", choices=("production", "development", "test"), default="production")
    parser.add_argument("--port", type=int, default=0, help="回环监听端口，默认随机")
    parser.add_argument("--web-dir", type=Path, help="前端构建产物目录，可选")
    return parser.parse_args()


async def run(data_dir: Path | None = None, environment: str = "production", *, port: int = 0, web_dir: Path | None = None) -> None:
    paths = HubPaths.resolve(data_dir)
    paths.create()
    instance_id = f"hub_{uuid.uuid4().hex}"
    token = generate_startup_token()
    started_at = datetime.now(timezone.utc)
    descriptor_file = RuntimeDescriptorFile(paths.runtime / "hub.json")
    lock = SingleInstanceLock(paths.runtime / "hub.lock")
    lock.acquire()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    listener.listen(128)
    port = int(listener.getsockname()[1])
    ports = build_ports()
    application = create_application(
        paths=paths,
        token=token,
        ports=ports,
        instance_id=instance_id,
        started_at=started_at,
        environment=environment,
    )
    # Database 由 create_application 内部创建，所以补齐要放在它之后。
    await bind_ports(application, ports)
    if environment == "development":
        # Existing middleware receives its set by reference at initialization.
        for middleware in application.app.user_middleware:
            if middleware.cls.__name__ == "LocalBoundaryMiddleware":
                middleware.kwargs["allowed_origins"] = set(middleware.kwargs["allowed_origins"]) | {
                    "http://localhost:5173", "http://127.0.0.1:5173",
                }
    if web_dir is not None:
        from fastapi.staticfiles import StaticFiles
        from starlette.exceptions import HTTPException

        class LocalWebFiles(StaticFiles):
            async def get_response(self, path, scope):
                if path.startswith(("api/", "internal/", "ws/")):
                    raise HTTPException(404)
                try:
                    return await super().get_response(path, scope)
                except HTTPException as error:
                    if error.status_code != 404 or "." in Path(path).name:
                        raise
                    return await super().get_response("index.html", scope)

        application.app.mount("/", LocalWebFiles(directory=str(web_dir.resolve()), html=True), name="local-web")
    code = application.local_auth.issue_code()
    print(f"Local Hub: http://127.0.0.1:{port}", flush=True)
    print(f"Local connection code (one use, 10 minutes): {code}", flush=True)
    descriptor = HubRuntimeDescriptor.model_validate(
        {
            "schemaVersion": 1,
            "instanceId": instance_id,
            "port": port,
            "token": token,
            "pid": os.getpid(),
            "baseUrl": f"http://127.0.0.1:{port}",
            "appVersion": APP_VERSION,
            "protocolVersion": PROTOCOL_VERSION,
            "startedAt": started_at.isoformat().replace("+00:00", "Z"),
        }
    )
    descriptor_file.write(descriptor)
    config = uvicorn.Config(
        application.app,
        host="127.0.0.1",
        port=port,
        access_log=False,
        log_level="warning",
        timeout_graceful_shutdown=12,
    )
    server = uvicorn.Server(config)
    try:
        await server.serve(sockets=[listener])
    finally:
        descriptor_file.remove(instance_id)
        lock.release()
        listener.close()


def main() -> None:
    args = _parse_args()
    asyncio.run(run(args.data_dir, args.environment, port=args.port, web_dir=args.web_dir))


if __name__ == "__main__":
    main()
