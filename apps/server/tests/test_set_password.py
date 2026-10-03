import io
import sys
from unittest.mock import Mock

import pytest

from conftest import Browser, PASSWORD
from server import cli
from server.common import uid

NEW_PASSWORD = 'replacement-password-for-cli-tests'
FAILURE = 'Operation failed; check account input, configuration and file permissions\n'


def invoke(env, monkeypatch, *, login='alice', password=NEW_PASSWORD, stdin=True):
    monkeypatch.setattr(cli.Settings, 'from_env', lambda: env.settings)
    argv = ['server.cli', 'set-password', '--login', login]
    stream = io.StringIO(password + '\nsecond line is not a password\n')
    if stdin:
        argv.append('--password-stdin')
        monkeypatch.setattr(sys, 'stdin', stream)
        monkeypatch.setattr(cli.getpass, 'getpass', Mock(side_effect=AssertionError('unexpected terminal read')))
    else:
        prompt = Mock(return_value=password)
        monkeypatch.setattr(cli.getpass, 'getpass', prompt)
    monkeypatch.setattr(sys, 'argv', argv)
    result = cli.main()
    if stdin:
        assert stream.readline() == 'second line is not a password\n'
    else:
        prompt.assert_called_once_with('Account password: ')
    return result


def login(env, password):
    return env.client.post('/api/v2/auth/login', json=dict(loginName='alice', password=password),
                          headers={'Cookie': '', 'Origin': env.settings.origin, 'Idempotency-Key': uid()})


@pytest.mark.parametrize('stdin', [True, False])
def test_cli_password_change_invalidates_all_sessions_but_preserves_pat(r15_env, monkeypatch, capsys, caplog, stdin):
    env = r15_env
    another = Browser(env, 'alice')
    logged_out = Browser(env, 'alice')
    logout_key = uid()
    assert logged_out.post('/auth/logout', key=logout_key).status_code == 200
    issued = env.alice.post('/api-tokens', dict(name='automation', scopes=['devices:read']))
    secret = issued.json()['data']['secret']
    with env.service.repo.transaction() as tx:
        old_account = tx.auth_get('account:' + env.service.security.mac('login', 'alice'))
    assert invoke(env, monkeypatch, stdin=stdin) == 0
    output = capsys.readouterr()
    assert output.out == 'Password updated; browser sessions invalidated\n' and output.err == ''
    for browser in (env.alice, another, logged_out):
        assert browser.get('/devices').status_code == 401
        assert browser.get('/auth/session').json()['data'] == {'authenticated': False}
    assert logged_out.post('/auth/logout', key=logout_key).status_code == 401
    assert env.bob.get('/devices').status_code == 200
    assert login(env, PASSWORD).status_code == 401
    assert login(env, NEW_PASSWORD).status_code == 200
    assert env.client.get('/api/v2/devices', headers={'Cookie': '', 'Authorization': 'Bearer ' + secret}).status_code == 200
    with env.service.repo.transaction() as tx:
        account = tx.auth_get('account:' + env.service.security.mac('login', 'alice'))
    assert account['owner'] == old_account['owner']
    assert account['password']['salt'] != old_account['password']['salt']
    for private in (PASSWORD, NEW_PASSWORD, account['password']['salt'], account['password']['hash']):
        assert private not in output.out + output.err + caplog.text


@pytest.mark.parametrize('name,password', [('unknown', NEW_PASSWORD), ('alice', 'too-short'), ('alice', 'x' * 1025)])
def test_cli_failure_does_not_create_account_or_invalidate_sessions(r15_env, monkeypatch, capsys, name, password):
    env = r15_env
    assert invoke(env, monkeypatch, login=name, password=password) == 1
    output = capsys.readouterr()
    assert output.out == '' and output.err == FAILURE
    assert env.alice.get('/devices').status_code == 200
    assert login(env, PASSWORD).status_code == 200
    with env.service.repo.transaction() as tx:
        assert tx.auth_get('account:' + env.service.security.mac('login', 'unknown')) is None


def test_password_and_session_change_are_one_transaction(r15_env, monkeypatch, capsys):
    from server.repository import UnitOfWork
    monkeypatch.setattr(UnitOfWork, 'delete_browser_sessions', Mock(side_effect=RuntimeError('private details')))
    assert invoke(r15_env, monkeypatch) == 1
    assert capsys.readouterr().err == FAILURE
    assert r15_env.alice.get('/devices').status_code == 200
    assert login(r15_env, PASSWORD).status_code == 200
    assert login(r15_env, NEW_PASSWORD).status_code == 401
