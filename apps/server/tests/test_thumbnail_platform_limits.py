"""Exercise platform policy without applying OS limits to the pytest process."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from server import thumbnail_child


def platform(monkeypatch, name, resource):
    # Replace module references, not the global os.name used by pathlib/pytest.
    monkeypatch.setattr(thumbnail_child, 'os', SimpleNamespace(name='posix'))
    monkeypatch.setattr(thumbnail_child, 'sys', SimpleNamespace(platform=name))
    monkeypatch.setitem(__import__('sys').modules, 'resource', resource)


def test_linux_keeps_mandatory_memory_cpu_and_file_limits(monkeypatch):
    resource = SimpleNamespace(RLIMIT_AS=1, RLIMIT_CPU=2, RLIMIT_FSIZE=3, setrlimit=Mock())
    platform(monkeypatch, 'linux', resource)
    thumbnail_child.restrict()
    assert resource.setrlimit.call_args_list == [
        ((1, (160 * 1024 * 1024, 160 * 1024 * 1024)),),
        ((2, (6, 6)),),
        ((3, (524288, 524288)),),
    ]


@pytest.mark.parametrize('failed_limit', [1, 2, 3])
@pytest.mark.parametrize('error', [ValueError, OSError])
def test_linux_limit_failure_stays_fatal(monkeypatch, failed_limit, error):
    def setrlimit(resource_id, value):
        if resource_id == failed_limit:
            raise error('synthetic unavailable limit')

    resource = SimpleNamespace(RLIMIT_AS=1, RLIMIT_CPU=2, RLIMIT_FSIZE=3, setrlimit=Mock(side_effect=setrlimit))
    platform(monkeypatch, 'linux', resource)
    with pytest.raises(error):
        thumbnail_child.restrict()


@pytest.mark.parametrize('failed_limit', [None, 2, 3, 'both'])
@pytest.mark.parametrize('error', [ValueError, OSError])
def test_darwin_tries_independent_limits_without_address_space_cap(monkeypatch, failed_limit, error):
    def setrlimit(resource_id, value):
        assert resource_id not in {1, 4}  # Neither AS nor DATA is a claimed memory guard.
        if failed_limit == 'both' or resource_id == failed_limit:
            raise error('synthetic unsupported macOS limit')

    resource = SimpleNamespace(RLIMIT_AS=1, RLIMIT_CPU=2, RLIMIT_FSIZE=3, RLIMIT_DATA=4,
                               setrlimit=Mock(side_effect=setrlimit))
    platform(monkeypatch, 'darwin', resource)
    thumbnail_child.restrict()
    assert resource.setrlimit.call_args_list == [((2, (6, 6)),), ((3, (524288, 524288)),)]


@pytest.mark.parametrize('available', [(), ('RLIMIT_CPU',), ('RLIMIT_FSIZE',)])
def test_darwin_missing_optional_constants_do_not_fail(monkeypatch, available):
    constants = {'RLIMIT_CPU': 2, 'RLIMIT_FSIZE': 3}
    resource = SimpleNamespace(setrlimit=Mock(), **{key: constants[key] for key in available})
    platform(monkeypatch, 'darwin', resource)
    thumbnail_child.restrict()
    assert resource.setrlimit.call_count == len(available)
