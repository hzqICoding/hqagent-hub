import configparser
import plistlib
from pathlib import Path


def test_service_templates_use_user_scope_private_umask_and_no_secrets():
    root=Path(__file__).resolve().parents[1]/'packaging'
    unit=configparser.ConfigParser(interpolation=None,strict=False)
    unit.read(root/'hqagent-hub.service')
    assert unit['Service']['UMask']=='0077'
    assert '-m runtime.main' in unit['Service']['ExecStart']
    assert unit['Install']['WantedBy']=='default.target'
    with (root/'local.hqagent.hub.plist').open('rb') as stream:
        value=plistlib.load(stream)
    assert value['Umask']==0o077
    assert value['ProgramArguments'][-2:]==['-m','runtime.main']
    assert value['RunAtLoad'] is True
    assert not any('TOKEN' in key or 'SECRET' in key for key in value['EnvironmentVariables'])
