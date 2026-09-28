import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { RemoteCatalogView, RemoteConversationView } from '@hqagent/protocol'
import RemoteChatPage from './RemoteChatPage.vue'
import RemoteDevicesPage from './RemoteDevicesPage.vue'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { MockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'

enableAutoUnmount(afterEach)
let gateway: MockRemoteGateway
let router: ReturnType<typeof createRouter>

beforeEach(async () => {
  setActivePinia(createPinia())
  gateway = new MockRemoteGateway()
  gateway.reset()
  gateway.runs = []
  gateway.commands = []
  setRemoteGatewayForTesting(gateway)
  router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/remote/chat', component: RemoteChatPage },
    { path: '/remote/devices', component: RemoteDevicesPage },
  ] })
  await router.push('/remote/chat?workerId=worker_demo')
})

afterEach(() => {
  useRemoteChatStore().reset()
  setRemoteGatewayForTesting(null)
  vi.restoreAllMocks()
})

function chat() {
  return mount(RemoteChatPage, { attachTo: document.body, global: { plugins: [router], stubs: { Teleport: true } } })
}

describe('R1.5 phone repair 2', () => {
  it('hides revoked devices by default, expands a read-only group and keeps the safety guidance', async () => {
    gateway.devices[1].status = 'revoked'
    const wrapper = mount(RemoteDevicesPage, { global: { plugins: [router], stubs: { Teleport: true } } })
    await flushPromises()
    expect(wrapper.text()).not.toContain('Home PC')
    const group = wrapper.findAll('button').find((b) => b.text() === '已撤销（1）')!
    await group.trigger('click')
    expect(wrapper.text()).toContain('Home PC')
    expect(wrapper.findAll('main div.cursor-pointer')).toHaveLength(1)
    await wrapper.findAll('button').find((b) => b.text() === '撤销设备')!.trigger('click')
    expect(wrapper.text()).toContain('重新配对会作为新设备出现')
    expect(wrapper.text()).toContain('关闭电脑上的 Hub 即可')
    expect(wrapper.text()).toContain('撤销不是停止操作')
  })

  it('returns to devices and clears content when selected computer is revoked by polling', async () => {
    chat()
    await flushPromises()
    const store = useRemoteChatStore()
    gateway.devices[0].status = 'revoked'
    await store.refreshActiveDevice()
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/remote/devices')
    expect(store.activeConversationId).toBeNull()
    expect(store.messages).toEqual([])
    expect(store.catalog).toBeNull()
    const wrapper = mount(RemoteDevicesPage, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('该电脑已撤销')
  })

  it('loads catalog options, preselects grouped project and submits actual scene version plus generated title', async () => {
    gateway.catalog.scenes = [{ sceneId: 'review_real', name: '真实审核', version: 7, readOnly: true }]
    const create = vi.spyOn(gateway, 'createConversation')
    const wrapper = chat()
    await flushPromises()
    await wrapper.get('[aria-label="在Web-Ecommerce新建任务"]').trigger('click')
    await flushPromises()
    expect((wrapper.get('#new-conv-workspace').element as HTMLSelectElement).value).toBe('workspace_web')
    expect(wrapper.get('#new-conv-scene').text()).toContain('真实审核')
    await wrapper.findAll('button').find((b) => b.text() === '创建')!.trigger('click')
    await flushPromises()
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ workspaceId: 'workspace_web', sceneId: 'review_real', sceneVersion: 7, title: expect.stringMatching(/^新任务 \d{2}-\d{2} \d{2}:\d{2}$/) }))
    expect(wrapper.text()).toContain('正在电脑上创建…')
  })

  it('disables creation while catalog loads, reports failure and retries on demand', async () => {
    const wrapper = chat()
    await flushPromises()
    const store = useRemoteChatStore()
    store.catalog = null
    let reject!: (reason: Error) => void
    const catalog = vi.spyOn(gateway, 'getWorkerCatalog').mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail }))
    await wrapper.findAll('button').find((b) => b.text() === '新建任务')!.trigger('click')
    await flushPromises()
    expect(wrapper.get('#new-conv-workspace').text()).toContain('正在读取电脑的项目列表…')
    expect(wrapper.findAll('button').find((b) => b.text() === '创建')!.attributes('disabled')).toBeDefined()
    reject(new Error('目录加载失败'))
    await flushPromises()
    expect(wrapper.text()).toContain('目录加载失败')
    await wrapper.findAll('button').find((b) => b.text() === '重试')!.trigger('click')
    await flushPromises()
    expect(catalog).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('button').find((b) => b.text() === '创建')!.attributes('disabled')).toBeUndefined()
  })

  it('preserves grouped project selection while an existing catalog request is in flight', async () => {
    const wrapper = chat()
    await flushPromises()
    let resolve!: (catalog: RemoteCatalogView) => void
    vi.spyOn(gateway, 'getWorkerCatalog').mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const loading = useRemoteChatStore().fetchCatalog()
    await flushPromises()
    await wrapper.get('[aria-label="在workspace_demo新建任务"]').trigger('click')
    resolve({ ...gateway.catalog, workspaces: [...gateway.catalog.workspaces].reverse() })
    await loading
    await flushPromises()
    expect((wrapper.get('#new-conv-workspace').element as HTMLSelectElement).value).toBe('workspace_demo')
  })

  it('rejects missing catalog and offline creation without sending a request', async () => {
    const wrapper = chat()
    await flushPromises()
    const store = useRemoteChatStore()
    const create = vi.spyOn(gateway, 'createConversation')
    store.catalog = null
    expect(await store.createConversation({ targetWorkerId: 'worker_demo', workerStoreId: 'store_demo', title: '任务', workspaceId: 'workspace_demo', sceneId: 'analyze', sceneVersion: 1 })).toBeNull()
    await store.fetchCatalog()
    await wrapper.findAll('button').find((b) => b.text() === '新建任务')!.trigger('click')
    await flushPromises()
    store.devices[0].online = false
    await wrapper.findAll('button').find((b) => b.text() === '创建')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('设备离线，发送失败')
    expect(create).not.toHaveBeenCalled()
  })

  it('polls the first creation without an active conversation and focuses its composer after real sync', async () => {
    gateway.conversations = []
    const wrapper = chat()
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === '新建任务')!.trigger('click')
    await flushPromises()
    await wrapper.findAll('button').find((b) => b.text() === '创建')!.trigger('click')
    await flushPromises()
    const store = useRemoteChatStore()
    expect(store.activeConversationId).toBeNull()
    const conversationId = store.pendingConversation!.conversationId
    const conv: RemoteConversationView = { conversationId, targetWorkerId: 'worker_demo', workerStoreId: 'store_demo', authority: 'remote', workspaceId: 'workspace_demo', sceneId: 'analyze', sceneVersion: 1, title: '新任务', createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() }
    gateway.conversations.push(conv)
    vi.spyOn(gateway, 'listEvents').mockResolvedValueOnce({ items: [{ type: 'conversation.updated', serverCursor: 'sync_1', recordedAt: new Date().toISOString(), payload: conv }], nextServerCursor: 'sync_1', hasMore: false })
    await store.pollEvents()
    await flushPromises()
    expect(store.activeConversationId).toBe(conversationId)
    expect(store.pendingConversation).toBeNull()
    expect(document.activeElement).toBe(wrapper.get('textarea').element)
  })

  it('ignores stale catalog responses when switching computers', async () => {
    const store = useRemoteChatStore()
    await store.fetchDevices()
    let resolve!: (catalog: RemoteCatalogView) => void
    vi.spyOn(gateway, 'getWorkerCatalog').mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const first = store.fetchCatalog()
    await store.selectDevice('worker_home_pc')
    resolve(gateway.catalog)
    await first
    expect(store.catalog?.workerId).toBe('worker_home_pc')
    expect(store.catalog?.workerStoreId).toBe('store_home')
  })

  it('defaults to compact run status, toggles details and automatically expands failures and unconfirmed controls', async () => {
    const wrapper = chat()
    await flushPromises()
    const store = useRemoteChatStore()
    expect(wrapper.find('[data-testid=run-status-toggle]').exists()).toBe(false)
    store.runs = [{ runId: 'run_test', conversationId: store.activeConversationId!, status: 'running', workerOnline: true, observedAt: new Date().toISOString() }]
    await flushPromises()
    expect(wrapper.get('[data-testid=run-status-toggle]').text()).toBe('运行中')
    expect(wrapper.find('#remote-status-details').exists()).toBe(false)
    await wrapper.get('[data-testid=run-status-toggle]').trigger('click')
    expect(wrapper.text()).toContain('1. 传输状态')
    await wrapper.get('[data-testid=run-status-toggle]').trigger('click')
    store.runs[0].status = 'failed'
    await flushPromises()
    expect(wrapper.find('#remote-status-details').exists()).toBe(true)
    expect(wrapper.get('[data-testid=run-status-toggle]').classes()).toContain('text-warning')
    store.runs[0].status = 'running'
    await flushPromises()
    await wrapper.get('[data-testid=run-status-toggle]').trigger('click')
    expect(wrapper.find('#remote-status-details').exists()).toBe(false)
    gateway.controlOutcome = 'unconfirmed'
    await store.controlRun('run_test', 'pause')
    await flushPromises()
    expect(wrapper.text()).toContain('未能确认 (需回电脑核对)')
  })

  it('expands delivery expiry even without a run and restricts withdrawal to eligible submissions', async () => {
    const wrapper = chat()
    await flushPromises()
    const store = useRemoteChatStore()
    const command = { commandId: 'cmd_new', conversationId: store.activeConversationId!, targetWorkerId: 'worker_demo', type: 'run.submit' as const, status: 'queued' as const, deliveryState: 'queued_online' as const, withdrawalState: 'none' as const, workerOnline: true, observedAt: new Date().toISOString(), createdAt: new Date().toISOString(), expiresAt: new Date(Date.now() + 30000).toISOString() }
    store.commands = [command]
    await flushPromises()
    expect(wrapper.text()).toContain('撤回指令')
    store.commands[0].withdrawalState = 'requested'
    await flushPromises()
    expect(wrapper.text()).not.toContain('撤回指令')
    store.commands[0].status = 'failed'
    store.commands[0].error = { code: 'REMOTE_DELIVERY_EXPIRED', message: '设备离线，发送失败', retryable: false }
    await flushPromises()
    expect(wrapper.find('#remote-status-details').exists()).toBe(true)
    expect(wrapper.text()).toContain('设备离线，发送失败')
  })
})
