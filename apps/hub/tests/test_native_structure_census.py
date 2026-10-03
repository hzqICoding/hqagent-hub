"""Synthetic-only checks for the local, metadata-only census utility."""
import importlib.util
import json
from pathlib import Path

from test_r3_native import fixture_history


def utility():
    spec = importlib.util.spec_from_file_location('native_structure_census',
        Path(__file__).resolve().parents[3] / '.hqagent' / 'native_structure_census.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_census_projection_does_not_decode_body_strings(monkeypatch, tmp_path):
    module = utility()
    original = module.json.loads
    secret = 'PRIVATE_BODY_DO_NOT_DECODE'
    raw = json.dumps({'type': 'user', 'version': '2.1.251', 'uuid': 'synthetic-id',
        'cwd': str(tmp_path), 'message': {'role': 'user', 'content': secret},
        'aiTitle': secret, 'input': {'private': secret, 'type': secret, 'cwd': secret,
                                   'version': secret}, 'output': secret}).encode()

    def guarded(value, *args, **kwargs):
        assert secret not in str(value)
        return original(value, *args, **kwargs)

    monkeypatch.setattr(module.json, 'loads', guarded)
    projected = module.project(raw)
    assert projected['message']['content'] == 'X'
    assert projected['version'] == '2.1.251'
    assert secret not in str(projected)


def test_census_reports_shapes_and_fixed_failure_categories_only(tmp_path):
    module = utility()
    root = tmp_path / 'records'
    path = fixture_history(root, tmp_path, version='0.111.0', text='PRIVATE_BODY_SENTINEL')
    result = module.census({'codex': root})['codex:0.111.0']
    assert result['validation']['pass'] == 4
    assert not any(count for kind, count in result['validation'].items() if kind != 'pass')
    assert result['files'] == {'total': 1, 'pass': 1}
    assert result['fields']['response_item']['payload.content[].text'] == ['string']
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[1]['payload']['content'][0]['text'] = {'private': 'PRIVATE_BODY_SENTINEL'}
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    report = module.census({'codex': root})
    encoded = json.dumps(report)
    assert 'PRIVATE_BODY_SENTINEL' not in encoded and str(tmp_path) not in encoded
    assert '00000000-0000-4000-8000-000000000001' not in encoded
    assert report['codex:0.111.0']['validation']['消息text不是字符串'] == 1
    assert report['codex:0.111.0']['files']['fail'] == 1
