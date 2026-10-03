import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { enableAutoUnmount, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import type { NativeMessagePage, RemoteLinkView } from '@hqagent/protocol'
import RemoteChatPage from '@/pages/remote/RemoteChatPage.vue'
import NativeSessionsPanel from './NativeSessionsPanel.vue'
import RemoteWorkspaceDialog from './RemoteWorkspaceDialog.vue'
import AuthorizedRootsSettings from './AuthorizedRootsSettings.vue'
import { NativeMessageAssembler, nativeSyncNotice, nativeFailure } from './native-utils'
import { nativeExampleMessages } from '@/shared/api/native-examples'
import { MockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { MockLocalChatGateway } from '@/shared/api/mock-local-chat-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'
import { setLocalChatGatewayForTesting } from '@/shared/api/local-chat-provider'
import { RemoteApiError, HubApiError } from '@/shared/api'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { useChatStore } from '@/stores/chat.store'

enableAutoUnmount(afterEach)
let remote: MockRemoteGateway
let local: MockLocalChatGateway
const options = { global: { stubs: { Teleport: true } } }
const button = (wrapper: VueWrapper, text: string) => wrapper.findAll('button').find((b) => b.text() === text)!
beforeEach(async () => {
  setActivePinia(createPinia()); localStorage.clear(); sessionStorage.clear()
  remote = new MockRemoteGateway(); remote.reset(); remote.devices[0].supportedWireRevisions = [2, 3]
  local = new MockLocalChatGateway()
  setRemoteGatewayForTesting(remote); setLocalChatGatewayForTesting(local)
  await useRemoteChatStore().fetchDevices()
  await useRemoteChatStore().selectDevice('worker_demo')
})
afterEach(() => { useRemoteChatStore().reset(); useChatStore().stopPolling(); setRemoteGatewayForTesting(null); setLocalChatGatewayForTesting(null); vi.restoreAllMocks(); vi.useRealTimers() })
function panel(isRemote = true, online = true) {
  return mount(NativeSessionsPanel, { ...options, props: { remote: isRemote, workerId: isRemote ? 'worker_demo' : undefined, online, revisions: [3], projects: [{ id: 'workspace_demo', name: '示例项目' }] } })
}
async function confirmImport(wrapper: VueWrapper) {
  await flushPromises()
  await wrapper.findAll('button').find((b) => b.text().includes('示例：梳理项目结构'))!.trigger('click')
  await flushPromises(); await button(wrapper, '接着对话').trigger('click'); await flushPromises()
}

describe('R3 native sessions', () => {
  it('groups by workspace with Agent and activity labels; offline history never requests content', async () => {
    const read = vi.spyOn(remote, 'readNativeMessages')
    const wrapper = panel(true, false); await flushPromises()
    expect(wrapper.text()).toContain('示例项目'); expect(wrapper.text()).toContain('Claude Code'); expect(wrapper.text()).toContain('Codex')
    for (const status of ['可能仍在终端中运行', '终端正在使用', '已确认关闭']) expect(wrapper.text()).toContain(status)
    await wrapper.findAll('button').find((b) => b.text().includes('示例：梳理项目结构'))!.trigger('click')
    expect(wrapper.text()).toContain('电脑离线，无法读取原生会话内容'); expect(read).not.toHaveBeenCalled()
  })
  it('requires explicit unchecked confirmation and reconciles remote 202 before selecting a real conversation', async () => {
    vi.useFakeTimers()
    const issue = vi.spyOn(remote, 'importNativeSession')
    const wrapper = panel(); await confirmImport(wrapper)
    expect(wrapper.text()).toContain('同时写入会损坏会话记录')
    expect(button(wrapper, '确认导入').attributes('disabled')).toBeDefined()
    expect(issue).not.toHaveBeenCalled()
    await wrapper.get('input[type=checkbox]').setValue(true)
    await button(wrapper, '确认导入').trigger('click'); await flushPromises()
    expect(issue).toHaveBeenCalledWith('native_example_0', { terminalClosedConfirmed: true, expectedIndexVersion: 1, sourceRevision: 'example_source_revision' })
    expect(wrapper.text()).toContain('正在电脑上导入…')
    expect(useRemoteChatStore().activeConversationId).not.toBe('imported_native_example_0')
    await vi.advanceTimersByTimeAsync(1000); await flushPromises()
    expect(useRemoteChatStore().activeConversationId).toBe('imported_native_example_0')
    expect(wrapper.emitted('opened')).toHaveLength(1)
  })
  it('does not treat an accepted import as failed at the delivery deadline', async () => {
    vi.useFakeTimers()
    vi.spyOn(remote, 'getCommand').mockImplementation(async (id) => ({ commandId: id, targetWorkerId: 'worker_demo', type: 'native.import', status: 'accepted', deliveryState: 'granted', withdrawalState: 'none', workerOnline: true, observedAt: new Date().toISOString(), createdAt: new Date().toISOString(), expiresAt: new Date(Date.now() - 60000).toISOString() }))
    const wrapper = panel(); await confirmImport(wrapper)
    await wrapper.get('input[type=checkbox]').setValue(true)
    await button(wrapper, '确认导入').trigger('click'); await flushPromises()
    await vi.advanceTimersByTimeAsync(31000); await flushPromises()
    expect(wrapper.text()).toContain('正在电脑上导入…')
    expect(wrapper.emitted('opened')).toBeUndefined()
  })
  it('drops read contents when offline and never persists native history', async () => {
    const wrapper = panel(); await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('示例：梳理项目结构'))!.trigger('click'); await flushPromises()
    await vi.waitFor(() => expect(wrapper.text()).toContain('这是用于界面验收的合成会话内容'))
    await wrapper.setProps({ online: false })
    expect(wrapper.text()).not.toContain('这是用于界面验收的合成会话内容')
    expect(JSON.stringify(localStorage)).not.toContain('合成会话内容')
    expect(JSON.stringify(sessionStorage)).not.toContain('合成会话内容')
  })

  it('imports locally with no cloud command or pairing requirement', async () => {
    const cloud = vi.spyOn(remote, 'importNativeSession')
    const wrapper = panel(false); await confirmImport(wrapper)
    await wrapper.get('input[type=checkbox]').setValue(true)
    await button(wrapper, '确认导入').trigger('click'); await flushPromises()
    expect(useChatStore().activeConversation?.conversationKind).toBe('native')
    expect(useChatStore().activeConversation?.sceneId).toBeUndefined()
    expect(cloud).not.toHaveBeenCalled()
  })
  it.each(['NATIVE_SESSION_ACTIVE', 'NATIVE_SESSION_CHANGED', 'NATIVE_SESSION_WRITER_CONFLICT', 'REMOTE_DEVICE_SUSPENDED'])('handles %s with requestId and drops confirmation', async (code) => {
    vi.spyOn(remote, 'importNativeSession').mockRejectedValue(new RemoteApiError({ code, status: 409, message: 'rejected', requestId: 'req_native_example' }))
    const wrapper = panel(); await confirmImport(wrapper)
    await wrapper.get('input[type=checkbox]').setValue(true); await button(wrapper, '确认导入').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain(nativeFailure({ code }).message); expect(wrapper.text()).toContain('req_native_example')
    if (wrapper.find('input[type=checkbox]').exists()) expect((wrapper.get('input[type=checkbox]').element as HTMLInputElement).checked).toBe(false)
  })
  it('copies synthetic local history and creates a native run without a scene snapshot', async () => {
    const conversation = await local.importNativeSession('native_example_0', { terminalClosedConfirmed: true, expectedIndexVersion: 1, sourceRevision: 'example_source_revision' })
    expect((await local.listLocalMessages(conversation.id))[0].text).toContain('合成会话内容')
    const receipt = await local.sendLocalMessage(conversation.id, { clientMessageId: 'synthetic_message', text: '合成续接', sessionMode: 'continue' })
    const run = await local.getLocalRun(receipt.runId)
    expect(run.conversationKind).toBe('native')
    expect(run.sceneSnapshot).toBeUndefined()
    expect(run.agentType).toBe('claude')
  })

  it('shows revision and sync-disabled reasons instead of an empty result', async () => {
    const wrapper = panel(); await wrapper.setProps({ revisions: [2] }); await flushPromises()
    expect(wrapper.text()).toContain('电脑不支持修订 3')
    vi.spyOn(remote, 'listNativeSessions').mockRejectedValue(new RemoteApiError({ code: 'REMOTE_SYNC_DISABLED', status: 409, message: '同步关闭' }))
    await wrapper.setProps({ revisions: [3] }); await flushPromises()
    expect(wrapper.text()).toContain('这台电脑已关闭同步')
    expect(wrapper.text()).not.toContain('没有已登记项目内的原生会话')
  })
  it('does not invent a sync-disabled fact from an empty remote index page', async () => {
    vi.spyOn(remote, 'listNativeSessions').mockResolvedValue({ items: [], hasMore: false })
    const wrapper = panel(); await flushPromises()
    expect(wrapper.text()).toContain('当前接口未提供同步开关状态')
    expect(wrapper.text()).not.toContain('没有已登记项目内的原生会话')
  })

  it('assembles across pages, verifies hash and hides incomplete messages', async () => {
    const original = await nativeExampleMessages('native_example_0')
    const part = original.items[0]; const split = Math.floor(part.text.length / 2)
    const first: NativeMessagePage = { ...original, hasMore: true, before: 'cursor_example', items: [{ ...part, text: part.text.slice(0, split), segmentCount: 2 }] }
    const second: NativeMessagePage = { ...original, items: [{ ...part, text: part.text.slice(split), segmentIndex: 1, segmentCount: 2 }] }
    const assembler = new NativeMessageAssembler()
    expect(await assembler.append(first)).toEqual([])
    expect((await assembler.append(second))[0].text).toBe(part.text)
    await expect(new NativeMessageAssembler().append({ ...original, items: [{ ...part, text: 'tampered' }] })).rejects.toThrow('校验失败')
    await expect(assembler.append({ ...second, sourceRevision: 'changed' })).rejects.toThrow('快照已变化')
  })
  it.each(['REMOTE_QUERY_TIMEOUT', 'REMOTE_QUERY_TOO_LARGE', 'NATIVE_SESSION_UNSUPPORTED'])('renders live read failure %s and correlation ID', async (code) => {
    vi.spyOn(remote, 'readNativeMessages').mockRejectedValue(new RemoteApiError({ code, status: 504, message: 'read failure', requestId: 'req_read_example' }))
    const wrapper = panel(); await flushPromises()
    await wrapper.findAll('button').find((b) => b.text().includes('示例：梳理项目结构'))!.trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain(nativeFailure({ code }).message); expect(wrapper.text()).toContain('req_read_example')
  })
  it('forces native remote and local submissions to continue and does not persist local content', async () => {
    const store = useRemoteChatStore(); store.runs = []; store.devices[0].supportedWireRevisions = [3]; store.activeConversation!.conversationKind = 'native'
    const send = vi.spyOn(remote, 'sendMessage')
    await store.sendMessage('合成原生消息', 'new')
    expect(send.mock.calls[0][1].sessionMode).toBe('continue')
    const native = await local.importNativeSession('native_example_0', { terminalClosedConfirmed: true, sourceRevision: 'example_source_revision', expectedIndexVersion: 1 })
    const chat = useChatStore(); chat.conversations = [native]; await chat.selectConversation(native.id)
    vi.spyOn(local, 'sendLocalMessage').mockRejectedValue(new HubApiError('网络测试', 'HUB_NOT_READY', 503))
    await expect(chat.sendMessage('仅内存的原生内容', 'new')).rejects.toThrow()
    expect(vi.mocked(local.sendLocalMessage).mock.calls[0][1].sessionMode).toBe('continue')
    expect(JSON.stringify(sessionStorage)).not.toContain('仅内存的原生内容'); expect(JSON.stringify(localStorage)).not.toContain('仅内存的原生内容')
  })
})

describe('R3 roots and workspace registration', () => {
  async function directory() {
    remote.catalog.authorizedRoots = [{ rootId: 'root_example', displayName: '授权开发目录', version: 1 }]
    await useRemoteChatStore().fetchCatalog()
    const wrapper = mount(RemoteWorkspaceDialog, options)
    await wrapper.get('button[aria-label="授权根目录"]').trigger('click'); await flushPromises()
    await wrapper.get('[role=option]').trigger('click'); await flushPromises()
    return wrapper
  }
  it('uses token breadcrumbs, returns to parent and warns for non-Git selections', async () => {
    const list = vi.spyOn(remote, 'listDirectory')
    const wrapper = await directory()
    await button(wrapper, '示例资料').trigger('click')
    expect(wrapper.text()).toContain('非 Git 仓库只能运行只读任务')
    await wrapper.findAll('button').find((b) => b.text() === '进入')!.trigger('click'); await flushPromises()
    expect(list.mock.calls.at(-1)?.[1].directoryToken).toBe('example_git_token')
    await button(wrapper, '返回上一层').trigger('click'); await flushPromises()
    expect(list.mock.calls.at(-1)?.[1].directoryToken).toBeUndefined()
    expect(JSON.stringify(list.mock.calls)).not.toContain('path')
  })
  it('clears stale tokens and returns to root after DIRECTORY_CHANGED', async () => {
    const wrapper = await directory()
    vi.spyOn(remote, 'listDirectory').mockRejectedValueOnce(new RemoteApiError({ code: 'REMOTE_DIRECTORY_CHANGED', status: 409, message: 'changed' }))
    await wrapper.findAll('button').find((b) => b.text() === '进入')!.trigger('click'); await flushPromises()
    expect(button(wrapper, '返回上一层')).toBeUndefined()
    expect(button(wrapper, '添加为项目').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('目录授权或目录内容已变化')
  })
  it('waits for 202 command and catalog projection before selecting registered project', async () => {
    vi.useFakeTimers()
    const wrapper = await directory()
    await button(wrapper, '示例资料').trigger('click')
    await button(wrapper, '添加为项目').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('正在电脑上添加项目…')
    expect(wrapper.emitted('selected')).toBeUndefined()
    await vi.advanceTimersByTimeAsync(1000); await flushPromises()
    expect(wrapper.emitted('selected')?.[0][0]).toMatch(/^workspace_registered_/)
    expect(useRemoteChatStore().catalog?.workspaces.at(-1)?.canWrite).toBe(false)
  })
  it('adds and removes local roots through picker and CAS; refreshes on conflict', async () => {
    const wrapper = mount(AuthorizedRootsSettings, options); await flushPromises()
    vi.spyOn(local, 'pickLocalDirectory').mockResolvedValue({ cancelled: false, selectedPath: 'E:/SyntheticRoot' })
    await button(wrapper, '选择目录添加').trigger('click'); await flushPromises()
    await wrapper.get('input').setValue('合成授权目录')
    const save = vi.spyOn(local, 'setAuthorizedRoots')
    await button(wrapper, '保存授权根目录').trigger('click'); await flushPromises()
    expect(save.mock.calls[0][0]).toEqual({ expectedVersion: 1, roots: [{ displayName: '合成授权目录', path: 'E:/SyntheticRoot' }] })
    local.authorizedRoots.version++
    await button(wrapper, '移除').trigger('click'); await button(wrapper, '保存授权根目录').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('授权根目录已变化')
    expect(wrapper.text()).toContain('E:/SyntheticRoot')
    await button(wrapper, '移除').trigger('click'); await button(wrapper, '保存授权根目录').trigger('click'); await flushPromises()
    expect(local.authorizedRoots.roots).toEqual([])
  })
  it('disables the new-task add-project entry when catalog has no authorized roots', async () => {
    const wrapper = mount(RemoteChatPage, options); await flushPromises()
    await button(wrapper, '新建任务').trigger('click'); await flushPromises()
    expect(button(wrapper, '添加项目').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('电脑未开放远程添加项目')
  })
  it('selects the registered project in the parent task form after catalog synchronization', async () => {
    vi.useFakeTimers()
    remote.catalog.authorizedRoots = [{ rootId: 'root_example', displayName: '根', version: 1 }]
    const wrapper = mount(RemoteChatPage, options); await flushPromises()
    await button(wrapper, '新建任务').trigger('click'); await flushPromises()
    await button(wrapper, '添加项目').trigger('click'); await flushPromises()
    await wrapper.get('button[aria-label="授权根目录"]').trigger('click'); await flushPromises()
    await wrapper.get('[role=option]').trigger('click'); await flushPromises()
    await button(wrapper, '示例资料').trigger('click')
    await button(wrapper, '添加为项目').trigger('click'); await flushPromises()
    await vi.advanceTimersByTimeAsync(1000); await flushPromises()
    expect(wrapper.get('#new-conv-workspace').text()).toBe('示例资料')
  })
  it('disables directory actions while suspended and leaves historic read available', async () => {
    const wrapper = await directory()
    useRemoteChatStore().devices[0].remoteAccess = 'suspended'
    await flushPromises()
    expect(wrapper.text()).toContain('这台电脑的远程操作已暂停')
    expect(button(wrapper, '添加为项目').attributes('disabled')).toBeDefined()
    expect(button(wrapper, '进入').attributes('disabled')).toBeDefined()
  })

  it('limits local roots to 32', async () => {
    local.authorizedRoots.roots = Array.from({ length: 32 }, (_, i) => ({ rootId: `root_${i}`, displayName: `根 ${i}`, path: `E:/Root${i}`, version: 1 }))
    const wrapper = mount(AuthorizedRootsSettings, options); await flushPromises()
    expect(button(wrapper, '选择目录添加').attributes('disabled')).toBeDefined()
  })
  it('uses actual pairing, offline and sync-disabled reasons; never claims success from a connection', () => {
    const sync = { mirrorEnabled: true, version: 1, syncGeneration: 1 }
    const paired: RemoteLinkView = { state: 'paired', serverOrigin: 'https://example.invalid', workerId: 'w', deviceName: 'PC', connectionStatus: 'online', lastConnectedAt: null }
    expect(nativeSyncNotice({ state: 'unpaired' }, sync)).toContain('尚未配对')
    expect(nativeSyncNotice({ ...paired, connectionStatus: 'offline' }, sync)).toContain('电脑离线')
    expect(nativeSyncNotice(paired, { ...sync, mirrorEnabled: false })).toContain('同步已关闭')
    expect(nativeSyncNotice(paired, sync)).toBe('已在本机导入，待连接支持修订 3 的服务后同步')
  })
})
