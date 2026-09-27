from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class SPAStaticFiles(StaticFiles):
    """Serve real assets normally; only extensionless GET routes use the SPA shell."""

    async def get_response(self, path, scope):
        route = path.replace('\\', '/').lstrip('/')
        if route.split('/', 1)[0] in {'api', 'ws'}:
            # Keep reserved namespaces in the parent app's ApiEnvelope 404 handler.
            raise HTTPException(status_code=404)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            response = None
        if response is not None and response.status_code != 404:
            return response
        if scope['method'] == 'GET' and '.' not in route.rstrip('/').rsplit('/', 1)[-1]:
            return await super().get_response('index.html', scope)
        if response is not None:
            return response
        raise HTTPException(status_code=404)
