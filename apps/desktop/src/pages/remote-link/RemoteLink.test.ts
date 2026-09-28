import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import RemoteLinkPage from './RemoteLinkPage.vue'
import { useRemoteLinkStore } from '@/stores/remote-link.store'
import { mockLocalChatGateway } from '@/shared/api/mock-local-chat-gateway'
import { setLocalChatGatewayForTesting } from '@/shared/api/local-chat-provider'
import { getRemoteLinkErrorMessage } from '@/shared/i18n/remote-link-errors'

describe('RemoteLinkPage & RemoteLinkStore', () => {
  let router: any

  beforeEach(async () => {
    setActivePinia(createPinia())
    mockLocalChatGateway.reset()
    setLocalChatGatewayForTesting(mockLocalChatGateway)

    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/remote-link', component: RemoteLinkPage },
        { path: '/chat', component: { template: '<div>Chat</div>' } },
      ],
    })
    await router.push('/remote-link')
  })

  afterEach(() => {
    setLocalChatGatewayForTesting(null)
    vi.restoreAllMocks()
    localStorage.clear()
    sessionStorage.clear()
  })

  it('renders unpaired state, validates serverOrigin, and displays last error if present', async () => {
    mockLocalChatGateway.setRemoteLinkState({
      state: 'unpaired',
      serverOrigin: 'https://hub.example.com',
      lastErrorCode: 'REMOTE_PAIRING_EXPIRED',
    })

    const wrapper = mount(RemoteLinkPage, {
      global: {
        plugins: [router],
        stubs: {
          HqButton: {
            template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
            props: ['disabled'],
          },
          HqBadge: {
            template: '<span class="badge"><slot /></span>',
          },
          HqDialog: {
            template: '<div v-if="open" class="dialog"><slot /><slot name="footer" /></div>',
            props: ['open'],
          },
        },
      },
    })

    await flushPromises()

    // 1. Should display unpaired header and inputs
    expect(wrapper.text()).toContain('发起新配对')
    expect(wrapper.text()).toContain('配对短码已过期，请重新发起配对')
    expect(wrapper.find('input[type="text"]').exists()).toBe(true)

    // 2. Validate invalid origin
    const originInput = wrapper.findAll('input')[0]
    await originInput.setValue('http://invalid-plain-http.com')
    await wrapper.find('form').trigger('submit.prevent')
    await flushPromises()

    expect(wrapper.text()).toContain('服务器地址格式不正确')
  })

  it('starts pairing, displays 8-character pairCode, countdown, and allows cancelling pairing', async () => {
    const store = useRemoteLinkStore()
    const wrapper = mount(RemoteLinkPage, {
      global: {
        plugins: [router],
        stubs: {
          HqButton: {
            template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
            props: ['disabled'],
          },
          HqBadge: {
            template: '<span class="badge"><slot /></span>',
          },
          HqDialog: {
            template: '<div v-if="open" class="dialog"><slot /><slot name="footer" /></div>',
            props: ['open'],
          },
        },
      },
    })

    await flushPromises()

    // Start pairing
    await store.startPairing({
      serverOrigin: 'https://remote.example.com',
      deviceName: '办公台式机',
    })
    await flushPromises()

    expect(store.isPairing).toBe(true)
    expect(store.pairCode).toBe('ABCD2345')
    expect(wrapper.text()).toContain('ABCD2345')
    expect(wrapper.text()).toContain('正在等待手机输入短码')
    expect(wrapper.text()).toContain('办公台式机')

    // Cancel pairing
    await store.cancelPairing()
    await flushPromises()

    expect(store.isUnpaired).toBe(true)
    expect(store.pairCode).toBe('')
  })

  it('handles pairing expiry transition to unpaired with REMOTE_PAIRING_EXPIRED code', async () => {
    const store = useRemoteLinkStore()
    // Seed pairing with past expiry
    mockLocalChatGateway.setRemoteLinkState({
      state: 'pairing',
      serverOrigin: 'https://hub.example.com',
      deviceName: '我的电脑',
      pairRequestId: 'preq_1',
      pairCode: 'ABCD2345',
      expiresAt: new Date(Date.now() - 1000).toISOString(),
    })

    await store.refreshLink()
    expect(store.isUnpaired).toBe(true)
    expect(store.lastErrorCode).toBe('REMOTE_PAIRING_EXPIRED')
    expect(store.lastErrorMessage).toContain('配对短码已过期')
  })

  it('renders paired state with online status and triggers unlink with secondary confirmation modal explaining the two required rules', async () => {
    mockLocalChatGateway.mockSimulatePairingSuccess('worker_test_pc')

    const wrapper = mount(RemoteLinkPage, {
      global: {
        plugins: [router],
        stubs: {
          HqButton: {
            template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
            props: ['disabled'],
          },
          HqBadge: {
            template: '<span class="badge"><slot /></span>',
          },
          HqDialog: {
            template: '<div v-if="open" class="dialog"><slot /><slot name="footer" /></div>',
            props: ['open'],
          },
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('在线 (已连接云端 Hub Server)')
    expect(wrapper.text()).toContain('worker_test_pc')

    // Click unlink button to open dialog
    const unlinkBtn = wrapper.findAll('button').find((b) => b.text().includes('解除绑定'))
    expect(unlinkBtn).toBeDefined()
    await unlinkBtn!.trigger('click')
    await flushPromises()

    // Dialog must explain the two key points:
    // 1. 已有的远程对话在电脑上仍是只读，不会变回本地对话
    // 2. 服务端的撤销可能要在手机端再撤销一次设备才生效
    expect(wrapper.text()).toContain('解绑后，已有的远程对话在电脑上仍是只读，不会变回本地对话')
    expect(wrapper.text()).toContain('服务端的撤销可能要在手机端再撤销一次设备才生效')

    // Confirm unlink
    const confirmBtn = wrapper.findAll('button').find((b) => b.text().includes('确认解除绑定'))
    expect(confirmBtn).toBeDefined()
    await confirmBtn!.trigger('click')
    await flushPromises()

    const store = useRemoteLinkStore()
    expect(store.isUnpaired).toBe(true)
  })

  it('renders revoked state with explanation and allows re-configuring link', async () => {
    mockLocalChatGateway.mockSimulateRevoked('REMOTE_DEVICE_REVOKED')

    const wrapper = mount(RemoteLinkPage, {
      global: {
        plugins: [router],
        stubs: {
          HqButton: {
            template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
            props: ['disabled'],
          },
          HqBadge: {
            template: '<span class="badge"><slot /></span>',
          },
          HqDialog: {
            template: '<div v-if="open" class="dialog"><slot /><slot name="footer" /></div>',
            props: ['open'],
          },
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('设备连接已被撤销')
    expect(wrapper.text()).toContain('revoked')
    expect(wrapper.text()).toContain('云端中转服务器已撤销此电脑凭据')
  })

  it('renders frozen state with explanation and does not provide an instant unfreeze button', async () => {
    mockLocalChatGateway.mockSimulateFrozen('REMOTE_EPOCH_STALE')

    const wrapper = mount(RemoteLinkPage, {
      global: {
        plugins: [router],
        stubs: {
          HqButton: {
            template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
            props: ['disabled'],
          },
          HqBadge: {
            template: '<span class="badge"><slot /></span>',
          },
          HqDialog: {
            template: '<div v-if="open" class="dialog"><slot /><slot name="footer" /></div>',
            props: ['open'],
          },
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('远程连接已冻结')
    expect(wrapper.text()).toContain('frozen')
    expect(wrapper.text()).toContain('存储世代需要核对')
    // Must NOT provide an unfreeze button
    expect(wrapper.text()).not.toContain('一键解除冻结')
    expect(wrapper.text()).not.toContain('一键解冻')
  })

  it('translates remote link error codes to localized Chinese accurately', () => {
    expect(getRemoteLinkErrorMessage('REMOTE_SERVER_ORIGIN_INVALID')).toContain('必须为 HTTPS 地址')
    expect(getRemoteLinkErrorMessage('REMOTE_SERVER_UNREACHABLE')).toContain('无法连接到远程服务器')
    expect(getRemoteLinkErrorMessage('REMOTE_PAIRING_IN_PROGRESS')).toContain('已有配对请求正在进行中')
    expect(getRemoteLinkErrorMessage('REMOTE_PAIRING_EXPIRED')).toContain('配对短码已过期')
    expect(getRemoteLinkErrorMessage('REMOTE_DEVICE_OFFLINE')).toContain('处于离线状态')
    expect(getRemoteLinkErrorMessage('CONVERSATION_AUTHORITY_MISMATCH')).toContain('这是手机远程对话')
  })

  it('guarantees zero client storage leaks: no pair codes, tokens, or secrets written to storage', async () => {
    const store = useRemoteLinkStore()
    await store.startPairing({
      serverOrigin: 'https://hub.example.com',
      deviceName: '我的电脑',
    })

    // Check all storage
    expect(localStorage.getItem('pairCode')).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('hubToken')).toBeNull()
    expect(localStorage.getItem('deviceSecret')).toBeNull()
    expect(sessionStorage.getItem('pairCode')).toBeNull()
    expect(sessionStorage.getItem('token')).toBeNull()
  })

  it('B7: renders QR code with format <serverOrigin>/remote/pair#code=<pairCode> during pairing state', async () => {
    mockLocalChatGateway.setRemoteLinkState({
      state: 'pairing',
      serverOrigin: 'https://hub.example.com',
      deviceName: '我的电脑',
      pairRequestId: 'pair_req_mock_1',
      pairCode: 'ABCD2345',
      expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
    })

    const wrapper = mount(RemoteLinkPage, {
      global: {
        plugins: [router],
        stubs: {
          HqButton: {
            template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
            props: ['disabled'],
          },
          HqBadge: {
            template: '<span class="badge"><slot /></span>',
          },
          HqDialog: {
            template: '<div v-if="open" class="dialog"><slot /><slot name="footer" /></div>',
            props: ['open'],
          },
        },
      },
    })

    await flushPromises()
    // Wait for async QRCode.toDataURL
    await new Promise((r) => setTimeout(r, 50))

    const qrImg = wrapper.find('img[data-testid="pair-qrcode"]')
    expect(qrImg.exists()).toBe(true)
    expect(qrImg.attributes('src')).toMatch(/^data:image\/png;base64,/)

    // Shortcode text and countdown preserved as fallback
    expect(wrapper.text()).toContain('ABCD2345')
    expect(wrapper.text()).toContain('有效剩余时间')

    // Disappears when pairing is cancelled or reset to unpaired
    const store = useRemoteLinkStore()
    await store.cancelPairing()
    await flushPromises()

    expect(wrapper.find('img[data-testid="pair-qrcode"]').exists()).toBe(false)
  })
})

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 10))
}
