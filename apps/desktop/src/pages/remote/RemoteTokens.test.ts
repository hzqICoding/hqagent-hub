import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { mount, flushPromises, enableAutoUnmount, type VueWrapper } from '@vue/test-utils'
import type { RemoteApiTokenIssuedView, RemoteApiTokenView } from '@hqagent/protocol'
import RemoteTokensPage from './RemoteTokensPage.vue'
import { MockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'
import { remoteRequestFailure } from '@/shared/api/remote-diagnostics'

enableAutoUnmount(afterEach)
let gateway: MockRemoteGateway
let pinia: Pinia
const token: RemoteApiTokenView = { tokenId: 'pat_example', name: '测试工具', tokenPrefix: 'hqr_pat_example', scopes: ['devices:read'], createdAt: '2026-09-01T00:00:00Z', expiresAt: '2026-12-01T00:00:00Z', status: 'active' }
beforeEach(() => {
  pinia = createPinia(); setActivePinia(pinia)
  gateway = new MockRemoteGateway(); gateway.reset()
  setRemoteGatewayForTesting(gateway)
  localStorage.clear(); sessionStorage.clear(); remoteRequestFailure.value = null
})
afterEach(() => { setRemoteGatewayForTesting(null); vi.restoreAllMocks() })
async function page() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/remote/tokens', component: RemoteTokensPage }, { path: '/remote/devices', component: { template: '<div>Devices</div>' } }] })
  await router.push('/remote/tokens')
  const wrapper = mount(RemoteTokensPage, { attachTo: document.body, global: { plugins: [router], stubs: { Teleport: true } } })
  await flushPromises()
  return wrapper
}
async function openIssue(wrapper: VueWrapper) {
  await wrapper.findAll('button').find((b) => b.text() === '新建令牌')!.trigger('click')
  await wrapper.get('[aria-label="令牌名称"]').setValue('开发机工具')
  await wrapper.get('input[value="devices:read"]').setValue(true)
}
const button = (wrapper: VueWrapper, text: string) => wrapper.findAll('button').find((b) => b.text() === text)!

