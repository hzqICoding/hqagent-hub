from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from adapters.claude_adapter import ClaudeAdapter
from adapters.process import CommandResult, command_environment


@pytest.fixture
def clean_environment(tmp_path, monkeypatch):
    # No real credentials or user settings are read by these tests.
    for key in tuple(os.environ):
        monkeypatch.delenv(key)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    return tmp_path / "settings.json"


def test_preserves_provider_and_proxy_environment_but_removes_only_nested_markers(clean_environment, monkeypatch):
    values = {"HTTP_PROXY": "http://parent-proxy.invalid:8000", "NO_PROXY": "",
              "CLAUDE_CODE_USE_BEDROCK": "1", "CLAUDE_CODE_CLIENT_CERT": "cert.pem",
              "ANTHROPIC_BASE_URL": "https://gateway.invalid", "ANTHROPIC_AUTH_TOKEN": "test-secret",
              "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
    for k, v in {**values, "CLAUDECODE": "1", "CLAUDE_PID": "123"}.items():
        monkeypatch.setenv(k, v)
    result = command_environment("claude")
    assert all(result[k] == v for k, v in values.items())
    assert "CLAUDECODE" not in result and "CLAUDE_PID" not in result
    assert os.environ["CLAUDECODE"] == "1"  # parent process is unchanged


def test_user_settings_supply_proxy_cert_and_auth_without_loading_customizations(clean_environment, monkeypatch):
    path = clean_environment
    value = {"env": {"HTTPS_PROXY": "http://saved-proxy.invalid:9000", "ALL_PROXY": "http://saved-proxy.invalid:9000",
                     "NO_PROXY": "localhost", "NODE_EXTRA_CA_CERTS": "custom.pem",
                     "ANTHROPIC_API_KEY": "test-key", "CLAUDE_CODE_USE_VERTEX": "1",
                     "NODE_OPTIONS": "--require should-not-run.js", "CLAUDECODE": "1"},
             "hooks": {"SessionStart": "must-not-run"}}
    path.write_text(json.dumps(value), encoding="utf-8-sig")
    original = path.read_bytes()
    monkeypatch.setenv("https_proxy", "http://explicit-proxy.invalid:8000")
    monkeypatch.setenv("NO_PROXY", "")
    result = command_environment("claude")
    proxy = {k.upper(): v for k, v in result.items()}
    assert proxy["HTTPS_PROXY"] == "http://explicit-proxy.invalid:8000"
    assert proxy["NO_PROXY"] == ""
    assert proxy["ALL_PROXY"] == value["env"]["ALL_PROXY"]
    assert proxy["NODE_EXTRA_CA_CERTS"] == "custom.pem"
    assert proxy["ANTHROPIC_API_KEY"] == "test-key"
    assert proxy["CLAUDE_CODE_USE_VERTEX"] == "1"
    assert "NODE_OPTIONS" not in result and "CLAUDECODE" not in result
    assert path.read_bytes() == original


@pytest.mark.parametrize("contents", ['{broken', '[]', '{"env": []}', '{"env": {"HTTPS_PROXY": 123}}'])
def test_invalid_settings_never_silently_fall_back_to_direct_connection(clean_environment, contents):
    clean_environment.write_text(contents, encoding="utf-8")
    with pytest.raises(OSError, match="未回退为直连") as error:
        command_environment("claude")
    assert contents not in str(error.value)


def test_default_settings_location_and_codex_environment_are_independent(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    folder = tmp_path / ".claude"
    folder.mkdir()
    (folder / "settings.json").write_text(json.dumps({"env": {"ANTHROPIC_CUSTOM_HEADERS": "test: value"}}))
    monkeypatch.delenv("ANTHROPIC_CUSTOM_HEADERS", raising=False)
    assert command_environment("claude")["ANTHROPIC_CUSTOM_HEADERS"] == "test: value"
    monkeypatch.setenv("CODEX_THREAD_ID", "parent")
    assert "ANTHROPIC_CUSTOM_HEADERS" not in command_environment("codex")
    assert "CODEX_THREAD_ID" not in command_environment("codex")


def test_claude_version_and_login_probes_share_runtime_network_environment(clean_environment):
    clean_environment.write_text(json.dumps({"env": {"HTTPS_PROXY": "http://saved-proxy.invalid:9000"}}))

    class Runner:
        environments = []

        def find(self, _command):
            return "claude.exe"

        async def run(self, args, **kwargs):
            self.environments.append(kwargs["env"])
            return CommandResult(0, "2.1.281" if "--version" in args else '{"loggedIn":true}', "")

    async def scenario():
        runner = Runner()
        adapter = ClaudeAdapter(runner=runner)
        await adapter.detect()
        await adapter.health()
        assert len(runner.environments) == 2
        assert all(env["HTTPS_PROXY"] == "http://saved-proxy.invalid:9000" for env in runner.environments)

    asyncio.run(scenario())
