"""Read-only Agent presentation without forcing execution-time discovery."""


async def agent_snapshot(port):
    method = getattr(type(port), 'cached_agents', None)
    if method is not None:
        return await method(port)
    # Legacy/injected ports keep their existing interface; production runtime
    # registration always uses AdapterManager's nonblocking snapshot path.
    return await port.list_agents()
