"""Release resources, independent of source checkout and deployment directory."""
import json
from importlib.resources import files

RESOURCES = files('server').joinpath('resources')
OPENAPI = json.loads(RESOURCES.joinpath('remote-hub.v2.bundle.json').read_text(encoding='utf-8'))
HTTP_ERRORS = json.loads(RESOURCES.joinpath('http-errors.json').read_text(encoding='utf-8'))
