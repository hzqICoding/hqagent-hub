"""Device-only credential storage and origin validation; never log input values."""
from __future__ import annotations

import ctypes
import ipaddress
import os
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from core.errors import HubError


def normalize_origin(value: str, *, development: bool = False) -> str:
    try:
        if any(ord(c) <= 32 for c in value) or "\\" in value or "?" in value or "#" in value:
            raise ValueError()
        url = urlsplit(value)
        host, port = url.hostname, url.port
        if not host or "%" in host or url.netloc.endswith(":") or url.username is not None or url.password is not None or url.path not in {"", "/"}:
            raise ValueError()
        if port is not None and not 1 <= port <= 65535:
            raise ValueError()
        if url.scheme != "https" and not (development and url.scheme == "http" and host in {"127.0.0.1", "localhost"}):
            raise ValueError()
        if ":" in host:
            host = "[" + ipaddress.IPv6Address(host).compressed + "]"
        else:
            host = host.encode("idna").decode("ascii").lower()
            if host.endswith("."):
                host = host[:-1]
            if len(host) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", p) for p in host.split(".")):
                raise ValueError()
            if re.fullmatch(r"[0-9.]+", host):
                host = str(ipaddress.IPv4Address(host))
        suffix = "" if port is None or port == (443 if url.scheme == "https" else 80) else f":{port}"
        return f"{url.scheme}://{host}{suffix}"
    except (ValueError, UnicodeError):
        raise HubError("REMOTE_SERVER_ORIGIN_INVALID", "远程服务地址必须是有效的受支持 origin") from None


class _Blob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, *, decrypt: bool = False) -> bytes:
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    call = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    call.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(_Blob)]
    call.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not call(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise HubError("INTERNAL", "设备凭据保护操作失败")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


class CredentialVault:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / "device.credential"

    def save(self, secret: str) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.directory.chmod(0o700)
        content = secret.encode("ascii")
        content = _dpapi(content) if os.name == "nt" else content
        self.atomic_write(self.path, content)

    @staticmethod
    def atomic_write(path: Path, content: bytes) -> None:
        temporary = path.with_name(path.name + ".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(0o600)

    def read(self) -> str:
        try:
            content = self.path.read_bytes()
            return (_dpapi(content, decrypt=True) if os.name == "nt" else content).decode("ascii")
        except Exception:
            raise HubError("REMOTE_DEVICE_AUTH_FAILED", "本机设备凭据不可用") from None

    def create(self) -> None:
        self.save(secrets.token_urlsafe(32))

    def delete(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            raise HubError("INTERNAL", "本机设备凭据删除失败") from None


def safe_text(value: str, secrets_to_hide: tuple[str, ...] = ()) -> str:
    for secret in secrets_to_hide:
        if secret:
            value = value.replace(secret, "[redacted]")
    value = re.sub(r"(?is)-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", "[redacted]", value)
    value = re.sub(r"(?is)<(?:analysis|think|thinking)>.*?</(?:analysis|think|thinking)>", "[redacted]", value)
    value = re.sub(r"(?i)(?:authorization[ \t]*[:=][ \t]*(?:bearer[ \t]+)?|bearer[ \t]+)\S+", "[redacted]", value)
    value = re.sub(r"(?m)^[ \t]*(?:export[ \t]+)?[A-Z_][A-Z0-9_]*=.*$", "[redacted]", value)
    value = re.sub(r"(?im)^.*(?:api[_-]?key|password|secret|token|BEGIN .*PRIVATE KEY|os\.environ|process\.env).*$", "[redacted]", value)
    return value
