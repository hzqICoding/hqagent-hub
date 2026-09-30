"""All Hub test trees default to isolated credential storage, never OS vaults."""
import pytest


@pytest.fixture(autouse=True)
def isolated_system_keyring(monkeypatch):
    from runtime.remote import keychain

    original = keychain.system_keyring
    monkeypatch.setattr(keychain, "system_keyring", lambda *args, **kwargs: None)
    # Selector tests may exercise this function only with mocked backend modules;
    # behavior tests explicitly inject MemoryKeyring instead of OS discovery.
    return original
