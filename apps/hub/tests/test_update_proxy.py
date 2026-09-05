from __future__ import annotations


def test_update_agent_absence_is_explicit(client, auth_headers) -> None:
    bootstrap = client.get("/api/v1/bootstrap", headers=auth_headers).json()["data"]
    assert bootstrap["features"]["updates"]["available"] is False
    assert "Update Agent" in bootstrap["features"]["updates"]["reason"]
    response = client.get("/api/v1/updates/state", headers=auth_headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "FEATURE_UNAVAILABLE"

