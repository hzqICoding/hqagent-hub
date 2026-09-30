import asyncio
from datetime import datetime,timedelta,timezone
import io
import json
import os
from pathlib import Path
import socket

import httpx
import pytest
import uvicorn

from protocol.generated.python import HubRuntimeDescriptor, PROTOCOL_VERSION
from runtime import cli
from runtime.paths import HubPaths
from runtime.remote.link import PairingHTTP
from runtime.remote.worker import NoRedirectConnect
from runtime.workspaces import WorkspaceService
from storage.workspaces import WorkspaceRepository
from remote_support import System,FakeRemoteServer,TOKEN,until


class Terminal(io.StringIO):
    def isatty(self):return True


def descriptor(path,port):
    value=HubRuntimeDescriptor(schemaVersion=1,instanceId='cli-test',port=port,token=TOKEN,pid=os.getpid(),
        baseUrl='https://untrusted.example',appVersion='0.1.0',protocolVersion=PROTOCOL_VERSION,
        startedAt=datetime.now(timezone.utc).isoformat())
    dest=HubPaths.resolve(path).runtime/'hub.json';dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(value.model_dump_json(by_alias=True),encoding='utf-8');dest.chmod(0o600)


def test_cli_all_operations_use_real_authenticated_loopback_api(tmp_path,monkeypatch,caplog):
    async def scenario():
        system=System(tmp_path)
        system.ports.workspaces=WorkspaceService(WorkspaceRepository(system.db))
        monkeypatch.setenv('GIT_CEILING_DIRECTORIES',str(tmp_path))
        class Discovery:
            async def discover(self):return []
        system.ports.agents=Discovery()
        listener=socket.socket();listener.bind(('127.0.0.1',0))
        port=listener.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(system.application.app,log_config=None,access_log=False,log_level='critical',lifespan='off'))
        task=asyncio.create_task(server.serve(sockets=[listener]))
        try:
            await until(lambda:server.started)
            descriptor(tmp_path/'data-root',port)
            client=cli.LocalClient(tmp_path/'data-root')
            output=Terminal()
            async def run(*args):
                output.seek(0);output.truncate()
                await asyncio.to_thread(cli.execute,cli.parser().parse_args(args),client,output)
                return output.getvalue()
            assert json.loads(await run('remote','status'))['state']=='unpaired'
            project=tmp_path/'project';project.mkdir()
            added=json.loads(await run('workspace','add',str(project)))
            assert added['path']==str(project) and not added['capabilities']['canRunWriteTasks']
            assert json.loads(await run('workspace','list'))[0]['id']==added['id']
            assert json.loads(await run('agents','discover'))==[]
            root=json.loads(await run('roots','add',str(tmp_path)))['roots'][0]
            assert json.loads(await run('roots','list'))['roots'][0]['rootId']==root['rootId']
            assert json.loads(await run('roots','remove',root['rootId']))['roots']==[]
            async with FakeRemoteServer(revision=3) as remote:
                system.link.http=PairingHTTP(system.link.vault,transport=httpx.AsyncHTTPTransport(verify=remote.client_tls))
                system.worker.connector=lambda uri,**kwargs:NoRedirectConnect(uri,ssl=remote.client_tls,**kwargs)
                remote.claimed=True
                await system.worker.start()
                pairing=await run('remote','pair','--server',remote.origin,'--device-name','headless')
                assert '配对短码:' in pairing and '配对完成' in pairing and len(pairing.splitlines())>10
                code=pairing.split('配对短码: ')[1].splitlines()[0]
                assert code not in caplog.text and TOKEN not in pairing+caplog.text
                state=json.loads(await run('remote','status'))
                assert state['state']=='paired' and 'pairCode' not in state
                assert json.loads(await run('remote','unlink'))['state']=='unpaired'
        finally:
            await system.close();server.should_exit=True
            await asyncio.wait_for(task,5);listener.close()
    asyncio.run(scenario())


def test_cli_declines_nonterminal_pairing_and_error_reflection():
    class Client:
        def request(self,*args):raise AssertionError('must not send')
    with pytest.raises(cli.CLIError):cli.pair(Client(),'https://example.test','machine',io.StringIO())
    assert cli.printable({'pairCode':'ABCD2345','token':'SECRET','authorization':'Bearer xx','state':'pairing'})=={'state':'pairing'}


@pytest.mark.parametrize('case',['cancel','expired','conflict'])
def test_pair_cancellation_expiry_and_changed_request_are_safe(case):
    current={'state':'pairing','serverOrigin':'https://example.test','deviceName':'cli','pairRequestId':'pair-request',
        'pairCode':'ABCD2345','expiresAt':(datetime.now(timezone.utc)+timedelta(seconds=-1 if case=='expired' else 30)).isoformat()}
    calls=[]
    class Client:
        def request(self,method,path,value=None):
            calls.append((method,path))
            return {**current,'pairRequestId':'other-request'} if case=='conflict' and method=='GET' else current
    def interrupt(_seconds):raise KeyboardInterrupt()
    with pytest.raises(cli.CLIError):cli.pair(Client(),current['serverOrigin'],'cli',Terminal(),sleep=interrupt)
    assert (('DELETE','/remote/pairing') in calls)==(case=='cancel')


def test_descriptor_remote_base_url_never_controls_connection(tmp_path,monkeypatch):
    descriptor(tmp_path,18999)
    calls=[]
    class Connection:
        def __init__(self,host,port,**kwargs):calls.append((host,port))
        def request(self,*args,**kwargs):calls.append(kwargs['headers'])
        def getresponse(self):
            class Response:
                status=302
                def read(self,_limit):return b'PRIVATE_REDIRECT'
            return Response()
        def close(self):pass
    monkeypatch.setattr(cli,'HTTPConnection',Connection)
    with pytest.raises(cli.CLIError) as error:cli.LocalClient(tmp_path).request('GET','/remote/link')
    assert calls[0]==('127.0.0.1',18999) and len(calls)==2
    assert TOKEN not in str(error.value) and 'PRIVATE_REDIRECT' not in str(error.value)
