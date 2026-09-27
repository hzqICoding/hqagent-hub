from conftest import FakeWorker


def test_pair_and_offline_delivery(env, paired):
    first = paired.send(paired.conv)
    second = paired.send(paired.conv)
    assert first["conversationSeq"] == 1 and second["conversationSeq"] == 2
    assert first["deliveryState"] == "queued_offline"
    with paired.connect():
        frames = [paired.receive(), paired.receive()]
        assert [f["conversationSeq"] for f in frames] == [1, 2]
        accepted = paired.event("command.accepted", commandId=first["commandId"], conversationId=paired.conv,
                                receivedAt=frames[0]["createdAt"], status="accepted", resultRef=dict(runId="run-1", executionTaskId="task-1"))
        assert paired.emit(accepted)["position"]["seq"] == 2
    result = env.alice.get("/commands/" + first["commandId"]).json()["data"]
    assert result["status"] == "accepted"
    assert env.bob.get("/commands/" + first["commandId"]).status_code == 404


def test_q1_pairing_short_code_exception(env):
    worker = FakeWorker(env, env.alice)
    assert worker.register().json()["data"] == worker.challenge
    code = worker.challenge["pairCode"]
    preview = env.alice.post("/pairings/preview", dict(pairCode=code))
    assert preview.status_code == 200 and code not in preview.text
    first = worker.confirm()
    assert worker.confirm().json()["data"] == first.json()["data"]
    assert code not in first.text
    assert env.alice.post("/pairings/" + worker.challenge["pairRequestId"] + "/confirm", dict(pairCode=code)).status_code == 409
    assert env.bob.post("/pairings/" + worker.challenge["pairRequestId"] + "/confirm", dict(pairCode=code)).status_code == 404
    assert code not in env.alice.get("/devices").text
