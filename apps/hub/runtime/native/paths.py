"""Real directory identities; Windows leases deny rename/delete while in use."""
from __future__ import annotations

import ctypes
import os
import re
from contextlib import ExitStack, contextmanager
from pathlib import Path, PureWindowsPath

from core.errors import HubError


def denied(code="REMOTE_PATH_OUTSIDE_ROOT"):
    return HubError(code, "目录路径或身份无法通过授权检查")


def absolute_directory(value: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value or value.startswith(("\\", "//")):
        raise denied()
    parts = re.split(r"[/\\]", value)
    if any(p in {".", ".."} or p.endswith((".", " ")) for p in parts if p):
        raise denied()
    if os.name == "nt":
        win = PureWindowsPath(value)
        if not win.is_absolute() or not re.fullmatch(r"[a-zA-Z]:", win.drive):
            raise denied()
        if any(":" in p for p in win.parts[1:]):
            raise denied()
    elif "\\" in value or any(":" in p for p in parts):
        raise denied()
    path = Path(value)
    if not path.is_absolute():
        raise denied()
    return path


def inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@contextmanager
def _open_directory(path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            stat = os.fstat(fd)
            yield (stat.st_dev, stat.st_ino)
        finally:
            os.close(fd)
        return
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    class Information(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("created", wintypes.FILETIME),
            ("accessed", wintypes.FILETIME), ("written", wintypes.FILETIME),
            ("volume", wintypes.DWORD), ("size_high", wintypes.DWORD), ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD), ("index_high", wintypes.DWORD), ("index_low", wintypes.DWORD)]
    info = kernel.GetFileInformationByHandle
    info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Information)]
    info.restype = wintypes.BOOL
    handle = create(str(path), 0x80000000, 0x1 | 0x2, None, 3, 0x02000000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise denied("REMOTE_DIRECTORY_CHANGED")
    try:
        value = Information()
        if not info(handle, ctypes.byref(value)) or not value.attributes & 0x10:
            raise denied("REMOTE_DIRECTORY_CHANGED")
        yield (value.volume, (value.index_high << 32) | value.index_low)
    finally:
        close(handle)


@contextmanager
def directory_lease(value: str, *, root: Path | None = None, identity=None):
    """Open resolved ancestors and target; reject changed identity before use.

    Callers use the resolved path while leases are held, and recheck before
    committing. No path supplied by the client is concatenated after validation.
    """
    raw = absolute_directory(value)
    try:
        resolved = raw.resolve(strict=True)
        if root is not None and not inside(resolved, root):
            raise denied()
        with ExitStack() as stack:
            parent_ids = []
            for part in [*reversed(resolved.parents), resolved]:
                parent_ids.append((part, stack.enter_context(_open_directory(part))))
            actual = parent_ids[-1][1]
            if root is not None and os.name == "nt":
                with _open_directory(root) as root_identity:
                    if actual[0] != root_identity[0]:
                        raise denied()
            if identity is not None and tuple(identity) != actual:
                raise denied("REMOTE_DIRECTORY_CHANGED")
            if raw.resolve(strict=True) != resolved:
                raise denied("REMOTE_DIRECTORY_CHANGED")
            yield resolved, actual
            if raw.resolve(strict=True) != resolved:
                raise denied("REMOTE_DIRECTORY_CHANGED")
            # POSIX handles survive rename; identity verification detects a
            # replacement before the caller publishes a listing/reference.
            for part, previous in parent_ids:
                with _open_directory(part) as current:
                    if current != previous:
                        raise denied("REMOTE_DIRECTORY_CHANGED")
    except (OSError, RuntimeError, ValueError):
        raise denied("REMOTE_DIRECTORY_CHANGED") from None
