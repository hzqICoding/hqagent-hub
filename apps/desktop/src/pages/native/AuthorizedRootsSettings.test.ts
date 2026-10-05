import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AuthorizedRootsSettings from './AuthorizedRootsSettings.vue'
import { defaultRootDisplayName } from './native-utils'
import { MockLocalChatGateway } from '@/shared/api/mock-local-chat-gateway'
import { setLocalChatGatewayForTesting } from '@/shared/api/local-chat-provider'

describe('defaultRootDisplayName', () => {
  it('derives folder name from Windows and POSIX paths', () => {
    expect(defaultRootDisplayName('E:\\OtherPro')).toBe('OtherPro')
    expect(defaultRootDisplayName('E:\\OtherPro\\')).toBe('OtherPro')
    expect(defaultRootDisplayName('E:/OtherPro')).toBe('OtherPro')
    expect(defaultRootDisplayName('E:/OtherPro/')).toBe('OtherPro')
    expect(defaultRootDisplayName('C:\\Users\\ua-hzq\\HQAgent-Hub')).toBe('HQAgent-Hub')
    expect(defaultRootDisplayName('/home/developer/workspace')).toBe('workspace')
  })

  it('derives drive display name for drive roots', () => {
    expect(defaultRootDisplayName('E:\\')).toBe('E 盘')
    expect(defaultRootDisplayName('E:/')).toBe('E 盘')
    expect(defaultRootDisplayName('E:')).toBe('E 盘')
    expect(defaultRootDisplayName('c:\\')).toBe('C 盘')
    expect(defaultRootDisplayName('d:/')).toBe('D 盘')
  })

  it('falls back safely for empty or invalid paths', () => {
    expect(defaultRootDisplayName('')).toBe('授权目录')
    expect(defaultRootDisplayName('   ')).toBe('授权目录')
  })
})

describe('AuthorizedRootsSettings Component', () => {
  let local: MockLocalChatGateway

  beforeEach(() => {
    setActivePinia(createPinia())
    local = new MockLocalChatGateway()
    local.authorizedRoots = {
      version: 1,
      roots: [
        {
          rootId: 'root-existing',
          displayName: '已有固定名',
          path: 'D:\\ExistingWork',
          version: 1,
        },
      ],
    }
    setLocalChatGatewayForTesting(local)
  })

  afterEach(() => {
    setLocalChatGatewayForTesting(null)
    vi.restoreAllMocks()
  })

  it('preserves existing item display names on load', async () => {
    const wrapper = mount(AuthorizedRootsSettings)
    await flushPromises()

    const inputs = wrapper.findAll('input[aria-label="根目录显示名称"]')
    expect(inputs.length).toBe(1)
    expect((inputs[0].element as HTMLInputElement).value).toBe('已有固定名')
    expect(wrapper.text()).toContain('D:\\ExistingWork')
  })

  it('defaults display name to folder name when picking a folder', async () => {
    const wrapper = mount(AuthorizedRootsSettings)
    await flushPromises()

    vi.spyOn(local, 'pickLocalDirectory').mockResolvedValue({
      cancelled: false,
      selectedPath: 'E:\\OtherPro',
    })

    const addBtn = wrapper.findAll('button').find((b) => b.text().trim() === '选择目录')!
    await addBtn.trigger('click')
    await flushPromises()

    const inputs = wrapper.findAll('input[aria-label="根目录显示名称"]')
    expect(inputs.length).toBe(2)
    // The second input should default to "OtherPro"
    expect((inputs[1].element as HTMLInputElement).value).toBe('OtherPro')
    expect(wrapper.text()).toContain('E:\\OtherPro')
  })

  it('defaults display name to drive name when picking a root drive', async () => {
    const wrapper = mount(AuthorizedRootsSettings)
    await flushPromises()

    vi.spyOn(local, 'pickLocalDirectory').mockResolvedValue({
      cancelled: false,
      selectedPath: 'E:\\',
    })

    const addBtn = wrapper.findAll('button').find((b) => b.text().trim() === '选择目录')!
    await addBtn.trigger('click')
    await flushPromises()

    const inputs = wrapper.findAll('input[aria-label="根目录显示名称"]')
    expect(inputs.length).toBe(2)
    // The second input should default to "E 盘"
    expect((inputs[1].element as HTMLInputElement).value).toBe('E 盘')
    expect(wrapper.text()).toContain('E:\\')
  })

  it('allows user to manually edit the name before saving', async () => {
    const wrapper = mount(AuthorizedRootsSettings)
    await flushPromises()

    vi.spyOn(local, 'pickLocalDirectory').mockResolvedValue({
      cancelled: false,
      selectedPath: 'E:\\OtherPro',
    })

    const addBtn = wrapper.findAll('button').find((b) => b.text().trim() === '选择目录')!
    await addBtn.trigger('click')
    await flushPromises()

    const inputs = wrapper.findAll('input[aria-label="根目录显示名称"]')
    await inputs[1].setValue('自定义工程目录')

    const saveSpy = vi.spyOn(local, 'setAuthorizedRoots')
    const saveBtn = wrapper.findAll('button').find((b) => b.text().trim() === '保存设置')!
    await saveBtn.trigger('click')
    await flushPromises()

    expect(saveSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        roots: expect.arrayContaining([
          expect.objectContaining({
            displayName: '自定义工程目录',
            path: 'E:\\OtherPro',
          }),
        ]),
      })
    )
  })

  it('refreshes roots when clicking the refresh icon button in the header', async () => {
    const wrapper = mount(AuthorizedRootsSettings)
    await flushPromises()

    const getSpy = vi.spyOn(local, 'getAuthorizedRoots')
    const refreshBtn = wrapper.find('button[aria-label="刷新"]')
    expect(refreshBtn.exists()).toBe(true)

    await refreshBtn.trigger('click')
    await flushPromises()

    expect(getSpy).toHaveBeenCalled()
  })
})
