import { describe, it, expect, beforeEach } from 'vitest'
import { MockLocalChatGateway } from './mock-local-chat-gateway'
import { HubApiError } from './local-hub-gateway'

describe('MockLocalChatGateway', () => {
  let gateway: MockLocalChatGateway

  beforeEach(() => {
    gateway = new MockLocalChatGateway()
  })

  it('provides default authenticated status and allows login/logout', async () => {
    let auth = await gateway.getLocalAuthStatus()
    expect(auth.authenticated).toBe(true)
    expect(auth.protocolVersion).toBe('0.3.0')

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
