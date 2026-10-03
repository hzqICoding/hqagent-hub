import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import HqDialog from './HqDialog.vue'
import HqSelect from './HqSelect.vue'
import HqDropdown from './HqDropdown.vue'
import { confirm, useConfirm } from './confirm'

afterEach(async () => {
  for (const cancel of document.querySelectorAll<HTMLButtonElement>('[data-confirm-cancel]')) cancel.click()
  await flushPromises()
  vi.restoreAllMocks(); document.querySelector('#test-trigger')?.remove()
})
enableAutoUnmount(afterEach)
function trigger() { const element = document.createElement('button'); element.id = 'test-trigger'; element.textContent = 'Open'; document.body.append(element); element.focus(); return element }
function clickText(text: string) { const button = [...document.querySelectorAll('button')].find((node) => node.textContent?.trim() === text); expect(button).toBeTruthy(); button!.click() }
beforeEach(() => { document.body.style.overflow = '' })

describe('shared confirmation promises', () => {
  it('resolves true only after explicit confirmation, locks scroll and returns focus', async () => {
    const opener = trigger()
    const result = confirm({ title: '确定退出登录？', confirmText: '退出' })
    await flushPromises()
    expect(document.querySelector('[role=dialog]')?.getAttribute('aria-labelledby')).toBeTruthy()
    expect(document.body.style.overflow).toBe('hidden')
    expect(document.activeElement?.textContent).toBe('取消')
    clickText('退出'); expect(await result).toBe(true); await flushPromises()
    expect(document.body.style.overflow).toBe(''); expect(document.activeElement).toBe(opener)
    expect(document.querySelector('[role=dialog]')).toBeNull()
  })
  it('resolves false on cancel or ordinary backdrop dismissal', async () => {
    trigger()
    const first = confirm({ title: '确认测试' }); await flushPromises(); clickText('取消'); expect(await first).toBe(false)
    const second = confirm({ title: '确认测试' }); await flushPromises()
    ;(document.querySelector('[data-testid=dialog-backdrop]') as HTMLElement).click()
    expect(await second).toBe(false)
  })
  it('keeps dangerous confirmation open on backdrop click and cancels with Esc', async () => {
    trigger()
    const result = confirm({ title: '删除设备？', description: '本机任务可能继续', danger: true })
    await flushPromises()
    ;(document.querySelector('[data-testid=dialog-backdrop]') as HTMLElement).click(); await flushPromises()
    expect(document.querySelector('[role=dialog]')).not.toBeNull()
    expect(document.querySelector('[role=dialog]')?.getAttribute('aria-describedby')).toBeTruthy()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(await result).toBe(false)
  })
  it('traps Tab and keeps nested dialogs scroll-locked when the top layer closes', async () => {
    const opener = trigger()
    const dialog = mount(HqDialog, { attachTo: document.body, props: { open: true, title: '外层' }, slots: { default: '<button id="inside">Inside</button>' } })
    await flushPromises()
    const result = confirm({ title: '内层' }); await flushPromises()
    const close = [...document.querySelectorAll<HTMLButtonElement>('[aria-label=关闭弹窗]')].at(-1)!
    close.focus(); document.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',shiftKey:true,bubbles:true,cancelable:true}))
    expect(document.activeElement?.textContent).toBe('确认')
    document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true})); expect(await result).toBe(false); await flushPromises()
    expect(document.body.style.overflow).toBe('hidden')
    await dialog.setProps({ open: false }); await flushPromises()
    expect(document.body.style.overflow).toBe(''); expect(document.activeElement).toBe(opener)
  })
  it('queues requests, resolving each Promise once in order', async () => {
    trigger()
    const first = confirm({ title: '第一项', confirmText: '继续第一项' })
    const second = confirm({ title: '第二项' })
    await flushPromises()
    expect(document.querySelectorAll('[role=dialog]')).toHaveLength(1)
    expect(document.body.textContent).not.toContain('第二项')
    clickText('继续第一项'); expect(await first).toBe(true); await flushPromises()
    expect(document.body.textContent).toContain('第二项')
    clickText('取消'); expect(await second).toBe(false); await flushPromises()
    expect(document.querySelector('[role=dialog]')).toBeNull()
    expect(document.body.style.overflow).toBe('')
  })
  it('cancels page-scoped pending confirmations on unmount', async () => {
    let request!: () => Promise<boolean>
    const wrapper = mount(defineComponent({ setup() { const ask = useConfirm(); request = () => ask({ title: '离页测试' }); return () => null } }))
    const result = request(); await flushPromises(); wrapper.unmount()
    expect(await result).toBe(false); await flushPromises()
    expect(document.querySelector('[role=dialog]')).toBeNull(); expect(document.body.style.overflow).toBe('')
  })
})

describe('shared adaptive selector/menu', () => {
  const options = [{ value: 'a', label: 'Alpha' }, { value: 'b', label: 'Blocked', disabled: true }, { value: 'c', label: 'Charlie' }]
  it('supports arrows, disabled options, Enter, Esc and focus return on desktop', async () => {
    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(1280)
    const wrapper = mount(HqSelect,{ attachTo:document.body, props:{modelValue:'a',options,label:'项目'} })
    const button = wrapper.get('button'); (button.element as HTMLElement).focus()
    await button.trigger('keydown',{key:'ArrowDown'}); await flushPromises()
    const listbox = document.querySelector('[role=listbox]') as HTMLElement
    expect(document.activeElement).toBe(listbox)
    listbox.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true,cancelable:true}))
    await flushPromises()
    expect(listbox.getAttribute('aria-activedescendant')).toContain('option-2')
    listbox.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true})); await flushPromises()
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['c']); expect(document.activeElement).toBe(button.element)
    await button.trigger('click'); await flushPromises(); document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true})); await flushPromises()
    expect(document.querySelector('[role=listbox]')).toBeNull(); expect(document.activeElement).toBe(button.element)
  })
  it('uses a themed bottom sheet on mobile and dismisses via its backdrop', async () => {
    vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(375)
    const wrapper = mount(HqSelect,{attachTo:document.body,props:{options,label:'项目'}})
    await wrapper.get('button').trigger('click'); await flushPromises()
    const panel = document.querySelector('[data-testid=option-panel]')!
    expect(panel.getAttribute('role')).toBe('dialog'); expect(panel.classList.contains('bottom-0')).toBe(true)
    expect(document.body.style.overflow).toBe('hidden')
    ;(document.querySelector('[data-testid=option-backdrop]') as HTMLElement).click(); await flushPromises()
    expect(document.body.style.overflow).toBe('')
  })
  it('provides keyboard menu actions without native menus', async () => {
    const action = vi.fn()
    const wrapper = mount(HqDropdown,{attachTo:document.body,props:{items:[{label:'操作1',action},{label:'禁用',disabled:true},{label:'操作2',action}]},slots:{default:'<button>更多</button>'}})
    await wrapper.get('button').trigger('keydown',{key:'ArrowDown'}); await flushPromises()
    expect(document.activeElement?.textContent).toBe('操作1')
    document.activeElement?.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true,cancelable:true}))
    expect(document.activeElement?.textContent).toBe('操作2')
    ;(document.activeElement as HTMLElement).click(); await flushPromises(); expect(action).toHaveBeenCalledTimes(1)
  })
})
