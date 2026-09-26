import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from './chat.store'
import { HubApiError, setLocalChatGatewayMode, mockLocalChatGateway } from '@/shared/api'

describe('ChatStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    mockLocalChatGateway.reset()
  })

  afterEach(() => {
    const store = useChatStore()
    store.stopPolling()
  })

  it('initializes conversations and workspaces', async () => {
    const store = useChatStore()
    await store.init()
    expect(store.conversations.length).toBeGreaterThan(0)
    expect(store.workspaces.length).toBeGreaterThan(0)
    expect(store.scenes.length).toBe(3)
    expect(store.activeConversationId).toBeDefined()
    expect(store.messages.length).toBeGreaterThan(0)
  })

  it('creates conversation and automatically switches active conversation', async () => {
    const store = useChatStore()
    await store.init()
    const newConv = await store.createConversation(
      '分析架构设计与扩展性',
      store.workspaces[0].id,
      'analyze'
    )
    expect(newConv.title).toBe('分析架构设计与扩展性')
    expect(store.activeConversationId).toBe(newConv.id)
    expect(store.sessionMode).toBe('new') // first message is new
  })

  it('groups active and archived tasks by project and searches project names', async () => {
    const store = useChatStore()
    await store.init()
    expect(store.groupedConversations.find((group) => group.workspace.id === 'ws_demo_project')).toBeDefined()
    expect(store.filteredConversations.every((conversation) => !conversation.archived)).toBe(true)

    store.searchQuery = 'Web-Ecommerce'
    expect(store.groupedConversations.map((group) => group.workspace.id)).toEqual(['ws_demo_project'])
    store.showArchived = true
    expect(store.filteredConversations.map((conversation) => conversation.id)).toContain('conv_archived_checkout')
  })

  it('refreshes metadata after a version conflict', async () => {
    const store = useChatStore()
    await store.init()
    const current = store.conversations.find((conversation) => conversation.id === 'conv_analyze_auth')!
    vi.spyOn(mockLocalChatGateway, 'updateLocalConversation').mockRejectedValueOnce(
      new HubApiError('版本冲突', 'CONFLICT', 409)
    )
    vi.spyOn(mockLocalChatGateway, 'listLocalConversations').mockResolvedValueOnce([
      ...store.conversations.filter((conversation) => conversation.id !== current.id),
      { ...current, title: '服务端新名称', version: 2 },
    ])

    await expect(store.renameConversation(current.id, '客户端名称')).rejects.toMatchObject({ code: 'CONFLICT' })
    expect(store.metadataError).toContain('已刷新列表')
    expect(store.conversations.find((conversation) => conversation.id === current.id)?.title).toBe('服务端新名称')
  })

  it('does not let an older metadata response overwrite a newer polled revision', async () => {
    const store = useChatStore()
    await store.init()
    await store.selectConversation('conv_analyze_auth')
    const current = store.activeConversation!
    let release!: (value: typeof current) => void
    const pendingResponse = new Promise<typeof current>((resolve) => { release = resolve })
    vi.spyOn(mockLocalChatGateway, 'updateLocalConversation').mockReturnValueOnce(pendingResponse)

    const archive = store.setConversationArchived(current.id, true)
    vi.spyOn(mockLocalChatGateway, 'listLocalConversations').mockResolvedValueOnce([
      ...store.conversations.filter((conversation) => conversation.id !== current.id),
      { ...current, title: '轮询得到的新名称', version: 3, archived: false },
    ])
    await store.fetchConversations()
    release({ ...current, title: '过时回包名称', version: 2, archived: true })
    const applied = await archive

    expect(applied).toMatchObject({ title: '轮询得到的新名称', version: 3, archived: false })
    expect(store.activeConversation).toMatchObject({ title: '轮询得到的新名称', version: 3, archived: false })
    expect(store.showArchived).toBe(false)
  })

  it('sends message, updates message stream, and triggers run update', async () => {
    const store = useChatStore()
    await store.init()

    const initialLen = store.messages.length
    await store.sendMessage('请分析当前目录结构')
    expect(store.messages.length).toBeGreaterThan(initialLen)
    expect(store.activeRun).toBeDefined()
  })

  it('controls run actions (pause, resume, cancel)', async () => {
    const store = useChatStore()
    await store.init()

    // Select conv with running task
    await store.selectConversation('conv_develop_ui')
    expect(store.activeRun?.status).toBe('running')

    await store.controlRun(store.activeRun!.id, 'pause')
    expect(store.activeRun?.status).toBe('paused')

    await store.controlRun(store.activeRun!.id, 'resume')
    expect(store.activeRun?.status).toBe('running')

    await store.controlRun(store.activeRun!.id, 'cancel')
    expect(store.activeRun?.status).toBe('cancelled')
  })

  it('handles session non-resumable failure', async () => {
    const store = useChatStore()
    await store.init()
    mockLocalChatGateway.simulateSessionNotResumable = true

    try {
      await store.sendMessage('继续上下文', 'continue')
      expect.unreachable('Should throw non resumable')
    } catch {
      expect(store.resumptionError).toContain('会话无法恢复')
    }
  })

  it('smartly parses tool call args and merges tool_result into preceding tool activity', async () => {
    const store = useChatStore()
    await store.init()

    const taskId = 'task_smart_parse_test'
    // 1. Emit tool call with JSON file_path
    store.ingestEvent({
      eventId: 'evt_tc_1',
      taskId,
      type: 'agent.tool_call',
      occurredAt: '2026-09-24T12:00:00Z',
      payload: {
        toolName: 'Read',
        argumentsExcerpt: '{"file_path": "E:\\\\WorkSpace\\\\ua_android\\\\ua_home\\\\src\\\\main\\\\java\\\\com\\\\example\\\\RtkService.java"}',
      },
    } as any)

    const list1 = store.activitiesByTaskId[taskId]
    expect(list1).toHaveLength(1)
    expect(list1[0].type).toBe('file')
    expect(list1[0].verb).toBe('Read')
    expect(list1[0].fileName).toBe('RtkService.java')
    expect(list1[0].target).toContain('RtkService.java')
    expect(list1[0].detail).toBeUndefined()

    // 2. Emit tool_result
    store.ingestEvent({
      eventId: 'evt_tr_1',
      taskId,
      type: 'agent.tool_call',
      occurredAt: '2026-09-24T12:00:01Z',
      payload: {
        toolName: 'tool_result',
        resultSummary: 'file content line 1\nfile content line 2',
        durationMs: 85,
      },
    } as any)

    // Should NOT create a second activity; instead, merged into the first!
    const list2 = store.activitiesByTaskId[taskId]
    expect(list2).toHaveLength(1)
    expect(list2[0].detail).toBe('file content line 1\nfile content line 2')
    expect(list2[0].durationMs).toBe(85)
    expect(list2[0].status).toBe('done')
  })
})
