import logging

import pytest

from core.errors import HubError
from runtime.remote.keychain import PosixCredentialStore, MARKER, SERVICE
from runtime.remote.security import CredentialVault


class MemoryKeyring:
    def __init__(self):self.items={}
    def get_password(self,service,account):return self.items.get((service,account))
    def set_password(self,service,account,value):self.items[service,account]=value
    def delete_password(self,service,account):self.items.pop((service,account),None)


def store(tmp_path,backend):
    return PosixCredentialStore(tmp_path,backend_factory=lambda:backend,atomic_write=CredentialVault.atomic_write)


def test_keyring_save_reload_unlink_never_logs_secret(tmp_path,caplog):
    backend=MemoryKeyring();vault=store(tmp_path,backend)
    caplog.set_level(logging.WARNING)
    vault.save('SYNTHETIC_CREDENTIAL')
    assert vault.path.read_bytes()==MARKER
    assert store(tmp_path,backend).read()=='SYNTHETIC_CREDENTIAL'
    assert 'mode=system-keyring' in caplog.text and 'SYNTHETIC_CREDENTIAL' not in caplog.text
    vault.delete()
    assert not vault.path.exists() and not backend.items


def test_fallback_then_migration_and_unavailable_keyring_does_not_lose_credential(tmp_path,caplog):
    vault=store(tmp_path,None);vault.save('SECRET_VALUE')
    assert vault.path.read_bytes()==b'SECRET_VALUE' and vault.read()=='SECRET_VALUE'
    assert 'mode=file-0600' in caplog.text and 'SECRET_VALUE' not in caplog.text
    backend=MemoryKeyring()
    migrated=store(tmp_path,backend)
    assert migrated.read()=='SECRET_VALUE' and migrated.path.read_bytes()==MARKER
    with pytest.raises(HubError):store(tmp_path,None).read()
    with pytest.raises(HubError):store(tmp_path,None).delete()
    assert migrated.read()=='SECRET_VALUE'
    migrated.delete()


@pytest.mark.parametrize('failure',['set','verify','marker'])
def test_migration_failure_preserves_old_file_and_allows_retry(tmp_path,monkeypatch,failure):
    backend=MemoryKeyring();vault=store(tmp_path,backend)
    clock=[100.0]
    vault.monotonic=lambda:clock[0]
    CredentialVault.atomic_write(vault.path,b'OLD_SECRET')
    with monkeypatch.context() as m:
        if failure=='set':
            def broken(*_args):raise RuntimeError('PRIVATE_BACKEND_ERROR')
            m.setattr(backend,'set_password',broken)
        elif failure=='verify':m.setattr(backend,'get_password',lambda *_args:'wrong')
        else:
            def write(path,raw):
                if raw==MARKER:raise OSError('PRIVATE_BACKEND_ERROR')
                CredentialVault.atomic_write(path,raw)
            m.setattr(vault,'atomic_write',write)
        assert vault.read()=='OLD_SECRET'
        assert vault.path.read_bytes()==b'OLD_SECRET'
    clock[0]+=600
    assert vault.read()=='OLD_SECRET' and vault.path.read_bytes()==MARKER
    vault.delete();assert not backend.items and not vault.pending.exists()


def test_system_backend_selection_does_not_use_third_party_plaintext_backend(isolated_system_keyring):
    system_keyring = isolated_system_keyring
    assert system_keyring('win32') is None and system_keyring('unknown') is None


@pytest.mark.parametrize('platform,module',[('darwin','keyring.backends.macOS'),('linux','keyring.backends.SecretService')])
def test_platform_keyring_selection_uses_only_native_backend(monkeypatch,platform,module,isolated_system_keyring):
    import sys
    from types import SimpleNamespace
    system_keyring = isolated_system_keyring
    class Backend(MemoryKeyring):priority=1
    monkeypatch.setitem(sys.modules,module,SimpleNamespace(Keyring=Backend))
    assert isinstance(system_keyring(platform),Backend)
    class Unavailable:
        def __init__(self):raise RuntimeError('unavailable')
    monkeypatch.setitem(sys.modules,module,SimpleNamespace(Keyring=Unavailable))
    assert system_keyring(platform) is None