describe('D50 API token page', () => {
  it('keeps scopes independent and only warns about deletion when explicitly checked', async () => {
    const wrapper = await page()
    await openIssue(wrapper)
    await wrapper.get('input[value="devices:manage"]').setValue(true)
    expect((wrapper.get('input[value="devices:delete"]').element as HTMLInputElement).checked).toBe(false)
    expect(wrapper.text()).not.toContain('删除是破坏性操作')
    await wrapper.get('input[value="devices:delete"]').setValue(true)
    expect(wrapper.text()).toContain('删除是破坏性操作')
    await wrapper.get('input[value="devices:delete"]').setValue(false)
    await wrapper.get('input[value="devices:read"]').setValue(false)
    const issue = vi.spyOn(gateway, 'issueApiToken')
    await button(wrapper, '签发令牌').trigger('click'); await flushPromises()
    expect(issue.mock.calls[0][0]).toEqual({ name: '开发机工具', scopes: ['devices:manage'] })
  })

  it('shows the secret only in its dialog and clears it on close without storage or store leakage', async () => {
    const wrapper = await page()
    await openIssue(wrapper)
    await button(wrapper, '签发令牌').trigger('click'); await flushPromises()
    const secret = wrapper.get('[data-testid="issued-secret"]').text()
    expect(secret).toContain('hqr_pat_')
    expect(wrapper.text()).toContain('关闭后无法再次查看')
    expect(wrapper.get('main').text()).not.toContain(secret)
    expect(JSON.stringify(pinia.state.value)).not.toContain(secret)
    expect(JSON.stringify(gateway.apiTokens)).not.toContain(secret)
    await button(wrapper, '关闭').trigger('click'); await flushPromises()
    expect(document.body.textContent).not.toContain(secret)
    expect(JSON.stringify(pinia.state.value)).not.toContain(secret)
    expect(JSON.stringify(localStorage)).not.toContain('hqr_pat_')
    expect(JSON.stringify(sessionStorage)).not.toContain('hqr_pat_')
    await button(wrapper, '新建令牌').trigger('click')
    expect(wrapper.find('[data-testid="issued-secret"]').exists()).toBe(false)
  })

  it('discards an issuance response that arrives after the dialog closes', async () => {
    let resolve!: (result: RemoteApiTokenIssuedView) => void
    vi.spyOn(gateway, 'issueApiToken').mockImplementation(() => new Promise((done) => { resolve = done }))
    const wrapper = await page(); await openIssue(wrapper)
    await button(wrapper, '签发令牌').trigger('click')
    await button(wrapper, '取消').trigger('click')
    resolve({ secretAvailable: true, secret: 'hqr_pat_EXAMPLE_LATE_SECRET', token })
    await flushPromises()
    expect(wrapper.text()).not.toContain('hqr_pat_EXAMPLE_LATE_SECRET')
    expect(JSON.stringify(pinia.state.value)).not.toContain('hqr_pat_')
  })

  it('shows metadata-only replay and offers revocation with a second confirmation', async () => {
    gateway.apiTokens = [{ ...token }]
    vi.spyOn(gateway, 'issueApiToken').mockResolvedValue({ secretAvailable: false, token })
    const revoke = vi.spyOn(gateway, 'revokeApiToken')
    const wrapper = await page(); await openIssue(wrapper)
    await button(wrapper, '签发令牌').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('令牌已创建但无法再次显示，如未保存请吊销后重建')
    expect(wrapper.find('[data-testid="issued-secret"]').exists()).toBe(false)
    expect(button(wrapper, '复制令牌')).toBeUndefined()
    await button(wrapper, '吊销此令牌').trigger('click')
    expect(revoke).not.toHaveBeenCalled()
    ;[...document.body.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.trim() === '确认吊销')!.click(); await flushPromises()
    expect(revoke).toHaveBeenCalledWith('pat_example')
    expect(wrapper.text()).not.toContain('测试工具')
  })

  it('lists metadata and filters revoked tokens by default', async () => {
    gateway.apiTokens = [{ ...token }, { ...token, tokenId: 'pat_old', name: '旧令牌', status: 'revoked' }, { ...token, tokenId: 'pat_expired', name: '过期令牌', status: 'expired' }]
    const list = vi.spyOn(gateway, 'listApiTokens')
    const wrapper = await page()
    expect(list).toHaveBeenCalledWith(undefined, 50, false)
    expect(wrapper.text()).toContain('hqr_pat_example')
    expect(wrapper.text()).toContain('从未使用')
    expect(wrapper.text()).toContain('已过期')
    expect(wrapper.text()).not.toContain('旧令牌')
    await wrapper.get('main input[type="checkbox"]').setValue(true); await flushPromises()
    expect(list).toHaveBeenLastCalledWith(undefined, 50, true)
    expect(wrapper.text()).toContain('旧令牌')
  })

  it('uses server default 90 days and rejects lifetime over 365 days', async () => {
    const wrapper = await page(); await openIssue(wrapper)
    expect((wrapper.get('[aria-label="有效期天数"]').element as HTMLInputElement).value).toBe('90')
    await wrapper.get('[aria-label="有效期天数"]').setValue(366)
    expect(button(wrapper, '签发令牌').attributes('disabled')).toBeDefined()
    await wrapper.get('[aria-label="有效期天数"]').setValue(30)
    const issue = vi.spyOn(gateway, 'issueApiToken')
    const now = Date.now()
    await button(wrapper, '签发令牌').trigger('click'); await flushPromises()
    const expiry = Date.parse(issue.mock.calls[0][0].expiresAt!)
    expect(expiry - now).toBeGreaterThanOrEqual(30 * 86400000)
    expect(expiry - now).toBeLessThan(30 * 86400000 + 1000)
  })

  it('reuses the same issuance intent after network failure, without duplicating the token', async () => {
    const issue = vi.spyOn(gateway, 'issueApiToken').mockRejectedValueOnce(new Error('network'))
    const wrapper = await page(); await openIssue(wrapper)
    await button(wrapper, '签发令牌').trigger('click'); await flushPromises()
    await button(wrapper, '签发令牌').trigger('click'); await flushPromises()
    expect(issue).toHaveBeenCalledTimes(2)
    expect(issue.mock.calls[0]).toEqual(issue.mock.calls[1])
    expect(gateway.apiTokens).toHaveLength(1)
  })
})
