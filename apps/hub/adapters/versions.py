"""Shared numeric CLI version grammar for metadata and display banners."""
import re


_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def version_tuple(value):
    """History metadata must remain an exact, bounded major.minor.patch."""
    if not isinstance(value, str) or len(value) > 32:
        return None
    match = _VERSION.fullmatch(value)
    return tuple(map(int, match.groups())) if match else None


def cli_version(value):
    """Extract the single numeric version from CLI output, never its surrounding text."""
    if not isinstance(value, str) or len(value) > 4096:
        return None
    versions = {parsed for token in value.split() if (parsed := version_tuple(token)) is not None}
    if len(versions) != 1:
        return None
    return '.'.join(map(str, versions.pop()))
