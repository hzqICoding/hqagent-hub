"""PI resource classification shared by HTTP projection and older wire gates."""
from contextvars import ContextVar
import json
import hashlib

from core.errors import HubError

CLIENT_PI = ContextVar('client_pi', default=None)
HTTP_PROJECTION = ContextVar('http_pi_projection', default=None)
PI_IMAGE_TARGET = ContextVar('pi_image_target', default=None)
DROP = object()
REFS = {'id', 'sceneId', 'agentId', 'agentInstanceId', 'requestAgentId', 'resolvedAgentId',
        'primaryAgentId', 'taskId', 'runId', 'conversationId', 'sessionId', 'nativeSessionId',
        'localConversationId', 'executionTaskId', 'messageId', 'approvalId', 'attachmentId', 'profileId', 'jobId', 'aggregateId'}


class PiVisibility:
    def __init__(self, worker):
        self.worker = worker
        self.db = worker.repo.database
        self.agents = set()
        self.scenes = set()
        self.conversations = set()
        self.resources = set()
        self.changed = None
        self.cursor_scopes = {}
        self.tombstones = set()

    async def refresh(self):
        await self.worker.attachments.capabilities.refresh()
        self.rebuild()

    def was_pi(self, identifier):
        return isinstance(identifier, str) and hashlib.sha256(identifier.encode()).hexdigest() in self.tombstones

    def remember_deleted(self, tx, identifiers):
        hashes = set(self.worker.repo.get('pi-resource-tombstones', tx) or [])
        hashes.update(hashlib.sha256(v.encode()).hexdigest() for v in identifiers if isinstance(v, str))
        self.worker.repo.put('pi-resource-tombstones', sorted(hashes), tx)
        self.tombstones = hashes

    def mentions(self, value, identifiers=None):
        historical = identifiers is None
        identifiers = self.resources if identifiers is None else identifiers
        if isinstance(value, list):
            return any(self.mentions(v, None if historical else identifiers) for v in value)
        if not isinstance(value, dict):
            return False
        if value.get('adapterId') == 'pi' or value.get('agentType') == 'pi':
            return True
        for key, val in value.items():
            if key in REFS and isinstance(val, str) and (val in identifiers or historical and self.was_pi(val)):
                return True
            if key == 'fallbackAgentIds' and any(v in identifiers for v in val or []):
                return True
            if isinstance(val, (dict, list)) and self.mentions(val, None if historical else identifiers):
                return True
        return False

    def rebuild(self):
        self.tombstones = set(self.worker.repo.get('pi-resource-tombstones') or [])
        caps = self.worker.attachments.capabilities
        latest = getattr(self.worker.bridge.chat.ports.agents, '_last_agents', ())
        if not isinstance(latest, (tuple, list)):
            latest = ()
        agents = {a.id for a in [*caps.agents.values(), *latest] if str(a.adapter_id) == 'pi'}
        manager = self.worker.bridge.chat.ports.agents
        if hasattr(type(manager), 'runtime_instances'):
            agents.update(manager.runtime_instances('pi'))
        scenes = {sid for sid, roles in caps.values.items() if any(r.get('agentId') in agents for r in roles)}
        jobs = self.worker.attachments.verifications.data['jobs']
        pi_jobs = {key for key, job in jobs.items() if self.mentions(job['view']['target'], agents)}
        with self.db.locked_connection() as db:
            marker = (db.total_changes, tuple(sorted(agents)), tuple(sorted(scenes)), tuple(sorted(pi_jobs)))
            if marker == self.changed:
                return
            resources = set(agents) | pi_jobs
            for row in db.execute('SELECT scene_id,payload_json FROM local_scenes'):
                if self.mentions(json.loads(row[1]), agents):
                    scenes.add(row[0])
            resources.update(scenes)
            for row in db.execute('SELECT profile_id,payload_json FROM team_profiles'):
                if self.mentions(json.loads(row[1]), agents):
                    resources.add(row[0])
            for row in db.execute('SELECT task_id,resolved_agent,payload_json FROM task_nodes'):
                if row[1] in agents or self.mentions(json.loads(row[2]), agents):
                    resources.add(row[0])
            for row in db.execute('SELECT task_id,profile_id FROM tasks'):
                if row[1] in resources:
                    resources.add(row[0])
            conversations = set()
            for row in db.execute('SELECT conversation_id,payload_json FROM local_conversations'):
                if self.mentions(json.loads(row[1]), resources):
                    conversations.add(row[0])
            runs = list(db.execute('SELECT run_id,conversation_id,task_id,scene_json FROM local_runs'))
            for row in runs:
                if row[2] in resources or self.mentions(json.loads(row[3]), resources):
                    conversations.add(row[1])
            resources.update(conversations)
            for row in runs:
                if row[1] in conversations:
                    resources.add(row[0])
                    if row[2]:
                        resources.add(row[2])
            for table, key, parent in (
                ('sessions', 'session_id', 'task_id'), ('approvals', 'approval_id', 'task_id'),
                ('local_messages', 'message_id', 'conversation_id'),
                ('local_attachments', 'attachment_id', 'conversation_id'),
                ('native_sources', 'native_id', 'conversation_id'),
            ):
                for identifier, owner in db.execute(f'SELECT {key},{parent} FROM {table}'):
                    if owner in resources:
                        resources.add(identifier)
            for row in db.execute('SELECT native_id,index_json FROM native_sources'):
                if self.mentions(json.loads(row[1]), resources):
                    resources.add(row[0])
        self.agents, self.scenes, self.conversations, self.resources = agents, scenes, conversations, resources
        self.changed = marker

    def is_pi(self, value):
        self.rebuild()
        return self.mentions(value)

    def require_wire(self, frame):
        if frame.get('wireRevision', 1) < 5 and self.is_pi(frame):
            raise HubError('REMOTE_REVISION_REQUIRED', '此资源等待远程线路升级')

    def old_projection(self, value, *, root=False):
        if isinstance(value, list):
            return [item for v in value if (item := self.old_projection(v)) is not DROP]
        if not isinstance(value, dict):
            return value
        if 'seq' in value and 'type' in value and self.mentions(value.get('payload')):
            return DROP
        if any(self.mentions(value.get(key)) for key in ('target', 'sceneSnapshot', 'resultRef')):
            return DROP
        # A container is not itself hidden merely because one child is PI.
        own = {k: v for k, v in value.items() if k in REFS or k in {'agentType', 'adapterId'}}
        if self.mentions(own):
            return DROP
        result = {}
        for key, val in value.items():
            if key == 'defaultProfileId' and val in self.resources:
                continue
            if key in {'guard', 'runtimes', 'unsupportedReason', 'formatProfile'}:
                continue
            if 'imageInput' in value and key in {'modelId', 'transport'}:
                continue
            if 'imageInput' in value and 'roleId' in value and key == 'agentType':
                continue
            if 'imageInput' in value and 'roleId' not in value and key == 'agentId':
                continue
            projected = self.old_projection(val)
            if projected is not DROP:
                result[key] = projected
        for key in ('items', 'discovered'):
            if key in result and isinstance(result[key], list) and 'total' in result:
                result['total'] = max(len(result[key]), result['total'] - (len(value[key]) - len(result[key])))
        if 'lastEventSeq' in result and isinstance(result.get('agents'), dict):
            agents = self.worker.attachments.capabilities.agents
            hidden = [a for a in agents.values() if str(a.adapter_id) == 'pi']
            summary = result['agents']
            for key, count in [('total', len(hidden)), ('ready', sum(str(a.status) == 'ready' for a in hidden)),
                               ('issues', sum(str(a.status) != 'ready' for a in hidden))]:
                if key in summary:
                    summary[key] = max(0, summary[key] - count)
        return result

    def project(self, value, enabled):
        self.rebuild()
        result = value if enabled else self.old_projection(value, root=True)
        if result is DROP:
            raise HubError('NOT_FOUND', '资源不存在')
        return result


def project_http(value):
    context = HTTP_PROJECTION.get()
    return context[0].project(value, context[1]) if context else value


def task_revision_allowed(database, task_id):
    """Resolve admission before LocalChat has published the Task handle too."""
    with database.locked_connection() as db:
        row = db.execute(
            "SELECT d.execution_json,i.command_json FROM local_runs r "
            "JOIN tasks t ON (r.task_id=t.task_id OR t.profile_id='local-profile:'||r.run_id) "
            "LEFT JOIN remote2_delivery d ON d.run_id=r.run_id "
            "LEFT JOIN remote_inbox i ON i.run_id=r.run_id "
            "WHERE t.task_id=? AND (d.command_id IS NOT NULL OR i.command_id IS NOT NULL) LIMIT 1",
            (task_id,)).fetchone()
    if row is None:
        return True
    return bool(row[0] and json.loads(row[0]).get('wireRevision', 1) >= 5)