def test_successfully_migrated_secret_is_not_replaced_on_new_save(tmp_path):
    backend=MemoryKeyring();vault=store(tmp_path,backend);vault.save('ORIGINAL')
    with pytest.raises(HubError):vault.save('REPLACEMENT')
    assert vault.read()=='ORIGINAL'


def test_default_factory_is_late_bound_and_isolated_from_system_vaults(tmp_path,monkeypatch):
    from runtime.remote import keychain
    vault=PosixCredentialStore(tmp_path,atomic_write=CredentialVault.atomic_write)
    assert keychain.system_keyring() is None
    calls=[]
    monkeypatch.setattr(keychain,'system_keyring',lambda:calls.append(True))
    vault.save('ISOLATED')
    assert calls==[True] and vault.path.read_bytes()==b'ISOLATED'


@pytest.mark.parametrize('failure',[None,'set','verify','unavailable'])
def test_new_save_never_writes_plaintext_before_trying_keyring(tmp_path,failure):
    backend=MemoryKeyring();operations=[]
    class Backend(MemoryKeyring):
        def set_password(self,*args):
            operations.append('set')
            if failure=='set':raise RuntimeError('PRIVATE')
            super().set_password(*args)
        def get_password(self,*args):
            operations.append('verify')
            return 'mismatch' if failure=='verify' else super().get_password(*args)
    backend=Backend()
    def factory():
        operations.append('discover')
        return None if failure=='unavailable' else backend
    def write(path,content):
        operations.append('plaintext' if content==b'NEW_SECRET' else 'marker' if content==MARKER else 'journal')
        CredentialVault.atomic_write(path,content)
    vault=PosixCredentialStore(tmp_path,backend_factory=factory,atomic_write=write)
    vault.save('NEW_SECRET')
    if failure is None:
        assert operations==['discover','journal','set','verify','marker']
        assert vault.path.read_bytes()==MARKER
    else:
        assert operations[-1]=='plaintext' and operations[0]=='discover'
        assert vault.path.read_bytes()==b'NEW_SECRET'


@pytest.mark.parametrize('mode',['missing','raises','verification'])
def test_file_mode_backs_off_and_marker_reads_bypass_backoff(tmp_path,mode):
    ticks=[100.0];calls=[];backend=MemoryKeyring();ready=[False]
    def factory():
        calls.append(ticks[0])
        if ready[0]:return backend
        if mode=='raises':raise RuntimeError('PRIVATE_DBUS_ERROR')
        if mode=='verification':
            class Invalid(MemoryKeyring):
                def get_password(self,*args):return 'mismatch'
            return Invalid()
        return None
    vault=PosixCredentialStore(tmp_path,backend_factory=factory,atomic_write=CredentialVault.atomic_write,
        monotonic=lambda:ticks[0])
    vault.save('SECRET')
    ready[0]=True
    for _ in range(10):assert vault.read()=='SECRET'
    ticks[0]=699.99
    assert vault.read()=='SECRET' and calls==[100.0]
    ticks[0]=700
    assert vault.read()=='SECRET' and vault.path.read_bytes()==MARKER
    assert calls==[100.0,700]
    vault.retry_after=99999
    assert vault.read()=='SECRET' and calls==[100.0,700,700]


def test_pending_first_write_recovers_keyring_after_marker_commit_failure(tmp_path):
    backend=MemoryKeyring();vault=store(tmp_path,backend)
    CredentialVault.atomic_write(vault.pending,b'pending\n')
    backend.set_password(SERVICE,vault.account,'RECOVERABLE')
    assert not vault.path.exists()
    assert vault.read()=='RECOVERABLE' and vault.path.read_bytes()==MARKER
    assert not vault.pending.exists()


@pytest.mark.skipif(__import__('os').name=='nt',reason='POSIX mode bits')
def test_headless_file_permissions_are_private(tmp_path):
    vault=store(tmp_path,None);vault.save('PRIVATE')
    assert vault.path.stat().st_mode&0o777==0o600
    assert tmp_path.stat().st_mode&0o777==0o700
