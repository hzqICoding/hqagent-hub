from __future__ import annotations

import json
from pathlib import Path

from runtime.instance import SingleInstanceError, SingleInstanceLock
from storage.database import Database


def test_v1_migrates_to_v2_and_consistent_backup_restores_data(tmp_path: Path) -> None:
    live_path = tmp_path / "hub.db"
    backup_path = tmp_path / "backup" / "hub-v1.db"
    database = Database(live_path)
    database.initialize(target_version=1)
    with database.transaction() as transaction:
        transaction.connection.execute(
            "INSERT INTO team_profiles(profile_id,name,scope,payload_json,updated_at) VALUES('p1','P1','global','{}','2026-09-05T00:00:00Z')"
        )
        transaction.connection.execute(
            "INSERT INTO tasks(task_id,workspace_id,profile_id,objective,status,source,payload_json,created_at,updated_at) "
            "VALUES('t1','w1','p1','obj','running','desktop','{}','2026-09-05T00:00:00Z','2026-09-05T00:00:00Z')"
        )
        transaction.connection.execute(
            "INSERT INTO sessions(session_id,task_id,workspace_id,role_id,agent_instance_id,purpose,reuse_policy,status,payload_json,last_used_at) "
            "VALUES('s1','t1','w1','architect','a1','plan','new_session','active','{}','2026-09-05T00:00:00Z')"
        )
        transaction.connection.execute("INSERT INTO settings(key,value_json) VALUES('x','{\"value\":1}')")
    database.backup(backup_path)
    database.initialize(target_version=2)
    assert database.schema_version == 2
    with database.transaction() as transaction:
        transaction.connection.execute("DELETE FROM tasks")
        transaction.connection.execute("DELETE FROM sessions")
        transaction.connection.execute("DELETE FROM team_profiles")
        transaction.connection.execute("DELETE FROM settings")
    database.restore_from_backup(backup_path)
    assert database.schema_version == 1
    with database.locked_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM team_profiles").fetchone()[0] == 1
        assert json.loads(connection.execute("SELECT value_json FROM settings WHERE key='x'").fetchone()[0]) == {"value": 1}
    database.close()


def test_single_instance_lock_releases_cleanly_twenty_times(tmp_path: Path) -> None:
    lock_path = tmp_path / "runtime" / "hub.lock"
    for _ in range(20):
        first = SingleInstanceLock(lock_path)
        first.acquire()
        second = SingleInstanceLock(lock_path)
        try:
            second.acquire()
            raise AssertionError("second instance acquired the lock")
        except SingleInstanceError:
            pass
        first.release()
        assert not lock_path.exists()


def test_drain_enters_maintenance_backs_up_and_returns_wait_pids(client, hub, auth_headers) -> None:
    response = client.post(
        "/internal/drain/start",
        headers=auth_headers,
        json={"timeoutSeconds": 1, "desktopPid": 12345, "updateAgentPid": 23456},
    )
    assert response.status_code == 200
    progress = response.json()["data"]
    assert progress["step"] == "ready"
    assert progress["backupCompleted"] is True
    assert {item["component"] for item in progress["waitPids"]} >= {"core", "desktop", "update-agent"}
    assert hub.drain.last_backup and hub.drain.last_backup.is_file()
    task = client.post("/api/v1/tasks", headers=auth_headers, json={"objective": "blocked", "workspaceId": "w"})
    assert task.status_code == 503
    assert task.json()["error"]["code"] == "HUB_MAINTENANCE"

