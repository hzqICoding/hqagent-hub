import secrets
import json

import pytest
from fastapi.testclient import TestClient
from protocol.generated.python import ApiEnvelope

from server.app import create_app
from server.config import Settings


@pytest.fixture
def static_client(tmp_path):
    static = tmp_path / 'h5'
    static.mkdir()
    (static / 'index.html').write_text('<html>SPA shell</html>', encoding='utf-8')
    (static / '404.html').write_text('Asset not found', encoding='utf-8')
    (static / 'app.js').write_text('window.app = true;', encoding='utf-8')
    (static / 'notice').write_text('real extensionless file', encoding='utf-8')
    (static / 'api' / 'v2').mkdir(parents=True)
    (static / 'api' / 'v2' / 'missing').write_text('not an API response', encoding='utf-8')
    settings = Settings(tmp_path / 'hub.sqlite3', secrets.token_bytes(32), origin='https://testserver', static_dir=static)
    with TestClient(create_app(settings), base_url=settings.origin) as client:
        yield client


@pytest.mark.parametrize('path', ['/remote/chat', '/remote/chat/', '/remote/chat?conversation=123', '/route.with.dot/chat'])
def test_history_deep_link_uses_index(static_client, path):
    response = static_client.get(path)
    assert response.status_code == 200
    assert response.text == '<html>SPA shell</html>'
    assert response.headers['content-type'].startswith('text/html')


def test_existing_assets_and_extensionless_files_are_unchanged(static_client):
    response = static_client.get('/app.js')
    assert response.status_code == 200 and response.text == 'window.app = true;'
    assert static_client.get('/notice').text == 'real extensionless file'
    assert static_client.head('/app.js').status_code == 200


@pytest.mark.parametrize('path', ['/api/v2/missing', '/api/missing.js', '/ws/missing', '/api', '/ws'])
def test_reserved_namespace_404_is_api_envelope(static_client, path):
    response = static_client.get(path)
    assert response.status_code == 404
    ApiEnvelope.model_validate(response.json())
    assert response.json()['success'] is False
    assert response.json()['error']['code'] == 'NOT_FOUND'
    assert response.headers['content-type'].startswith('application/json')


@pytest.mark.parametrize('path', ['/missing.js', '/assets/missing.css', '/images/missing.svg', '/.env'])
def test_missing_asset_with_extension_stays_404(static_client, path):
    response = static_client.get(path)
    assert response.status_code == 404 and 'SPA shell' not in response.text


def test_only_get_requests_receive_spa_fallback(static_client):
    assert static_client.head('/remote/chat').status_code == 404
    response = static_client.post('/remote/chat', json={})
    assert response.status_code >= 400 and 'SPA shell' not in response.text
    assert static_client.get('/api/v2/auth/session').json()['data'] == {'authenticated': False}


@pytest.mark.parametrize('path', ['/remote/chat', '/app.js', '/missing.js', '/api/v2/missing'])
def test_static_and_api_request_ids_have_one_completion_record(static_client, path, caplog):
    caplog.set_level('INFO', logger='hqremote')
    response = static_client.get(path)
    record, = [json.loads(r.message) for r in caplog.records if r.name == 'hqremote']
    assert response.headers['x-request-id'] == record['requestId']
    assert record['status'] == response.status_code
    assert record['operation'] == ('unmatched' if path.startswith('/api/') else 'static')
    if path.startswith('/api/'):
        assert response.json()['requestId'] == record['requestId']
