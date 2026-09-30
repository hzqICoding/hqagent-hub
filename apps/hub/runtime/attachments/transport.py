"""Suppress third-party transfer diagnostics, scoped to attachment HTTP I/O."""
from contextlib import asynccontextmanager
from contextvars import ContextVar
import logging


_private_transfer = ContextVar('attachment_private_transfer', default=False)


class _TransferFilter(logging.Filter):
    def filter(self, record):
        return not _private_transfer.get()


@asynccontextmanager
async def attachment_client(factory):
    client = factory()
    # httpx/httpcore diagnostics can include resource URLs and request/response
    # metadata. Leave unrelated traffic's logging policy unchanged.
    names = ['httpx', *[name for name in logging.Logger.manager.loggerDict
                        if name.startswith('httpcore')]]
    for name in names:
        logger = logging.getLogger(name)
        if not any(isinstance(value, _TransferFilter) for value in logger.filters):
            logger.addFilter(_TransferFilter())
    token = _private_transfer.set(True)
    try:
        async with client:
            yield client
    finally:
        _private_transfer.reset(token)
