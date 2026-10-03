"""Ephemeral revision-3 queries. No receipt ledger, reliable seq or body cache."""
import asyncio
import hashlib
import threading

from protocol.generated.python import DirectoryListingInput, NativeReadInput
from core.errors import HubError
from runtime.remote.commands import error_view
from runtime.remote.deadline import instant
from runtime.remote.wire import canonical
from adapters.history import CANCEL_READ


class QueryChannel:
    def __init__(self, worker, connection_id, send):
        self.worker, self.connection_id, self.send = worker, connection_id, send
        self.tasks = {}
        self.closed = False

    def guard(self, frame):
        identity, link = self.worker.repo.get("identity"), self.worker.repo.get("link")["view"]
        if (self.closed or frame["connectionId"] != self.connection_id or frame["workerEpoch"] != identity["epoch"] or
                frame["expectedWorkerStoreId"] != identity["store"] or frame["targetWorkerId"] != link.get("workerId") or link["state"] != "paired"):
            raise HubError("REMOTE_DEVICE_OFFLINE", "临时查询的连接身份已失效")
        if not self.worker.sync.settings().mirror_enabled:
            raise HubError("REMOTE_SYNC_DISABLED", "同步已关闭")
        try:
            remaining = instant(frame["expiresAt"]) - self.worker.delivery.clock.upper()
        except HubError:
            raise HubError("REMOTE_QUERY_TIMEOUT", "查询时间界限已失效") from None
        if not 0 < remaining <= 10:
            raise HubError("REMOTE_QUERY_TIMEOUT", "临时查询已过期")
        return remaining

    def common(self, frame):
        return {"wireRevision":frame["wireRevision"],"queryId":frame["queryId"],"requestId":frame["requestId"],
            "connectionId":frame["connectionId"],"workerId":frame["targetWorkerId"],
            "workerStoreId":frame["expectedWorkerStoreId"],"workerEpoch":frame["workerEpoch"]}

    async def submit(self, frame):
        if self.worker.link.contains_credentials(canonical(frame)):
            raise HubError("REMOTE_DEVICE_AUTH_FAILED", "临时查询包含不允许传播的凭据")
        if frame["queryId"] in self.tasks:
            return
        if len(self.tasks) >= 4:
            await self.send({"type":"query.failed",**self.common(frame),"error":error_view("REMOTE_RATE_LIMITED")})
            return
        job = asyncio.create_task(self.execute(frame))
        self.tasks[frame["queryId"]] = job
        def completed(done):
            self.tasks.pop(frame["queryId"],None)
            if not done.cancelled():
                done.exception()  # Transport loss must not dump query locals.
        job.add_done_callback(completed)

    async def execute(self, frame):
        cancellation = threading.Event()
        token = CANCEL_READ.set(cancellation)
        try:
            async with asyncio.timeout(self.guard(frame)):
                if frame["type"] == "query.native.messages":
                    value = NativeReadInput.model_validate(frame["payload"])
                    result = await self.worker.native.read(value.native_session_id, revision=value.source_revision,
                        before=value.before, limit=value.limit,scope=(frame["expectedWorkerStoreId"],self.worker.sync.settings().sync_generation))
                    result_type = "native.messages"
                else:
                    value = DirectoryListingInput.model_validate(frame["payload"])
                    result = await asyncio.to_thread(self.worker.roots.listing,value,frame["requestId"])
                    result_type = "directory.list"
                text = canonical(result.model_dump(mode="json",by_alias=True,exclude_none=True))
                body = text.encode()
                if len(body) > 1024 * 1024:
                    raise HubError("REMOTE_QUERY_TOO_LARGE", "临时查询结果超过上限")
                chunks = [text[i:i+16000] for i in range(0,len(text),16000)]
                if len(chunks) > 128:
                    raise HubError("REMOTE_QUERY_TOO_LARGE", "临时查询分段超过上限")
                for index, chunk in enumerate(chunks):
                    self.guard(frame)
                    if result_type == "directory.list":
                        self.worker.roots._root(value.root_id,value.root_version)
                    else:
                        await self.worker.native.registered(self.worker.native.row(value.native_session_id))
                    await self.send({"type":"query.result.segment",**self.common(frame),"resultType":result_type,
                        "segmentIndex":index,"segmentCount":len(chunks),"totalUtf8Bytes":len(body),
                        "contentSha256":hashlib.sha256(body).hexdigest(),"text":chunk})
        except (HubError, TimeoutError) as error:
            if not self.closed:
                await self.send({"type":"query.failed",**self.common(frame),
                    "error":error_view(error.code if isinstance(error,HubError) else "REMOTE_QUERY_TIMEOUT")})
        except Exception:
            if not self.closed:
                await self.send({"type":"query.failed",**self.common(frame),"error":error_view("INTERNAL")})
        finally:
            cancellation.set()
            CANCEL_READ.reset(token)

    def cancel_pending(self):
        for task in list(self.tasks.values()):
            task.cancel()

    async def close(self):
        self.closed = True
        jobs = list(self.tasks.values())
        for job in jobs:
            job.cancel()
        await asyncio.gather(*jobs,return_exceptions=True)
        self.tasks.clear()
