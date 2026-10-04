"""Read-only process evidence for legacy PI starts that returned no handle.

Never starts a helper, kills a process, or treats an unreadable process as absent.
The legacy PI launch always passed its managed --session-dir in the command line.
"""
import os
from pathlib import Path


def _owned(command, root):
    text = command.replace('\\', '/').casefold()
    directory = str(root / 'pi' / 'sessions').replace('\\', '/').casefold().rstrip('/')
    return directory in text


def pi_processes_absent(root):
    root = Path(root).resolve()
    if os.name != 'nt':
        proc = Path('/proc')
        if not proc.is_dir():
            return False
        try:
            entries = list(proc.glob('[0-9]*'))
            for entry in entries:
                try:
                    command = (entry / 'cmdline').read_bytes().decode('utf-8').replace('\0', ' ')
                except FileNotFoundError:
                    continue  # The process exited before observation.
                except (OSError, UnicodeError):
                    return False
                if _owned(command, root):
                    return False
        except OSError:
            return False
        return True
    import ctypes
    from ctypes import wintypes as w
    class Entry(ctypes.Structure):
        _fields_ = [('size', w.DWORD), ('usage', w.DWORD), ('pid', w.DWORD),
            ('heap', ctypes.c_size_t), ('module', w.DWORD), ('threads', w.DWORD),
            ('parent', w.DWORD), ('priority', w.LONG), ('flags', w.DWORD), ('exe', w.WCHAR * 260)]
    class Unicode(ctypes.Structure):
        _fields_ = [('length', w.USHORT), ('maximum', w.USHORT), ('buffer', ctypes.c_void_p)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    query = ctypes.WinDLL('ntdll').NtQueryInformationProcess
    query.argtypes = [w.HANDLE, w.ULONG, ctypes.c_void_p, w.ULONG, ctypes.POINTER(w.ULONG)]
    query.restype = w.LONG
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return False
    try:
        first, following = kernel.Process32FirstW, kernel.Process32NextW
        for function in (first, following):
            function.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
            function.restype = w.BOOL
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        active = first(snapshot, ctypes.byref(entry))
        while active:
            if entry.exe.casefold() in {'node.exe', 'nodejs.exe', 'pi.exe'}:
                handle = kernel.OpenProcess(0x1000, False, entry.pid)
                if not handle:
                    if ctypes.get_last_error() != 87:  # Invalid PID: already exited.
                        return False
                else:
                    try:
                        size = w.ULONG()
                        query(handle, 60, None, 0, ctypes.byref(size))
                        if not 0 < size.value <= 128 * 1024:
                            return False
                        buffer = ctypes.create_string_buffer(size.value)
                        if query(handle, 60, buffer, size.value, ctypes.byref(size)) != 0:
                            return False
                        value = Unicode.from_buffer(buffer)
                        address = ctypes.addressof(buffer)
                        if not value.buffer or not address <= value.buffer <= address + size.value - value.length:
                            return False
                        if _owned(ctypes.wstring_at(value.buffer, value.length // 2), root):
                            return False
                    finally:
                        kernel.CloseHandle(handle)
            active = following(snapshot, ctypes.byref(entry))
        return ctypes.get_last_error() == 18  # ERROR_NO_MORE_FILES, not an enumeration failure.
    finally:
        kernel.CloseHandle(snapshot)
