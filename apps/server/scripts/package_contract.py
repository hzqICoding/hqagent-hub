"""Copy frozen protocol publication into the independently deployable server package."""
import json
from pathlib import Path
import shutil

import yaml

root = Path(__file__).resolve().parents[3]
protocol = root / 'packages/protocol'
target = Path(__file__).resolve().parents[1] / 'server/resources'
target.mkdir(exist_ok=True)
shutil.copyfile(protocol / 'openapi/remote-hub.v2.bundle.json', target / 'remote-hub.v2.bundle.json')
registry = yaml.safe_load((protocol / 'registry/error-codes.yaml').read_text(encoding='utf-8'))['errors']
guide = yaml.safe_load((protocol / 'remote/http-error-guidance.yaml').read_text(encoding='utf-8'))['errors']
errors = {e['code']: dict(status=e['http'], retryable=e['retryable'], message=guide[e['code']]['message']) for e in registry}
(target / 'http-errors.json').write_text(json.dumps(errors, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'Packaged OpenAPI and {len(errors)} HTTP error mappings')
