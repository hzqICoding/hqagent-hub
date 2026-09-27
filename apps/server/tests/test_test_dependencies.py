from pathlib import Path
import tomllib


def test_test_extra_is_declared_and_matches_available_hub_lock_pins():
    root = Path(__file__).resolve().parents[3]
    project = tomllib.loads((root / 'apps/server/pyproject.toml').read_text(encoding='utf-8'))['project']
    extra = project['optional-dependencies']['test']
    assert set(extra) == {'pytest==8.4.2', 'httpx==0.28.1', 'PyYAML==6.0.3'}
    locked = (root / 'apps/hub/requirements.local-lock.txt').read_text(encoding='utf-8').splitlines()
    for pin in extra:
        name = pin.split('==')[0].lower()
        existing = [entry for entry in locked if entry.lower().startswith(name + '==')]
        if name in {'pytest', 'httpx'} or existing:
            assert existing == [pin]
    assert project['dependencies'] == ['fastapi>=0.141.1', 'uvicorn', 'websockets', 'pydantic>=2']
