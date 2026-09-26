import { describe, it, expect, beforeEach } from 'vitest'
import { MockLocalChatGateway } from './mock-local-chat-gateway'
import { HubApiError } from './local-hub-gateway'
import { PROTOCOL_VERSION } from '@hqagent/protocol'

describe('MockLocalChatGateway', () => {
  let gateway: MockLocalChatGateway

  beforeEach(() => {
    gateway = new MockLocalChatGateway()
  })

  it('provides default authenticated status and allows login/logout', async () => {
    let auth = await gateway.getLocalAuthStatus()
    expect(auth.authenticated).toBe(true)
    expect(auth.protocolVersion).toBe(PROTOCOL_VERSION)

    await gateway.logoutLocalSession()
    auth = await gateway.getLocalAuthStatus()
    expect(auth.authenticated).toBe(false)

    // Login with valid code
    await gateway.openLocalSession({ code: 'valid-local-code-1234' })
    auth = await gateway.getLocalAuthStatus()
    expect(auth.authenticated).toBe(true)

    // Login with short code should fail validation
    await expect(gateway.openLocalSession({ code: '123' })).rejects.toThrow(HubApiError)
  })

  it('lists default workspaces, agents, and scenes from contract fixtures', async () => {
    const workspaces = await gateway.listLocalWorkspaces()
    expect(workspaces.length).toBeGreaterThan(0)
    expect(workspaces[0]).toHaveProperty('id')
    expect(workspaces[0]).toHaveProperty('path')

    const agents = await gateway.listLocalAgents()
    expect(agents.length).toBeGreaterThan(0)

    const scenes = await gateway.listLocalScenes()
    expect(scenes.length).toBe(3)
    const sceneIds = scenes.map((s) => s.id)
    expect(sceneIds).toContain('analyze')
    expect(sceneIds).toContain('plan')
    expect(sceneIds).toContain('develop')
  })

  it('fetches agent models with verified flag or unverified reason', async () => {
    const claudeModels = await gateway.getAgentModels('claude-code-local')
    expect(claudeModels.verified).toBe(true)
    expect(claudeModels.models.length).toBeGreaterThan(0)
    expect(claudeModels.models[0].id).toBe('claude-3-7-sonnet')

    const customModels = await gateway.getAgentModels('unregistered-custom-agent')
    expect(customModels.verified).toBe(false)
    expect(customModels.models.length).toBe(0)
    expect(customModels.reason).toBeDefined()
  })

  it('handles scene save with version conflict (409 expectedVersion)', async () => {
    const scenes = await gateway.listLocalScenes()
    const developScene = scenes.find((s) => s.id === 'develop')!

    // Version mismatch
    await expect(
      gateway.saveLocalScene('develop', {
        roles: developScene.roles,
        expectedVersion: developScene.version + 99,
      })
    ).rejects.toThrow(HubApiError)

    // Correct expected version
    const updated = await gateway.saveLocalScene('develop', {
      roles: developScene.roles,
      expectedVersion: developScene.version,
    })
    expect(updated.version).toBe(developScene.version + 1)
  })

  it('persists review mode while keeping existing run snapshots immutable', async () => {
    const runsBefore = await gateway.listConversationRuns('conv_develop_ui')
    expect(runsBefore[0].sceneSnapshot.reviewMode).toBe('original_planner')
    const scenes = await gateway.listLocalScenes()
    const develop = scenes.find(scene => scene.id === 'develop')!

    const updated = await gateway.saveLocalScene('develop', {
      roles: develop.roles,
      expectedVersion: develop.version,
      reviewMode: 'independent',
    })
    expect(updated.reviewMode).toBe('independent')

    const runsAfter = await gateway.listConversationRuns('conv_develop_ui')
    expect(runsAfter[0].sceneSnapshot.reviewMode).toBe('original_planner')
  })

  it('rejects incomplete original planner scene saves', async () => {
    const scenes = await gateway.listLocalScenes()
    const develop = scenes.find(scene => scene.id === 'develop')!
    const planner = develop.roles.find(role => role.roleId === 'planner')!
    const reviewer = develop.roles.find(role => role.roleId === 'reviewer')!

    reviewer.enabled = false
    await expect(gateway.saveLocalScene('develop', {
      roles: develop.roles,
      expectedVersion: develop.version,
      reviewMode: 'original_planner',
    })).rejects.toMatchObject({ code: 'VALIDATION_FAILED', status: 422 })

    reviewer.enabled = true
    planner.agentInstanceId = ''
    await expect(gateway.saveLocalScene('develop', {
      roles: develop.roles,
      expectedVersion: develop.version,
      reviewMode: 'original_planner',
    })).rejects.toMatchObject({ code: 'VALIDATION_FAILED', status: 422 })
  })

  it('maps original planner review to an acceptance node sharing the planner session', async () => {
    const conv = await gateway.createLocalConversation({
      title: '原规划者验收测试',
      workspaceId: 'ws_local_hub',
      sceneId: 'develop',
    })
    const receipt = await gateway.sendLocalMessage(conv.id, {
      clientMessageId: 'client_original_planner_review',
      text: '实现并交回原规划者验收',
      sessionMode: 'new',
    })
    const run = await gateway.getLocalRun(receipt.runId)
    const plannerNode = run.task!.nodes.find(
      node => node.roleId === 'planner' && node.phase === 'execution'
    )!
    const acceptanceNode = run.task!.nodes.find(node => node.phase === 'acceptance')!

    expect(acceptanceNode.roleId).toBe('planner')
    expect(acceptanceNode.sessionId).toBe(plannerNode.sessionId)
    expect(acceptanceNode.externalSessionId).toBe(plannerNode.externalSessionId)
    expect(acceptanceNode.reviewEvidenceId).toBeDefined()
    expect(acceptanceNode.reviewVerdict).toBeUndefined()
  })

  it('creates conversation, sends message, returns duplicate receipt on repeat clientMessageId', async () => {
    const conv = await gateway.createLocalConversation({
      title: '测试新建会话',
      workspaceId: 'ws_local_hub',
      sceneId: 'analyze',
    })
    expect(conv.id).toBeDefined()

    const receipt1 = await gateway.sendLocalMessage(conv.id, {
      clientMessageId: 'client_msg_001',
      text: '请分析当前目录下的项目结构',
      sessionMode: 'new',
    })
    expect(receipt1.duplicate).toBe(false)
    expect(receipt1.status).toBe('accepted')

    // Same clientMessageId should return duplicate: true
    const receipt2 = await gateway.sendLocalMessage(conv.id, {
      clientMessageId: 'client_msg_001',
      text: '请分析当前目录下的项目结构',
      sessionMode: 'new',
    })
    expect(receipt2.duplicate).toBe(true)

    const messages = await gateway.listLocalMessages(conv.id)
    expect(messages.length).toBeGreaterThanOrEqual(2) // user + system process msg
  })

  it('handles run action controls (pause, resume, cancel)', async () => {
    const runs = await gateway.listConversationRuns('conv_develop_ui')
    expect(runs.length).toBeGreaterThan(0)
    const runId = runs[0].id

    const paused = await gateway.controlLocalRun(runId, { action: 'pause' })
    expect(paused.status).toBe('paused')

    const resumed = await gateway.controlLocalRun(runId, { action: 'resume' })
    expect(resumed.status).toBe('running')

    const cancelled = await gateway.controlLocalRun(runId, { action: 'cancel' })
    expect(cancelled.status).toBe('cancelled')
  })

  it('creates custom ordered scenes from copied role-template provenance', async () => {
    const templates = await gateway.listLocalRoleTemplates()
    const reviewerTemplate = templates[0]
    const input = {
      name: '定制开发验收',
      description: '顺序执行三个阶段',
      reviewMode: 'original_planner' as const,
      roles: [
        { roleId: 'planner', roleName: 'RTK 规划', agentInstanceId: 'agent-1', instructions: 'plan', enabled: true },
        { roleId: 'developer', roleName: 'RTK 实现', agentInstanceId: 'agent-2', instructions: 'develop', enabled: true },
        {
          roleId: 'reviewer', roleName: reviewerTemplate.name, agentInstanceId: 'agent-3',
          instructions: reviewerTemplate.instructions, enabled: true,
          roleTemplateId: reviewerTemplate.id, roleTemplateVersion: reviewerTemplate.version,
        },
      ],
    }
    const created = await gateway.createLocalScene(input, 'create-custom-scene-1')
    const replay = await gateway.createLocalScene(input, 'create-custom-scene-1')

    expect(created.id).toMatch(/^scene_custom_/)
    expect(created).toMatchObject({ name: '定制开发验收', isBuiltin: false, readOnly: false, version: 1 })
    expect(created.roles.map(role => role.roleId)).toEqual(['planner', 'developer', 'reviewer'])
    expect(created.roles[2].agentInstanceId).toBe(created.roles[0].agentInstanceId)
    expect(replay.id).toBe(created.id)
  })

  it('rejects duplicate stages and invalid custom original-planner order', async () => {
    await expect(gateway.createLocalScene({
      name: '重复阶段',
      roles: [
        { roleId: 'analyst', agentInstanceId: 'a', instructions: '', enabled: true },
        { roleId: 'analyst', agentInstanceId: 'b', instructions: '', enabled: true },
      ],
    }, 'duplicate-stage')).rejects.toMatchObject({ code: 'VALIDATION_FAILED' })

    await expect(gateway.createLocalScene({
      name: '顺序错误', reviewMode: 'original_planner',
      roles: [
        { roleId: 'developer', agentInstanceId: 'a', instructions: '', enabled: true },
        { roleId: 'planner', agentInstanceId: 'b', instructions: '', enabled: true },
        { roleId: 'reviewer', agentInstanceId: 'c', instructions: '', enabled: true },
      ],
    }, 'invalid-planner-order')).rejects.toMatchObject({ code: 'VALIDATION_FAILED' })

    await expect(gateway.createLocalScene({
      name: '模板来源错误',
      roles: [{
        roleId: 'analyst', agentInstanceId: 'a', instructions: '', enabled: true,
        roleTemplateId: '', roleTemplateVersion: -1,
      }],
    }, 'invalid-template-provenance')).rejects.toMatchObject({ code: 'VALIDATION_FAILED' })
  })

  it('creates and version-updates role templates without mutating scene copies', async () => {
    const created = await gateway.createLocalRoleTemplate({
      name: 'RTK 分析员', baseRoleId: 'analyst', instructions: '分析 RTK 数据链路',
    }, 'create-template-1')
    const scene = await gateway.createLocalScene({
      name: 'RTK 分析',
      roles: [{
        roleId: 'analyst', roleName: created.name, agentInstanceId: 'agent-1', instructions: created.instructions,
        enabled: true, roleTemplateId: created.id, roleTemplateVersion: created.version,
      }],
    }, 'scene-from-template-1')
    const updated = await gateway.updateLocalRoleTemplate(created.id, {
      expectedVersion: 1, name: 'RTK 高级分析员', instructions: '新的模板职责',
    }, 'update-template-1')

    expect(updated).toMatchObject({ baseRoleId: 'analyst', version: 2 })
    const persistedScene = (await gateway.listLocalScenes()).find(item => item.id === scene.id)!
    expect(persistedScene.roles[0]).toMatchObject({
      roleName: 'RTK 分析员', instructions: '分析 RTK 数据链路', roleTemplateVersion: 1,
    })
    await expect(gateway.updateLocalRoleTemplate(created.id, {
      expectedVersion: 1, name: '过期更新', instructions: '',
    }, 'stale-template-update')).rejects.toMatchObject({ code: 'CONFLICT', status: 409 })
  })

  it('renames, archives, restores, and replays metadata updates idempotently', async () => {
    const renamed = await gateway.updateLocalConversation(
      'conv_analyze_auth',
      { expectedVersion: 1, title: '新的鉴权任务名称' },
      'rename-conversation-1'
    )
    expect(renamed).toMatchObject({ title: '新的鉴权任务名称', version: 2, archived: false })

    const replay = await gateway.updateLocalConversation(
      'conv_analyze_auth',
      { expectedVersion: 1, title: '新的鉴权任务名称' },
      'rename-conversation-1'
    )
    expect(replay.version).toBe(2)

    const archived = await gateway.updateLocalConversation(
      'conv_analyze_auth',
      { expectedVersion: 2, archived: true },
      'archive-conversation-1'
    )
    expect(archived).toMatchObject({ archived: true, version: 3 })
    await expect(gateway.sendLocalMessage('conv_analyze_auth', {
      clientMessageId: 'archived-message', text: '不应发送', sessionMode: 'continue',
    })).rejects.toMatchObject({ code: 'CONFLICT', status: 409 })

    const restored = await gateway.updateLocalConversation(
      'conv_analyze_auth',
      { expectedVersion: 3, archived: false },
      'restore-conversation-1'
    )
    expect(restored).toMatchObject({ archived: false, version: 4 })
  })

  it('rejects stale metadata versions and unfinished-run archives', async () => {
    await expect(gateway.updateLocalConversation(
      'conv_analyze_auth',
      { expectedVersion: 99, title: '过期更新' },
      'stale-conversation-1'
    )).rejects.toMatchObject({ code: 'CONFLICT', status: 409 })

    await expect(gateway.updateLocalConversation(
      'conv_develop_ui',
      { expectedVersion: 1, archived: true },
      'archive-running-conversation-1'
    )).rejects.toMatchObject({ code: 'CONFLICT', status: 409 })
  })

  it('handles cursor expiry error in listLocalEvents', async () => {
    gateway.simulateCursorExpired = true
    await expect(gateway.listLocalEvents(0)).rejects.toThrow(HubApiError)

    // Next call succeeds
    const page = await gateway.listLocalEvents(0)
    expect(page.events).toBeDefined()
    expect(page.nextSeq).toBeDefined()
  })

  it('handles session not resumable error', async () => {
    gateway.simulateSessionNotResumable = true
    await expect(
      gateway.sendLocalMessage('conv_analyze_auth', {
        clientMessageId: 'test_not_resumable',
        text: '继续上一轮任务',
        sessionMode: 'continue',
      })
    ).rejects.toThrow(HubApiError)
  })
})
