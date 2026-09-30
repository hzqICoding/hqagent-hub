"""Real loopback 20MB upload/download RSS measurement, no whole-file buffers."""
import ctypes
import hashlib
import os
from pathlib import Path
import threading
import time

from protocol.generated import python as dto
from server.common import uid


def rss(pid):
    if os.name=='nt':
        from ctypes import wintypes as w
        class Counters(ctypes.Structure):
            _fields_=[('cb',w.DWORD),('faults',w.DWORD)]+[(n,ctypes.c_size_t) for n in ('peakWorking','working','peakPaged','paged','peakNonpaged','nonpaged','pagefile','peakPagefile')]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
        kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE;kernel.CloseHandle.argtypes=[w.HANDLE]
        psapi.GetProcessMemoryInfo.argtypes=[w.HANDLE,ctypes.c_void_p,w.DWORD]
        handle=kernel.OpenProcess(0x410,False,pid)
        if not handle:raise OSError('Cannot measure server RSS')
        try:
            result=Counters();result.cb=ctypes.sizeof(result)
            if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(result),result.cb):raise OSError('Cannot measure server RSS')
            return result.working
        finally:kernel.CloseHandle(handle)
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        if line.startswith('VmRSS:'):return int(line.split()[1])*1024
    raise OSError('RSS unavailable')


def attachment_smoke(client,conversation,pid):
    total=20000000;block=b'x'*65536
    def chunks():
        remaining=total
        while remaining:
            piece=block[:min(remaining,len(block))];remaining-=len(piece);yield piece
    expected=hashlib.sha256()
    for chunk in chunks():expected.update(chunk)
    baseline=rss(pid);samples=[baseline];stop=threading.Event()
    def sample():
        while not stop.wait(.01):samples.append(rss(pid))
    monitor=threading.Thread(target=sample);monitor.start()
    try:
        response=client.post('/api/v2/conversations/'+conversation+'/attachments',content=chunks(),headers={
            'Content-Length':str(total),'Content-Type':'application/octet-stream','X-File-Name':'large.txt','X-Content-Sha256':expected.hexdigest(),'Idempotency-Key':uid()})
        assert response.status_code==201, '20MB upload failed'
        value=response.json()['data'];dto.RemoteAttachmentView.model_validate(value)
        identifier=value['attachment']['attachmentId'];downloaded=0;actual=hashlib.sha256()
        with client.stream('GET','/api/v2/attachments/'+identifier+'/content') as received:
            assert received.status_code==200 and int(received.headers['content-length'])==total
            assert received.headers['content-disposition'].startswith('attachment')
            for chunk in received.iter_bytes(65536):downloaded+=len(chunk);actual.update(chunk)
        assert downloaded==total and actual.hexdigest()==expected.hexdigest()
        samples.append(rss(pid))
        deleted=client.delete('/api/v2/attachments/'+identifier,headers={'Idempotency-Key':uid()})
        assert deleted.status_code==200
    finally:stop.set();monitor.join(timeout=2)
    peak=max(samples);delta=peak-baseline
    assert delta < 16*1024*1024, 'Streaming RSS growth exceeded 16MiB budget'
    print(f'20MB streaming RSS: baseline={baseline} peak={peak} delta={delta} bytes; upload/download SHA256: PASS')
