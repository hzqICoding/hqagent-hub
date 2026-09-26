import pytest


@pytest.mark.parametrize('body', [
    {'title': None, 'workspaceId': 'ws', 'sceneId': 'analyze'},
    {'title': {'secret': 'PRIVATE_INPUT_MARKER'}, 'workspaceId': 'ws', 'sceneId': 'analyze'},
    {'title': 'test', 'workspaceId': 'ws'},
])
def test_invalid_request_returns_sanitized_422(client, auth_headers, body):
    response = client.post('/api/v2/conversations', json=body,
        headers={**auth_headers, 'Idempotency-Key': 'invalid-request'})
    assert response.status_code == 422
    value = response.json()
    assert value['error']['code'] == 'VALIDATION_FAILED'
    assert 'PRIVATE_INPUT_MARKER' not in response.text
    errors = value['error']['detail']['errors']
    assert errors
    assert all(set(error) <= {'type', 'loc', 'msg'} for error in errors)
