import json

import pytest
from starlette.websockets import WebSocketDisconnect

from conftest import FakeWorker
from server import wire


@pytest.mark.parametrize("version", ["0.6.0", "0.6.1", "99.2.3-preview+build.9"])
def test_package_version_is_diagnostic(env, paired, version):
    with paired.connect(paired.hello(protocolVersion=version)):
        assert paired.ack["type"] == "worker.hello_ack"
        assert paired.ack["wireRevision"] == 1
        assert "protocolVersion" not in paired.ack


@pytest.mark.parametrize("revision", [0, 6, 999, True, 1.0, "1", None])
def test_revision_negotiated_before_strict_dto(env, paired, revision):
    hello = paired.hello(wireRevision=revision)
    hello["futureField"] = "unknown"
    with paired.connect(hello):
        assert paired.ack["error"]["code"] == "REMOTE_PROTOCOL_UNSUPPORTED"
        assert paired.ack["supportedWireRevisions"] == [1, 2, 3, 4, 5]


def test_revision_one_remains_strict(env, paired):
    hello = paired.hello(futureField="forbidden")
    with paired.connect(hello):
        assert paired.ack["error"]["code"] == "VALIDATION_FAILED"
        assert paired.ack["supportedWireRevisions"] == [1, 2, 3, 4, 5]


def test_old_draft_not_auto_upgraded(env, paired):
    hello = paired.hello()
    del hello["wireRevision"]
    with paired.connect(hello):
        assert paired.ack["error"]["code"] == "REMOTE_PROTOCOL_UNSUPPORTED"


def test_oversized_frame_closed_1009(env, paired):
    with paired.connect():
        paired.ws.send_text(" " * (wire.MAX_FRAME_BYTES + 1))
        assert paired.receive()["error"]["code"] == "REMOTE_FRAME_TOO_LARGE"
        with pytest.raises(WebSocketDisconnect) as closed:
            paired.receive()
        assert closed.value.code == 1009


def test_hello_timeout(env, paired, monkeypatch):
    monkeypatch.setattr("server.worker.HELLO_TIMEOUT", 0.03)
    with env.client.websocket_connect("wss://testserver/ws/v2/worker", headers={"Authorization": "Bearer " + paired.secret}) as socket:
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()
