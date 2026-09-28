import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RemoteDevicePage } from '@hqagent/protocol'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import RemoteDevicesPage from './RemoteDevicesPage.vue'
import RemoteChatPage from './RemoteChatPage.vue'
import { MockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'
import { RemoteApiError, RemoteGateway } from '@/shared/api/remote-gateway'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { remoteRequestFailure } from '@/shared/api/remote-diagnostics'

enableAutoUnmount(afterEach)
let gateway: MockRemoteGateway
let router: ReturnType<typeof createRouter>
beforeEach(async () => {
  setActivePinia(createPinia())
  gateway = new MockRemoteGateway()
  gateway.reset()
  setRemoteGatewayForTesting(gateway)
  remoteRequestFailure.value = null
  router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/remote/devices', component: RemoteDevicesPage },
    { path: '/remote/chat', component: RemoteChatPage },
    { path: '/remote/tokens', component: { template: '<div>Tokens</div>' } },
  ] })
  await router.push('/remote/chat?workerId=worker_demo')
})
afterEach(() => { useRemoteChatStore().reset(); setRemoteGatewayForTesting(null); vi.restoreAllMocks(); vi.unstubAllGlobals(); remoteRequestFailure.value = null })
const options = () => ({ global: { plugins: [router], stubs: { Teleport: true } } })

