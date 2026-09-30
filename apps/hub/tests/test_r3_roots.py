from __future__ import annotations

import asyncio
import json
import os

import pytest
from protocol.generated.python import LocalAuthorizedRootsInput, LocalAuthorizedRootsView, DirectoryListingInput
from core.errors import HubError
from runtime.native.paths import absolute_directory, directory_lease
from remote_support import System
from test_remote_cookie_routes import login, ORIGIN


def configure(system, path):
    return system.worker.roots.replace(LocalAuthorizedRootsInput(expectedVersion=1,
        roots=[{"path": str(path), "displayName": "Projects"}]), "roots").roots[0]


def listing(system, root, **extra):
    return system.worker.roots.listing(DirectoryListingInput(rootId=root.root_id, rootVersion=root.version,
        **extra), "synthetic-list-request")


def test_local_roots_shared_cookie_bearer_cas_and_removal_invalidates_references(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            directory = tmp_path / "projects"
            directory.mkdir()
            response = await system.local.get("/api/v1/remote/authorized-roots")
            assert response.status_code == 200
            assert response.json()["data"] == {"version": 1, "roots": []}
            assert response.headers["cache-control"] == "no-store"
            await login(system)
            path = "/api/v2/remote/authorized-roots"
            payload = {"expectedVersion": 1, "roots": [{"displayName": "Projects", "path": str(directory)}]}
            denied = await system.local.put(path, json=payload, headers={"Idempotency-Key": "set"})
            assert denied.status_code == 403
            headers = {"Origin": ORIGIN, "Idempotency-Key": "set"}
            changed = await system.local.put(path, json=payload, headers=headers)
            assert changed.status_code == 200, changed.text
            view = LocalAuthorizedRootsView.model_validate(changed.json()["data"])
            replay = await system.local.put(path, json=payload, headers=headers)
            assert replay.json()["data"] == changed.json()["data"]
            stale = await system.local.put(path, json=payload, headers={**headers, "Idempotency-Key": "stale"})
            assert stale.status_code == 409
            assert system.worker.roots.catalog() == [{"rootId": view.roots[0].root_id, "displayName": "Projects", "version": 1}]
            assert str(directory) not in json.dumps(system.worker.roots.catalog())
            page = listing(system, view.roots[0])
            removed = await system.local.put(path, json={"expectedVersion": 2, "roots": []},
                headers={**headers, "Idempotency-Key": "remove"})
            assert removed.status_code == 200
            with pytest.raises(HubError) as error:
                with system.worker.roots.selected(view.roots[0].root_id, 1, page.directory_token):
                    pass
            assert error.value.code == "REMOTE_ROOT_NOT_AUTHORIZED"
            system.local.cookies.clear()
            assert (await system.local.get(path)).status_code == 401
        finally:
            await system.close()
    asyncio.run(scenario())


def test_directory_page_only_contains_directories_and_cursor_pins_snapshot(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            root_path = tmp_path / "root"
            root_path.mkdir()
            (root_path / "file-secret.txt").write_text("never return")
            (root_path / "shortcut.lnk").write_bytes(b"not executed")
            for number in range(103):
                (root_path / f"directory-{number:03d}").mkdir()
            root = configure(system, root_path)
            first = listing(system, root, limit=100)
            assert len(first.entries) == 100 and first.has_more
            second = listing(system, root, directoryToken=first.directory_token, cursor=first.next_cursor, limit=100)
            assert len(second.entries) == 3 and second.has_more is False
            assert not any(e.name.endswith((".txt", ".lnk")) for e in first.entries)
            assert "file-secret" not in first.model_dump_json(by_alias=True)
            (root_path / "new-directory").mkdir()
            with pytest.raises(HubError) as error:
                listing(system, root, cursor=first.next_cursor)
            assert error.value.code == "REMOTE_DIRECTORY_CHANGED"
            with system.db.locked_connection() as db:
                audit = [json.loads(r[0]) for r in db.execute("SELECT payload_json FROM events WHERE type='remote.directory.audited'")]
            assert len(audit) == 3
            assert all(a["requestId"] == "synthetic-list-request" for a in audit)
            assert all(set(a) == {"requestId", "operation", "rootId", "resultCode"} for a in audit)
            assert "directory-" not in json.dumps(audit)
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("path", ["../outside", "E:relative", r"\\host\share", r"\\?\E:\root",
    r"\\.\C:\root", "E:/root/../outside", "E:/root/file:stream", "E:/root/ambiguous.", "E:/root/a ", "E:/root/\x00"])
def test_unsafe_directory_paths_are_rejected_without_echo(path):
    with pytest.raises(HubError) as error:
        absolute_directory(path)
    assert error.value.code == "REMOTE_PATH_OUTSIDE_ROOT"
    assert path not in error.value.message and error.value.detail is None


def test_junction_or_symlink_cannot_escape_authorized_root(tmp_path):
    async def scenario():
        system = System(tmp_path)
        root_path, outside = tmp_path / "root", tmp_path / "outside"
        root_path.mkdir(); outside.mkdir()
        link = root_path / "escape"
        try:
            root = configure(system, root_path)
            if os.name == "nt":
                import _winapi
                _winapi.CreateJunction(str(outside), str(link))
            else:
                link.symlink_to(outside, target_is_directory=True)
            page = listing(system, root)
            assert page.entries == []
            assert "escape" not in page.model_dump_json() and str(outside) not in page.model_dump_json()
            with pytest.raises(HubError) as error:
                with directory_lease(str(link), root=root_path):
                    pass
            assert error.value.code == "REMOTE_PATH_OUTSIDE_ROOT"
            assert str(outside) not in error.value.message
        finally:
            if link.exists():
                os.rmdir(link) if os.name == "nt" else link.unlink()
            await system.close()
    asyncio.run(scenario())


def test_directory_token_rejects_replaced_identity_and_expiry(tmp_path):
    async def scenario():
        system = System(tmp_path)
        try:
            root_path = tmp_path / "root"
            child = root_path / "child"
            child.mkdir(parents=True)
            root = configure(system, root_path)
            page = listing(system, root)
            token = page.entries[0].directory_token
            child.rename(root_path / "renamed")
            child.mkdir()
            with pytest.raises(HubError) as changed:
                with system.worker.roots.selected(root.root_id, 1, token):
                    pass
            assert changed.value.code == "REMOTE_DIRECTORY_CHANGED"
            clock = system.worker.roots.clock()
            system.worker.roots.clock = lambda: clock + 901
            with pytest.raises(HubError) as expired:
                listing(system, root, directoryToken=page.directory_token)
            assert expired.value.code == "REMOTE_DIRECTORY_CHANGED"
        finally:
            await system.close()
    asyncio.run(scenario())


@pytest.mark.skipif(os.name != "nt", reason="Windows deny-delete lease semantics")
def test_windows_directory_handle_prevents_replacement_while_held(tmp_path):
    child = tmp_path / "leased"
    child.mkdir()
    with directory_lease(str(child)):
        with pytest.raises(PermissionError):
            child.rename(tmp_path / "replacement")
    child.rename(tmp_path / "replacement")
