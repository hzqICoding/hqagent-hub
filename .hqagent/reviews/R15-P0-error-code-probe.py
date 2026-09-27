"""Read-only reproduction: a registry addition widens an unchanged rev1 DTO."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('protocol_generator_probe', ROOT / 'scripts/protocol/generate.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)
index = generator.load_schemas()
registries = generator.load_registries()
order = ['ErrorCode', 'RemoteError', 'RemoteWorkerHelloRejected']
frame = json.loads((ROOT / 'packages/protocol/fixtures/contracts/remote.RemoteWorkerHelloRejected.json').read_text(encoding='utf-8'))
frame['error']['code'] = 'REMOTE_HANDOVER_BUSY'


def accepts(registry, name):
    source = generator.emit_py(index, registry, order, '0.6.3')
    module = ModuleType(name)
    sys.modules[name] = module
    exec(compile(source, '<in-memory-generated-probe>', 'exec'), module.__dict__)
    try:
        module.RemoteWorkerHelloRejected.model_validate(frame)
        return True
    except ValidationError:
        return False


expanded = deepcopy(registries)
assert frame['error']['code'] not in expanded['error-codes']
expanded['error-codes'].append(frame['error']['code'])
original_accepts = accepts(registries, 'baseline_error_probe')
expanded_accepts = accepts(expanded, 'expanded_error_probe')
print(f'wireRevision={frame["wireRevision"]}; code={frame["error"]["code"]}')
print(f'unchanged rev1 DTO + existing registry accepts: {original_accepts}')
print(f'unchanged rev1 DTO + in-memory registry addition accepts: {expanded_accepts}')
assert original_accepts is False and expanded_accepts is True
assert (ROOT / 'packages/protocol/VERSION').read_text().strip() == '0.6.3'
print('No schema, registry, fixture, generated file or VERSION was written.')
