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
})
