import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import RemotePairingPage from './RemotePairingPage.vue'
import { mockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'

describe('RemotePairingPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setRemoteGatewayForTesting(mockRemoteGateway)
    mockRemoteGateway.pairingErrorCode = null
  })

  afterEach(() => {
    setRemoteGatewayForTesting(null)
    vi.restoreAllMocks()
  })

  it('formats input to 8 uppercase alphanumeric characters and fetches preview', async () => {
    const wrapper = mount(RemotePairingPage)
    const input = wrapper.find('input#pair-code')

    await input.setValue('abcd-1234')
    // Auto-formatted to 8 chars uppercase
    expect((input.element as HTMLInputElement).value).toBe('ABCD1234')

    const previewBtn = wrapper.find('[data-testid="preview-btn"]')
    expect(previewBtn.text()).toContain('获取设备预览')
    await previewBtn.trigger('click')
    await flushPromises()

    // Preview card is rendered
    expect(wrapper.text()).toContain('Office PC (Alex)')
    expect(wrapper.text()).toContain('windows')
    expect(wrapper.text()).toContain('x86_64')
    expect(wrapper.text()).toContain('待绑定')
  })

  it('handles REMOTE_PAIRING_EXPIRED error correctly', async () => {
    mockRemoteGateway.pairingErrorCode = 'REMOTE_PAIRING_EXPIRED'
    const wrapper = mount(RemotePairingPage)
    const input = wrapper.find('input#pair-code')

    await input.setValue('EXPIRED0')
    const previewBtn = wrapper.find('[data-testid="preview-btn"]')
    await previewBtn.trigger('click')
    await flushPromises()

    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.find('[role="alert"]').text()).toContain('配对请求或配对短码已过期')
  })

  it('handles REMOTE_PAIRING_CONFLICT error correctly', async () => {
    mockRemoteGateway.pairingErrorCode = 'REMOTE_PAIRING_CONFLICT'
    const wrapper = mount(RemotePairingPage)
    const input = wrapper.find('input#pair-code')

    await input.setValue('CONFLICT')
    const previewBtn = wrapper.find('[data-testid="preview-btn"]')
    await previewBtn.trigger('click')
    await flushPromises()

    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.find('[role="alert"]').text()).toContain('该配对短码已绑定或已被其他用户认领')
  })

  it('handles REMOTE_PAIRING_INVALID error correctly', async () => {
    mockRemoteGateway.pairingErrorCode = 'REMOTE_PAIRING_INVALID'
    const wrapper = mount(RemotePairingPage)
    const input = wrapper.find('input#pair-code')

    await input.setValue('INVALID0')
    const previewBtn = wrapper.find('[data-testid="preview-btn"]')
    await previewBtn.trigger('click')
    await flushPromises()

    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.find('[role="alert"]').text()).toContain('配对短码无效')
  })

  it('B7: reads shortcode from location.hash, immediately clears hash, auto-fills code and triggers preview without auto-binding', async () => {
    const replaceStateSpy = vi.spyOn(window.history, 'replaceState')
    window.location.hash = '#code=ABCD2345'
    const confirmSpy = vi.spyOn(mockRemoteGateway, 'confirmPairing')

    const wrapper = mount(RemotePairingPage)
    await flushPromises()

    // 1. Hash is cleared from address bar
    expect(replaceStateSpy).toHaveBeenCalled()

    // 2. Pair code is automatically populated
    const input = wrapper.find<HTMLInputElement>('input#pair-code')
    expect(input.element.value).toBe('ABCD2345')

    // 3. Preview card is automatically displayed
    expect(wrapper.text()).toContain('Office PC (Alex)')
    expect(wrapper.text()).toContain('windows')
    expect(wrapper.text()).toContain('待绑定')

    // 4. Must NOT auto-bind without explicit user confirmation
    expect(confirmSpy).not.toHaveBeenCalled()

    // 5. User explicitly confirms
    const confirmBtn = wrapper.findAll('button').find((b) => b.text().includes('确认绑定并建立连接'))
    expect(confirmBtn).toBeDefined()
    await confirmBtn?.trigger('click')
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalledWith('pair_demo', { pairCode: 'ABCD2345' })
    expect(wrapper.text()).toContain('设备绑定成功！')
  })

  it('B7: ignores invalid code in location.hash and does not trigger preview', async () => {
    window.location.hash = '#code=INVALID_LONG'

    const wrapper = mount(RemotePairingPage)
    await flushPromises()

    const input = wrapper.find<HTMLInputElement>('input#pair-code')
    expect(input.element.value).toBe('')
    expect(wrapper.text()).not.toContain('Office PC (Alex)')
    expect(wrapper.find('[data-testid="preview-btn"]').exists()).toBe(true)
  })

  it('B7: unauthenticated user preserves code in memory via authStore across login with zero storage leaks', async () => {
    const authStore = (await import('@/stores/remote-auth.store')).useRemoteAuthStore()
    authStore.pendingPairCode = 'XYZ98765'

    const wrapper = mount(RemotePairingPage)
    await flushPromises()

    // Picked up from in-memory pendingPairCode
    const input = wrapper.find<HTMLInputElement>('input#pair-code')
    expect(input.element.value).toBe('XYZ98765')
    // In-memory ref consumed
    expect(authStore.pendingPairCode).toBeNull()

    // Zero storage leaks audit
    expect(localStorage.getItem('pairCode')).toBeNull()
    expect(localStorage.getItem('code')).toBeNull()
    expect(sessionStorage.getItem('pairCode')).toBeNull()
    expect(sessionStorage.getItem('code')).toBeNull()
  })
})
