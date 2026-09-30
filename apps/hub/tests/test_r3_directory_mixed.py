import asyncio
import json
import os
from contextlib import contextmanager

from protocol.generated.python import DirectoryListingPage
from core.errors import HubError
from runtime.native import paths
from runtime.workspaces import WorkspaceService
from storage.workspaces import WorkspaceRepository
from remote_support import System, FakeRemoteServer, until, command_events
from test_r3_roots import configure, listing
from test_r3_native import setup_native
from test_r3_wire import query, resource, permission


def test_mixed_directory_skips_unsafe_children_but_preserves_target_and_registration_guards(tmp_path,monkeypatch):
    async def scenario():
        system=System(tmp_path)
        root_path=tmp_path/'root'; root_path.mkdir()
        outside=tmp_path/'outside-private'; outside.mkdir()
        escape=root_path/'escape-private'
        blocked=root_path/'denied-private'
        invalid=root_path/'unopenable-private'
        for child in (escape,blocked,invalid,root_path/'plain',root_path/'gitproj'):
            child.mkdir()
        (root_path/'gitproj'/'.git').mkdir()
        try:
            setup_native(system,tmp_path/'empty-native')
            system.chat.ports.workspaces=WorkspaceService(WorkspaceRepository(system.db))
            monkeypatch.setenv('GIT_CEILING_DIRECTORIES',str(tmp_path))
            root=configure(system,root_path)
            original=paths._open_directory
            @contextmanager
            def guarded(path):
                # Inject OS open failures rather than editing user/host ACLs.
                if path==blocked:
                    raise PermissionError('synthetic denial')
                if path==invalid:
                    raise NotADirectoryError('synthetic replacement')
                with original(path) as identity:
                    yield identity
            async with FakeRemoteServer(revision=3) as server:
                await system.pair(server,start=True)
                old=listing(system,root)
                tokens={entry.name:entry.directory_token for entry in old.entries}
                escape.rmdir()
                if os.name=='nt':
                    import _winapi
                    _winapi.CreateJunction(str(outside),str(escape))
                else:
                    escape.symlink_to(outside,target_is_directory=True)
                monkeypatch.setattr(paths,'_open_directory',guarded)
                await server.send(query(system,server,'query.directory.list',{'rootId':root.root_id,'rootVersion':1},'mixed'))
                await until(lambda:any(f.get('queryId')=='mixed' and f['type'] in {'query.result.segment','query.failed'} for f in server.frames))
                parts=[f for f in server.frames if f.get('queryId')=='mixed']
                assert all(f['type']=='query.result.segment' for f in parts),parts
                page=DirectoryListingPage.model_validate_json(''.join(f['text'] for f in sorted(parts,key=lambda f:f['segmentIndex'])))
                assert [entry.name for entry in page.entries]==['gitproj','plain']
                assert page.entries[0].is_git_repository and not page.entries[1].is_git_repository
                raw=json.dumps(parts)
                assert all(name not in raw for name in ('escape-private','outside-private','denied-private','unopenable-private'))
                with system.db.locked_connection() as db:
                    audit=json.loads(db.execute("SELECT payload_json FROM events WHERE type='remote.directory.audited' ORDER BY seq DESC LIMIT 1").fetchone()[0])
                assert audit['skippedCount']==3 and audit['resultCode']=='OK'
                assert set(audit)=={'requestId','operation','rootId','resultCode','skippedCount'}
                # Requesting the unsafe item itself is still a failed target,
                # not an empty successful page or an authorized workspace.
                for name,code in (('escape-private','REMOTE_PATH_OUTSIDE_ROOT'),('denied-private','REMOTE_DIRECTORY_CHANGED')):
                    try:
                        listing(system,root,directoryToken=tokens[name])
                        assert False,'unsafe target accepted'
                    except HubError as error:
                        assert error.code==code
                rejected=resource(system,'workspace.register',{'rootId':root.root_id,'rootVersion':1,'directoryToken':tokens['escape-private']},'escape-registration')
                await server.send(rejected)
                await until(lambda:command_events(server,'escape-registration','command.rejected'))
                assert command_events(server,'escape-registration','command.rejected')[-1]['error']['code']=='REMOTE_PATH_OUTSIDE_ROOT'
                normal=resource(system,'workspace.register',{'rootId':root.root_id,'rootVersion':1,'directoryToken':page.entries[1].directory_token},'normal-registration')
                await server.send(normal)
                await until(lambda:command_events(server,'normal-registration','command.received'))
                await server.send(permission(normal,command_events(server,'normal-registration','command.received')[-1]))
                await until(lambda:command_events(server,'normal-registration','command.completed'))
                ref=command_events(server,'normal-registration','command.completed')[-1]['resourceRef']
                workspace=await system.chat.ports.workspaces.get_workspace(ref['workspaceId'])
                assert workspace.path==str(root_path/'plain') and not workspace.capabilities.can_run_write_tasks
                assert not server.errors
        finally:
            if escape.exists():
                os.rmdir(escape) if os.name=='nt' else escape.unlink()
            await system.close()
    asyncio.run(scenario())
