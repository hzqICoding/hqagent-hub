import asyncio
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest
from protocol.generated import python as dto

from adapters.failures import version_tuple as adapter_version
from adapters.history import FileHistory
from adapters.versions import cli_version, version_tuple
from remote_support import System, until
from runtime.attachments import verification
from runtime.attachments.capabilities import REQUIRED_PROBES
from runtime.attachments.verification_target import target_for
from test_local_image_jobs import ProbeAdapter


@pytest.mark.parametrize('banner,expected', [
    ('2.1.288 (Claude Code)', '2.1.288'),
    ('codex-cli 0.159.2', '0.159.2'),
    ('  codex-cli 0.159.2\r\n', '0.159.2'),
    ('0.159.2', '0.159.2'),
    ('unknown', None),
    (None, None),
    ('release 01.2.3', None),
    ('release 1.2', None),
    ('release 1.2.3.4', None),
    ('release 1.2.3 other 2.3.4', None),
])
def test_shared_version_grammar_and_safe_banner_extraction(banner, expected):
    assert cli_version(banner) == expected
    assert FileHistory.version_tuple is version_tuple
    if expected:
        numeric = tuple(map(int, expected.split('.')))
        assert FileHistory.version_tuple(expected) == adapter_version(banner) == numeric
        if banner != expected:
            assert FileHistory.version_tuple(banner) is None  # Do not loosen history metadata.
    else:
        assert adapter_version(banner) == ()


@pytest.mark.parametrize('kind,banner,version,model', [
    ('claude', '2.1.288 (Claude Code)', '2.1.288', 'opus'),
    ('codex', 'codex-cli 0.159.2', '0.159.2', 'gpt-6-astra'),
])
def test_real_banners_enable_legacy_targets_and_publish_exact_verified_capabilities(
        tmp_path, monkeypatch, kind, banner, version, model):
    async def scenario():
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path / 'config'))
        monkeypatch.setenv('CODEX_HOME', str(tmp_path / 'config'))
        system = System(tmp_path)
        adapter = ProbeAdapter()
        adapter.version = banner
        identifier = 'local.' + kind + '.default'
        service = system.worker.attachments
        coordinator, caps = service.verifications, service.capabilities
        directory = system.tasks.directory
        directory.adapter = adapter
        directory.candidates = tuple(replace(a, instance_id=identifier, adapter_id=kind) for a in directory.candidates)
        async def agents():
            return [dto.AgentView(id=identifier, adapterId=kind, version=banner, displayName='synthetic',
                status='ready', detectedAt='2026-10-01T00:00:00Z', capabilities=[], assignedRoles=[], isPrimaryFor=[])]
        system.ports.agents = SimpleNamespace(list_agents=agents)
        original_inputs = verification.synthetic_inputs
        def inputs(path):
            values, colors, nonce = original_inputs(path)
            adapter.result = adapter.result.model_copy(update={'summary': ' '.join(colors) + ' ' + nonce})
            return values, colors, nonce
        monkeypatch.setattr(verification, 'synthetic_inputs', inputs)
        try:
            scene = system.chat.repository.scene('analyze')
            system.chat.repository.save_scene('analyze', dto.SaveLocalSceneInput(expectedVersion=scene.version,
                roles=[r.model_copy(update={'agent_instance_id': identifier, 'model_id_': model}) for r in scene.roles]))
            legacy = {}
            for selected in (None, model):
                record = caps.store.record(kind, banner, selected, {k: True for k in REQUIRED_PROBES}, ['image/png'])
                # Reproduce pre-repair files containing the unmodified CLI banner.
                record['version'] = banner
                path = caps.store.root / caps.store.key(kind, selected)
                path.write_text(json.dumps(record), encoding='utf-8')
                legacy[path] = path.read_bytes()
            response = await system.local.get('/api/v1/agents/image-verifications', params={'agentId': identifier})
            assert response.status_code == 200, response.text
            rows = response.json()['data']['items']
            assert {r['target'].get('modelId') for r in rows} == {None, model}
            assert not adapter.started
            for row in rows:
                target = row['target']
                assert target['cliVersion'] == row['lastRecord']['target']['cliVersion'] == version
                assert row['status'] == 'stale' and row['invalidationReasons'] == ['legacy_unbound']
                assert not row['passed'] and row['lastRecord']['passed']
                assert target == target_for(identifier, kind, version, target.get('modelId'), adapter)
                assert not caps.store.capability(kind, banner, target.get('modelId'), target=target).verified
                value = dict(agentId=identifier, expectedTargetRevision=target['targetRevision'], acknowledgeModelUsage=True)
                if 'modelId' in target:
                    value['modelId'] = target['modelId']
                started = await system.local.post('/api/v1/agents/image-verification-jobs', json=value,
                    headers={'Origin': 'http://127.0.0.1', 'Idempotency-Key': 'verify-' + str(target.get('modelId'))})
                assert started.status_code == 202, started.text
                job_id = started.json()['data']['jobId']
                await until(lambda: not coordinator.tasks)
                job = coordinator.view(job_id)
                assert job.status == 'succeeded' and job.applied_to_current_target
                record = caps.store.latest(identifier, kind, target.get('modelId'))
                assert record['version'] == version
                assert caps.store.capability(kind, banner, target.get('modelId'), target=target).verified
            assert all(path.read_bytes() == body for path, body in legacy.items())
            assert caps.values['analyze'][0]['imageInput']['verified']
            assert caps.native(kind, identifier)['imageInput']['verified']
            candidate = directory.candidates[0]
            await service.check_execution(candidate, model, [{'attachment': {'kind': 'image', 'mimeType': 'image/png'}}])
            # Formatting alone must not invalidate the already paid observation.
            adapter.version = version
            page = await coordinator.matrix(agent_id=identifier)
            assert all(row.passed and row.target.cli_version == version for row in page.items)
            adapter.version = 'not a version'
            page = await coordinator.matrix(agent_id=identifier)
            assert all(row.status == 'unavailable' and row.target.cli_version is None and
                       'target_unavailable' in row.invalidation_reasons for row in page.items)
            assert len(adapter.started) == 4  # Queries and capability checks never start probes.
        finally:
            await system.close()
    asyncio.run(scenario())
