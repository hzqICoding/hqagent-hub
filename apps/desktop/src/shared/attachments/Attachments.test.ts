import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { File as NodeFile, Blob as NodeBlob } from 'node:buffer'
import { createHash } from 'node:crypto'
import { mount, flushPromises, enableAutoUnmount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import type { ImageInputCapability, AttachmentTargetCapabilities, MessageAttachmentView } from '@hqagent/protocol'
import AttachmentDrafts from './AttachmentDrafts.vue'
import AttachmentItem from './AttachmentItem.vue'
import RemoteChatPage from '@/pages/remote/RemoteChatPage.vue'
import ChatComposer from '@/pages/chat/components/ChatComposer.vue'
import { MockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { MockLocalChatGateway } from '@/shared/api/mock-local-chat-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'
import { setLocalChatGatewayForTesting } from '@/shared/api/local-chat-provider'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { useChatStore } from '@/stores/chat.store'
import { RemoteApiError, HubApiError } from '@/shared/api'
import { validateImageCapabilities } from './validation'
import { IncrementalSha256 } from './sha256'

enableAutoUnmount(afterEach)
let remote: MockRemoteGateway, local: MockLocalChatGateway
const file = (name = 'example.txt', bytes = new TextEncoder().encode('synthetic attachment')) => new NodeFile([bytes], name) as unknown as File
const image = () => file('example.png', new Uint8Array([137,80,78,71,13,10,26,10,0,0,0]))
const supported: ImageInputCapability = { support: 'supported', cliEntry: 'supported', runtimeImplemented: true, verified: true, mimeTypes: ['image/png'], maxBytes: 10000000 }
const options = { global: { stubs: { Teleport: true } } }
async function upload(remoteMode = true, attachmentFile = file()) {
  const blob = new Uint8Array(await attachmentFile.arrayBuffer())
  const gateway = remoteMode ? remote : local
  return gateway.uploadAttachment(remoteMode ? 'conversation_demo' : 'conv_analyze_router', attachmentFile, { fileName: attachmentFile.name, sha256: new IncrementalSha256().update(blob).hex(), idempotencyKey: crypto.randomUUID() })
}
async function choose(wrapper: VueWrapper, files: File[]) {
  const input = wrapper.get('[data-testid=select-files]')
  Object.defineProperty(input.element, 'files', { value: files, configurable: true })
  await input.trigger('change'); await flushPromises()
}
const button = (wrapper: VueWrapper, label: string) => wrapper.findAll('button').find((b) => b.text() === label)!

beforeEach(async () => {
  setActivePinia(createPinia()); localStorage.clear(); sessionStorage.clear()
  remote = new MockRemoteGateway(); remote.reset(); remote.runs = []; remote.commands = []; remote.devices[0].supportedWireRevisions = [2,3,4]
  local = new MockLocalChatGateway()
  setRemoteGatewayForTesting(remote); setLocalChatGatewayForTesting(local)
  const URLBase = URL
  vi.stubGlobal('URL', class extends URLBase { static createObjectURL = vi.fn(() => 'blob:synthetic-preview'); static revokeObjectURL = vi.fn() })
  await useRemoteChatStore().fetchDevices(); await useRemoteChatStore().selectDevice('worker_demo')
})
afterEach(() => { useRemoteChatStore().reset(); useChatStore().stopPolling(); setRemoteGatewayForTesting(null); setLocalChatGatewayForTesting(null); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

describe('attachment selection and drafts', () => {
  it('loads limits, uploads sequential raw files and deletes an unsent item', async () => {
    const send = vi.spyOn(remote, 'uploadAttachment')
    const remove = vi.spyOn(remote, 'deleteAttachment')
    const wrapper = mount(AttachmentDrafts, { props: { conversationId: 'conversation_demo', remote: true }, ...options })
    await choose(wrapper, [file()])
    await vi.waitFor(() => expect(wrapper.findAll('[data-testid=attachment-status]').some((s) => s.text() === '已上传')).toBe(true))
    expect(send.mock.calls[0][1]).toBeInstanceOf(NodeFile)
    expect(send.mock.calls[0][2].sha256).toBe(createHash('sha256').update('synthetic attachment').digest('hex'))
    expect(wrapper.text()).toContain('24 小时清理')
    await wrapper.get('[aria-label="移除 example.txt"]').trigger('click'); await flushPromises()
    expect(remove).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).not.toContain('example.txt')
    expect(JSON.stringify(localStorage)).not.toContain('synthetic attachment'); expect(JSON.stringify(sessionStorage)).not.toContain('synthetic attachment')
  })
  it.each(['count','quota','size','type','empty'])('rejects %s limits during selection without uploading invalid files', async (kind) => {
    const send = vi.spyOn(remote, 'uploadAttachment')
    if (kind === 'quota') vi.spyOn(remote, 'getAttachmentLimits').mockResolvedValue({ limits: remote.attachmentLibrary.limits, usedBytes: remote.attachmentLibrary.limits.accountQuotaBytes, reservedBytes: 0, observedAt: new Date().toISOString() })
    const oversized = file(); Object.defineProperty(oversized, 'size', { value: remote.attachmentLibrary.limits.fileMaxBytes + 1 })
    const files = kind === 'count' ? Array.from({ length: 6 }, (_, i) => file(`example${i}.txt`)) : [kind === 'size' ? oversized : kind === 'type' ? file('bad.svg') : kind === 'empty' ? file('empty.txt',new Uint8Array()) : file()]
    const wrapper = mount(AttachmentDrafts, { props: { conversationId: 'conversation_demo', remote: true }, ...options })
    await choose(wrapper, files)
    await vi.waitFor(() => expect(wrapper.find('[role=alert]').exists()).toBe(true))
    if (kind !== 'count') expect(send).not.toHaveBeenCalled()
    else expect(wrapper.text()).toContain('最多 5 个附件')
  })
  it('keeps upload failure visible and reuses its idempotency key only on manual retry', async () => {
    const send = vi.spyOn(remote, 'uploadAttachment').mockRejectedValueOnce(new RemoteApiError({ code: 'ATTACHMENT_HASH_MISMATCH', status: 422, message: 'hash mismatch' }))
    const wrapper = mount(AttachmentDrafts, { props: { conversationId: 'conversation_demo', remote: true }, ...options })
    await choose(wrapper, [file()]); await vi.waitFor(() => expect(wrapper.text()).toContain('上传失败'))
    expect(send).toHaveBeenCalledTimes(1)
    await button(wrapper, '重试上传').trigger('click'); await vi.waitFor(() => expect(wrapper.findAll('[data-testid=attachment-status]').some((s) => s.text() === '已上传')).toBe(true))
    expect(send.mock.calls[0][2].idempotencyKey).toBe(send.mock.calls[1][2].idempotencyKey)
  })
  it('blocks uploads while suspended, even when a chooser event fires', async () => {
    const send = vi.spyOn(remote, 'uploadAttachment')
    const wrapper = mount(AttachmentDrafts, { props: { conversationId: 'conversation_demo', remote: true, suspended: true }, ...options })
    await choose(wrapper, [file()]); expect(send).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('远程操作已暂停')
  })
  it('allows offline staging and explains retention without claiming send success', async () => {
    const wrapper = mount(AttachmentDrafts, { props: { conversationId: 'conversation_demo', remote: true, offline: true }, ...options })
    await choose(wrapper, [file()]); await vi.waitFor(() => expect(wrapper.findAll('[data-testid=attachment-status]').some((s) => s.text() === '已上传')).toBe(true))
    expect(wrapper.text()).toContain('电脑离线，发送失败'); expect(wrapper.text()).toContain('24 小时清理')
  })
})

describe('attachment sending', () => {
  it('rejects images when any role, layer, MIME or size capability is missing', async () => {
    const record = await upload(true, image())
    const target: AttachmentTargetCapabilities = { conversationKind: 'scenario', capabilityRevision: 1, roles: [{ roleId: 'planner', agentId: 'a', imageInput: supported }, { roleId: 'reviewer', agentId: 'b', imageInput: { ...supported, support: 'unknown' } }] }
    expect(() => validateImageCapabilities([record.attachment], target)).toThrow('当前 Agent 不支持图片')
    for (const partial of [{ cliEntry: 'unknown' as const }, { runtimeImplemented: false }, { verified: false }, { maxBytes: 1 }, { mimeTypes: [] }]) {
      target.roles = [{ roleId: 'r', agentId: 'a', imageInput: { ...supported, ...partial } }]
      expect(() => validateImageCapabilities([record.attachment], target)).toThrow('当前 Agent 不支持图片')
    }
    expect(() => validateImageCapabilities([record.attachment])).toThrow('当前 Agent 不支持图片')
    expect(() => validateImageCapabilities([record.attachment], { conversationKind: 'native', capabilityRevision: 1, roles: [], native: { agentType: 'codex', imageInput: supported } })).not.toThrow()
  })
  it('fetches all current catalog capabilities before remote send and carries only IDs', async () => {
    const record = await upload(true, image())
    const store = useRemoteChatStore(); const send = vi.spyOn(remote, 'sendMessage')
    await expect(store.sendMessage('合成图片问题', 'continue', undefined, [record.attachment.attachmentId])).rejects.toThrow('当前 Agent 不支持图片')
    expect(send).not.toHaveBeenCalled()
    remote.catalog.scenes[0].roleImageCapabilities = [{ roleId: 'analyst', agentId: 'mock', imageInput: supported }]
    await store.sendMessage('合成图片问题', 'continue', undefined, [record.attachment.attachmentId])
    expect(send.mock.calls[0][1].attachmentIds).toEqual([record.attachment.attachmentId])
    expect(send.mock.calls[0][1]).not.toHaveProperty('attachments')
    expect(send.mock.calls[0][1]).not.toHaveProperty('file')
  })
  it('preserves remote draft and staged attachments after server image rejection', async () => {
    const wrapper = mount(RemoteChatPage, options); await flushPromises()
    const send = vi.spyOn(remote, 'sendMessage').mockRejectedValueOnce(new RemoteApiError({ code: 'AGENT_IMAGE_UNSUPPORTED', status: 422, message: '当前 Agent 不支持图片' }))
    await choose(wrapper, [file()]); await vi.waitFor(() => expect(wrapper.findAll('[data-testid=attachment-status]').some((s) => s.text() === '已上传')).toBe(true))
    await wrapper.get('textarea').setValue('保留附件问题')
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter' }); await flushPromises()
    expect(send).toHaveBeenCalledTimes(1)
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('保留附件问题')
    expect(wrapper.text()).toContain('当前 Agent 不支持图片'); expect(wrapper.text()).toContain('example.txt')
  })
  it('retains offline uploads and performs no send request', async () => {
    const record = await upload()
    const send = vi.spyOn(remote, 'sendMessage'); useRemoteChatStore().devices[0].online = false
    await expect(useRemoteChatStore().sendMessage('offline', 'continue', undefined, [record.attachment.attachmentId])).rejects.toMatchObject({ code: 'REMOTE_DEVICE_OFFLINE' })
    expect(send).not.toHaveBeenCalled(); expect(remote.attachmentLibrary.records.size).toBe(1)
  })
  it('keeps retry identity for a remotely reserved attachment after a lost response', async () => {
    const record = await upload(); const send = vi.spyOn(remote, 'sendMessage').mockRejectedValue(new RemoteApiError({ code: 'NETWORK_ERROR', status: 0, message: 'network' }))
    const store = useRemoteChatStore()
    await expect(store.sendMessage('retry', 'continue', undefined, [record.attachment.attachmentId])).rejects.toThrow()
    record.state = 'reserved'
    await expect(store.sendMessage('retry', 'continue', undefined, [record.attachment.attachmentId])).rejects.toThrow()
    expect(send.mock.calls[0][1].clientMessageId).toBe(send.mock.calls[1][1].clientMessageId)
    expect(JSON.stringify(sessionStorage)).not.toContain(record.attachment.attachmentId)
  })
  it('preserves local text and attachment draft on failure without sessionStorage payloads', async () => {
    const chat = useChatStore(); await chat.init(); chat.activeConversationId = 'conv_analyze_router'
    // Select a new non-busy conversation using the existing fixture scene.
    const conv = await local.createLocalConversation({ title: '附件测试', workspaceId: chat.workspaces[0].id, sceneId: 'analyze' })
    chat.conversations.unshift(conv); await chat.selectConversation(conv.id)
    const wrapper = mount(ChatComposer, options)
    await choose(wrapper, [file()]); await vi.waitFor(() => expect(wrapper.findAll('[data-testid=attachment-status]').some((s) => s.text() === '已上传')).toBe(true))
    vi.spyOn(local, 'sendLocalMessage').mockRejectedValue(new HubApiError('发送失败', 'HUB_NOT_READY', 503))
    await wrapper.get('textarea').setValue('附件输入应保留')
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter' }); await flushPromises()
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('附件输入应保留')
    expect(wrapper.text()).toContain('example.txt')
    expect(JSON.stringify(sessionStorage)).not.toContain('附件输入应保留')
  })
})

describe('attachment display', () => {
  it.each(['pending_upload','unavailable'] as const)('never offers a remote download for %s', async (availability) => {
    const record = await upload(); const wrapper = mount(AttachmentItem, { props: { attachment: { ...record.attachment, availability } as MessageAttachmentView, remote: true } })
    await flushPromises(); expect(wrapper.find('[aria-label^="下载"]').exists()).toBe(false)
    expect(wrapper.text()).toContain(availability === 'pending_upload' ? '附件待上传' : '附件不可用')
  })
  it('uses only generated thumbnails and revokes their blob URL on unmount', async () => {
    const record = await upload(true, image())
    const metadata = remote.attachmentLibrary.get(record.attachment.attachmentId).remote.attachment
    metadata.thumbnailStatus = 'ready'
    const thumbnail = vi.spyOn(remote, 'getAttachmentThumbnail').mockResolvedValue(new NodeBlob([new Uint8Array([137,80,78,71,13,10,26,10])], { type: 'image/png' }) as unknown as Blob)
    const original = vi.spyOn(remote, 'getAttachmentContent')
    const wrapper = mount(AttachmentItem, { props: { attachment: metadata, remote: true } })
    await vi.waitFor(() => expect(wrapper.find('img').exists()).toBe(true))
    expect(thumbnail).toHaveBeenCalledTimes(1); expect(original).not.toHaveBeenCalled()
    wrapper.unmount(); expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:synthetic-preview')
  })
  it('never falls back to original if thumbnail is unavailable or wrong MIME', async () => {
    const record = await upload(true, image()); const metadata = remote.attachmentLibrary.get(record.attachment.attachmentId).remote.attachment; metadata.thumbnailStatus = 'ready'
    vi.spyOn(remote, 'getAttachmentThumbnail').mockResolvedValue(new NodeBlob(['<svg/>'],{type:'image/svg+xml'}) as unknown as Blob)
    const original = vi.spyOn(remote, 'getAttachmentContent')
    const wrapper = mount(AttachmentItem, { props: { attachment: metadata, remote: true } }); await flushPromises()
    expect(wrapper.find('img').exists()).toBe(false); expect(original).not.toHaveBeenCalled()
  })
  it('downloads originals only through a temporary octet-stream URL and releases it', async () => {
    const record = await upload()
    vi.useFakeTimers()
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const wrapper = mount(AttachmentItem, { props: { attachment: record.attachment as MessageAttachmentView, remote: true } })
    await wrapper.get('[aria-label^="下载"]').trigger('click')
    await vi.advanceTimersByTimeAsync(1100); await flushPromises()
    expect(click).toHaveBeenCalledTimes(1)
    expect(vi.mocked(URL.createObjectURL).mock.calls[0][0]).toMatchObject({ type: 'application/octet-stream' })
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:synthetic-preview')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('iframe').exists()).toBe(false)
  })
  it('does not create a thumbnail URL from a late result after unmount', async () => {
    const record = await upload(true, image())
    const metadata = { ...record.attachment, thumbnailStatus: 'ready' as const } as MessageAttachmentView
    let resolve!: (blob: Blob) => void
    vi.spyOn(remote, 'getAttachmentThumbnail').mockImplementation(() => new Promise((done) => { resolve = done }))
    const wrapper = mount(AttachmentItem, { props: { attachment: metadata, remote: true } })
    await flushPromises(); wrapper.unmount()
    resolve(new NodeBlob([new Uint8Array([137,80,78,71,13,10,26,10])],{type:'image/png'}) as unknown as Blob)
    await flushPromises()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })
  it('renders file icons for pending thumbnails instead of fetching originals', async () => {
    const record = await upload(true, image())
    const original = vi.spyOn(remote, 'getAttachmentContent'), thumbnail = vi.spyOn(remote, 'getAttachmentThumbnail')
    const wrapper = mount(AttachmentItem, { props: { attachment: record.attachment as MessageAttachmentView, remote: true } })
    await flushPromises()
    expect(wrapper.text()).toContain('缩略图生成中')
    expect(original).not.toHaveBeenCalled(); expect(thumbnail).not.toHaveBeenCalled()
  })

  it('keeps local download enabled despite cloud sync failure and does not request a thumbnail', async () => {
    const record = await upload(false, image()); const metadata = local.attachmentLibrary.get(record.attachment.attachmentId).local
    metadata.syncStatus = 'unavailable'; metadata.syncError = 'ATTACHMENT_QUOTA_EXCEEDED'
    const thumbnail = vi.spyOn(local,'getAttachmentThumbnail')
    const wrapper = mount(AttachmentItem, { props: { attachment: metadata.attachment } }); await flushPromises()
    expect(wrapper.text()).toContain('本机可用 · 同步失败'); expect(wrapper.find('[aria-label^="下载"]').exists()).toBe(true)
    expect(thumbnail).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('不影响本机使用')
  })
})
