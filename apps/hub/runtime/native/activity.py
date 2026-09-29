"""Conservative exact-ID process observations. Unknown never means closed."""
import os
import re
import time

from storage.local_chat import now


def process_match(vendor_id):
    if os.name != "nt":
        from pathlib import Path
        proc = Path("/proc")
        if not proc.is_dir():
            return "unknown"
        for entry in proc.glob("[0-9]*/cmdline"):
            try:
                args = entry.read_bytes().decode("utf-8").split("\0")
                if vendor_id in args and any("claude" in a or "codex" in a for a in args[:3]):
                    return "present"
            except (OSError, UnicodeError):
                continue
        return "unknown"
    # No shell or WMI subprocess; command lines remain only in memory.
    import ctypes
    from ctypes import wintypes as w
    class Entry(ctypes.Structure):
        _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("pid", w.DWORD),
            ("heap", ctypes.c_size_t), ("module", w.DWORD), ("threads", w.DWORD),
            ("parent", w.DWORD), ("priority", w.LONG), ("flags", w.DWORD), ("exe", w.WCHAR * 260)]
    class Unicode(ctypes.Structure):
        _fields_ = [("length", w.USHORT), ("maximum", w.USHORT), ("buffer", ctypes.c_void_p)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    nt = ctypes.WinDLL("ntdll")
    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    query = nt.NtQueryInformationProcess
    query.argtypes = [w.HANDLE, w.ULONG, ctypes.c_void_p, w.ULONG, ctypes.POINTER(w.ULONG)]
    query.restype = w.LONG
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return "unknown"
    try:
        entry = Entry(); entry.size = ctypes.sizeof(entry)
        first, following = kernel.Process32FirstW, kernel.Process32NextW
        for fn in (first, following):
            fn.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
            fn.restype = w.BOOL
        active = first(snapshot, ctypes.byref(entry))
        while active:
            if entry.exe.lower() in {"claude.exe", "codex.exe", "node.exe"}:
                handle = kernel.OpenProcess(0x1000, False, entry.pid)
                if handle:
                    try:
                        size = w.ULONG()
                        query(handle, 60, None, 0, ctypes.byref(size))
                        if 0 < size.value <= 128 * 1024:
                            buffer = ctypes.create_string_buffer(size.value)
                            if query(handle, 60, buffer, size.value, ctypes.byref(size)) == 0:
                                text = Unicode.from_buffer(buffer)
                                command = ctypes.wstring_at(text.buffer, text.length // 2)
                                if re.search(r"(?<![\w-])" + re.escape(vendor_id) + r"(?![\w-])", command):
                                    return "present"
                    finally:
                        kernel.CloseHandle(handle)
            active = following(snapshot, ctypes.byref(entry))
        return "unknown"
    finally:
        kernel.CloseHandle(snapshot)


def evidence(source, probe=process_match):
    match = probe(source.vendor_id)
    recent = time.time() - source.modified < 5
    return {"activity": "likely_active" if match == "present" or recent else "unknown",
            "observedAt": now(), "processMatch": match, "recentlyModified": recent}
