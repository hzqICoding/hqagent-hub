import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { invoke } from '@tauri-apps/api/core'
import DesktopConnection from './DesktopConnection.vue'
import { useLocalAuthStore } from '@/stores/local-auth.store'

vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn() }))
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

it('waits without a code page, reconnects automatically, preserves pages and toggles autostart', async () => {
  vi.useFakeTimers()
  const pinia = createPinia(); setActivePinia(pinia)
  const auth = useLocalAuthStore()
  const check = vi.spyOn(auth, 'checkAuthStatus').mockImplementationOnce(async () => {
    auth.authError = 'Hub 尚未就绪: 就绪探测 bootstrap 超时（30 秒），将自动重试'
    return false
  }).mockResolvedValue(true)
  vi.mocked(invoke).mockImplementation(async (command) => {
    if (command === 'get_autostart_enabled') return true
    if (command === 'get_shell_status') return { childProcesses: [{ component: 'update-agent', state: 'missing' }] }
    return undefined
  })
  const wrapper = mount(DesktopConnection, { global: { plugins: [pinia] }, slots: { default: '<input data-draft value="keep draft" />' } })
  await flushPromises()
  expect(wrapper.text()).toContain('正在启动本机 Hub')
  expect(wrapper.text()).toContain('就绪探测 bootstrap 超时（30 秒）')
  expect(wrapper.text()).not.toContain('请检查桌面 Bearer')
  expect(wrapper.text()).not.toContain('连接码')
  expect(wrapper.find('[data-draft]').exists()).toBe(false)
  await vi.advanceTimersByTimeAsync(2000); await flushPromises()
  const draft = wrapper.get('[data-draft]').element
  expect(wrapper.text()).toContain('Hub：运行中')
  expect(wrapper.text()).toContain('更新组件未安装')
  check.mockResolvedValueOnce(false)
  await vi.advanceTimersByTimeAsync(2000); await flushPromises()
  expect(wrapper.get('[data-draft]').element).toBe(draft)
  await vi.advanceTimersByTimeAsync(2000); await flushPromises()
  expect(wrapper.get('[data-draft]').element).toBe(draft)
  await wrapper.get('input[type=checkbox]').setValue(false)
  expect(invoke).toHaveBeenCalledWith('set_autostart_enabled', { enabled: false })
  wrapper.unmount()
})