describe('D50 devices and suspension', () => {
  it('shows connection and remote-access states independently and prefers the display alias', async () => {
    gateway.devices[0].remoteAccess = 'suspended'
    gateway.devices[0].displayName = '我的办公室'
    const wrapper = mount(RemoteDevicesPage, options())
    await flushPromises()
    expect(wrapper.text()).toContain('我的办公室')
    expect(wrapper.text()).not.toContain('Office PC (Alex)')
    expect(wrapper.text()).toContain('电脑在线')
    expect(wrapper.text()).toContain('远程操作已暂停')
    expect(wrapper.text()).not.toContain('撤销设备')
    const filters = wrapper.findAll('select')
    await filters[1].setValue('suspended')
    expect(wrapper.text()).not.toContain('Home PC')
  })

  it('patches pause/resume and clearing an alias with current CAS versions, then reads authoritative state', async () => {
    const store = useRemoteChatStore()
    await store.fetchDevices()
    const patch = vi.spyOn(gateway, 'patchDevice')
    const get = vi.spyOn(gateway, 'getDevice')
    expect(await store.patchDevice('worker_demo', { remoteAccess: 'suspended' })).toBe(true)
    expect(patch).toHaveBeenLastCalledWith('worker_demo', { remoteAccess: 'suspended', expectedVersion: 1 })
    expect(store.devices[0].remoteAccess).toBe('suspended')
    expect(await store.patchDevice('worker_demo', { remoteAccess: 'enabled' })).toBe(true)
    expect(patch).toHaveBeenLastCalledWith('worker_demo', { remoteAccess: 'enabled', expectedVersion: 2 })
    await store.patchDevice('worker_demo', { displayName: '别名' })
    await store.patchDevice('worker_demo', { displayName: '' })
    expect(store.devices[0].displayName).toBeUndefined()
    expect(get).toHaveBeenCalledTimes(8) // mock mutation reads + mandatory post-mutation reads
  })

  it('refreshes after CAS conflict, waits for a new user intent and generates a different key', async () => {
    const real = new RemoteGateway()
    const device = { ...gateway.devices[0], version: 1 }
    const keys: string[] = []
    const versions: number[] = []
    let patches = 0
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init: RequestInit) => {
      if (init.method === 'PATCH') {
        keys.push((init.headers as Record<string, string>)['Idempotency-Key'])
        versions.push(JSON.parse(init.body as string).expectedVersion)
        patches++
        if (patches === 1) {
          device.version = 2
          return new Response(JSON.stringify({ success: false, protocolVersion: '0.8.0', error: { code: 'CONFLICT' }, requestId: 'req_conflict_12345678' }), { status: 409 })
        }
        device.version = 3
        device.remoteAccess = 'suspended'
      }
      return new Response(JSON.stringify({ success: true, protocolVersion: '0.8.0', data: device }))
    }))
    setRemoteGatewayForTesting(real)
    const store = useRemoteChatStore()
    store.devices = [{ ...device }]
    expect(await store.patchDevice(device.workerId, { remoteAccess: 'suspended' })).toBe(false)
    expect(store.deviceActionError).toBe('设备状态已变化，请确认后重试')
    expect(patches).toBe(1)
    expect(store.devices[0].version).toBe(2)
    expect(await store.patchDevice(device.workerId, { remoteAccess: 'suspended' })).toBe(true)
    expect(versions).toEqual([1, 2])
    expect(keys[0]).not.toBe(keys[1])
  })

  it.each(['0.7.0', '0.8.0'])('only treats deletion 404 as absent when server protocol is %s', async (version) => {
    setRemoteGatewayForTesting(new RemoteGateway())
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init: RequestInit) => new Response(JSON.stringify(
      init.method === 'DELETE'
        ? { success: false, protocolVersion: version, error: { code: 'NOT_FOUND' } }
        : { success: true, protocolVersion: version, data: { items: [], hasMore: false } }
    ), { status: init.method === 'DELETE' ? 404 : 200 })))
    const store = useRemoteChatStore()
    expect(await store.deleteDevice('missing')).toBe(version === '0.8.0')
    if (version === '0.7.0') expect(store.deviceActionError).toContain('升级到 0.8.0')
  })

  it('requests revoked history only on expansion and deletes it only after confirmation', async () => {
    gateway.devices[1].status = 'revoked'
    const list = vi.spyOn(gateway, 'listDevices')
    const remove = vi.spyOn(gateway, 'deleteDevice')
    const wrapper = mount(RemoteDevicesPage, options())
    await flushPromises()
    expect(list).toHaveBeenCalledWith(undefined, 100, { includeRevoked: false })
    expect(list.mock.calls.some((args) => args[2]?.includeRevoked)).toBe(false)
    await wrapper.findAll('button').find((b) => b.text().includes('已撤销'))!.trigger('click')
    await flushPromises()
    expect(list).toHaveBeenLastCalledWith(undefined, 100, { includeRevoked: true })
    await wrapper.findAll('button').find((b) => b.text() === '删除')!.trigger('click')
    expect(remove).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('电脑本地不受影响')
    await wrapper.findAll('button').find((b) => b.text() === '确认删除')!.trigger('click')
    await flushPromises()
    expect(remove).toHaveBeenCalledWith('worker_home_pc')
    expect(wrapper.text()).not.toContain('Home PC')
    expect(wrapper.text()).toContain('已撤销（0）')
  })

  it('does not use a stale PATCH response as the new local state', async () => {
    const store = useRemoteChatStore()
    await store.fetchDevices()
    vi.spyOn(gateway, 'patchDevice').mockResolvedValue({ ...gateway.devices[0], displayName: '过时回执', version: 2 })
    gateway.devices[0].displayName = '当前服务器名称'
    gateway.devices[0].version = 3
    await store.patchDevice('worker_demo', { displayName: '过时回执' })
    expect(store.devices[0].displayName).toBe('当前服务器名称')
    expect(store.devices[0].version).toBe(3)
  })

  it('disables restricted controls while keeping cancel and reject available and history readable', async () => {
    gateway.devices[0].remoteAccess = 'suspended'
    gateway.highRiskApprovalAllowed = true
    gateway.approvals[0].action = 'shell'
    const wrapper = mount(RemoteChatPage, options())
    await flushPromises()
    const store = useRemoteChatStore()
    expect(store.isWorkerOnline).toBe(true)
    expect(store.isRemoteSuspended).toBe(true)
    expect(store.messages.length).toBeGreaterThan(0)
    expect(wrapper.get('textarea').attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('button').find((b) => b.text() === '新建任务')!.attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid=run-status-toggle]').trigger('click')
    const buttons = wrapper.findAll('button')
    expect(buttons.find((b) => b.text() === '暂停')!.attributes('disabled')).toBeDefined()
    expect(buttons.find((b) => b.text() === '批准执行')!.attributes('disabled')).toBeDefined()
    expect(buttons.find((b) => b.text() === '取消')!.attributes('disabled')).toBeUndefined()
    expect(buttons.find((b) => b.text() === '拒绝拦截')!.attributes('disabled')).toBeUndefined()
    const control = vi.spyOn(gateway, 'controlRun')
    await expect(store.controlRun('run_demo', 'retry')).rejects.toMatchObject({ code: 'REMOTE_DEVICE_SUSPENDED' })
    await store.controlRun('run_demo', 'cancel')
    expect(control).toHaveBeenCalledTimes(1)
    const approve = vi.spyOn(gateway, 'decideApproval')
    await expect(store.decideApproval(store.approvals[0].approvalId, 'approve')).rejects.toMatchObject({ code: 'REMOTE_DEVICE_SUSPENDED' })
    await store.decideApproval(store.approvals[0].approvalId, 'reject')
    expect(approve).toHaveBeenCalledTimes(1)
  })

  it('refreshes suspension from a command failure event without touching the draft', async () => {
    gateway.runs = []
    const wrapper = mount(RemoteChatPage, options())
    await flushPromises()
    await wrapper.get('textarea').setValue('尚未发送的草稿')
    const store = useRemoteChatStore()
    gateway.devices[0].remoteAccess = 'suspended'
    await store.applyEvent({ type: 'command.updated', serverCursor: 'cur_suspended', recordedAt: new Date().toISOString(),
      payload: { ...gateway.commands[0], status: 'failed', error: { code: 'REMOTE_DEVICE_SUSPENDED', message: '这台电脑的远程操作已暂停', retryable: false } } })
    await flushPromises()
    expect(store.isRemoteSuspended).toBe(true)
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('尚未发送的草稿')
  })

  it('does not let an older list response overwrite post-PATCH device state', async () => {
    const store = useRemoteChatStore()
    await store.fetchDevices()
    const stale = store.devices.map((d) => ({ ...d }))
    let resolve!: (page: RemoteDevicePage) => void
    vi.spyOn(gateway, 'listDevices').mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const pending = store.fetchDevices()
    await store.patchDevice('worker_demo', { remoteAccess: 'suspended' })
    resolve({ items: stale, hasMore: false })
    await pending
    expect(store.devices[0].remoteAccess).toBe('suspended')
  })

  it('keeps the draft on a server SUSPENDED race and refreshes device state', async () => {
    gateway.runs = []
    const wrapper = mount(RemoteChatPage, options())
    await flushPromises()
    await wrapper.get('textarea').setValue('保留输入内容')
    const get = vi.spyOn(gateway, 'getDevice')
    vi.spyOn(gateway, 'sendMessage').mockImplementation(async () => {
      gateway.devices[0].remoteAccess = 'suspended'
      throw new RemoteApiError({ code: 'REMOTE_DEVICE_SUSPENDED', status: 409, message: '这台电脑的远程操作已暂停' })
    })
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('保留输入内容')
    expect(wrapper.text()).toContain('这台电脑的远程操作已暂停')
    expect(get).toHaveBeenCalledWith('worker_demo')
    expect(useRemoteChatStore().isRemoteSuspended).toBe(true)
  })
})
