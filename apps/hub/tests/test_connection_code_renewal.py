import json

from fastapi.testclient import TestClient

from api.app import create_application
from core.local_auth import COOKIE_NAME
from runtime.paths import HubPaths
from runtime import pair


def test_only_operator_can_renew_and_existing_browser_session_survives(tmp_path):
    hub = create_application(paths=HubPaths.resolve(tmp_path), token='operator-secret',
        allowed_hosts={'testserver'}, allowed_origins={'http://testserver'}, environment='test')
    hub.local_auth.issue_code('first-login-code')
    with TestClient(hub.app) as client:
        origin = {'Origin': 'http://testserver'}
        endpoint = '/internal/auth/connection-code'
        assert client.post(endpoint).status_code == 401
        assert client.post(endpoint, headers={'Authorization': 'Bearer wrong'}).status_code == 401
        assert client.post('/api/v2/auth/local-session', json={'code': 'first-login-code'}, headers=origin).status_code == 200
        browser_cookie = client.cookies.get(COOKIE_NAME)
        assert client.post(endpoint, headers=origin).status_code == 401
        old_code = hub.local_auth.issue_code('unused-old-code')
        response = client.post(endpoint, headers={'Authorization': 'Bearer operator-secret'})
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert 'operator-secret' not in response.text
        code = response.json()['data']
        assert code['expiresInSeconds'] == 600
        assert hub.local_auth.valid(browser_cookie)
        assert client.get('/api/v2/auth/status').json()['data']['authenticated']
        assert client.post('/api/v2/auth/local-session', json={'code': old_code}, headers=origin).status_code == 401
        assert client.post('/api/v2/auth/local-session', json={'code': code['code']}, headers=origin).status_code == 200
        assert client.post('/api/v2/auth/local-session', json={'code': code['code']}, headers=origin).status_code == 401
        assert hub.local_auth.valid(browser_cookie)


def test_cli_uses_loopback_and_never_prints_operator_credential(tmp_path, monkeypatch, capsys):
    paths = HubPaths.resolve(tmp_path)
    paths.create()
    (paths.runtime / 'hub.json').write_text(json.dumps({'port': 8765, 'token': 'private-operator-token',
                                                       'baseUrl': 'https://must-not-contact.example'}))
    captured = {}

    class Response:
        status = 200
        def read(self):
            return b'{"success":true,"data":{"code":"new-code-123","expiresInSeconds":600}}'

    class Connection:
        def __init__(self, host, port, timeout):
            captured.update(host=host, port=port, timeout=timeout)
        def request(self, method, path, body, headers):
            captured.update(method=method, path=path, headers=headers)
        def getresponse(self):
            return Response()
        def close(self):
            captured['closed'] = True

    monkeypatch.setattr(pair, 'HTTPConnection', Connection)
    monkeypatch.setattr(pair.sys.stdout, 'isatty', lambda: True)
    monkeypatch.setattr('sys.argv', ['pair', '--data-dir', str(tmp_path)])
    pair.main()
    output = capsys.readouterr().out
    assert 'new-code-123' in output and 'private-operator-token' not in output
    assert captured['host'] == '127.0.0.1' and captured['port'] == 8765
    assert captured['path'] == '/internal/auth/connection-code'
    assert captured['headers']['Authorization'] == 'Bearer private-operator-token'
    assert captured['closed'] is True
