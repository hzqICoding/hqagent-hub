import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import RemoteChatPage from './RemoteChatPage.vue'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { useRemoteAuthStore } from '@/stores/remote-auth.store'
import { MockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'

enableAutoUnmount(afterEach)
let gateway: MockRemoteGateway
beforeEach(() => {
  setActivePinia(createPinia())
  gateway = new MockRemoteGateway(); gateway.reset(); gateway.runs = []; gateway.commands = []
  gateway.conversations.forEach((c) => { c.busy = false })
  setRemoteGatewayForTesting(gateway)
})
afterEach(() => { useRemoteChatStore().reset(); setRemoteGatewayForTesting(null); vi.restoreAllMocks() })
async function page() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{path:'/remote/chat',component:RemoteChatPage},{path:'/remote/login',component:{template:'<div />'}}] })
  await router.push('/remote/chat?workerId=worker_demo')
  const wrapper = mount(RemoteChatPage, { attachTo:document.body, global:{plugins:[router]} })
  await flushPromises(); return wrapper
}
describe('mobile one-shot new topic and header', () => {
  it('defaults every ordinary send to continue, including the first message', async () => {
    const wrapper = await page(), send = vi.spyOn(gateway,'sendMessage')
    expect(wrapper.find('input[type=radio]').exists()).toBe(false)
    expect(wrapper.get('[data-testid=chat-header-actions]').findAll('button').map((b)=>b.attributes('aria-label'))).toEqual(['新话题','管理设备','退出登录'])
    expect(wrapper.get('footer').text()).not.toMatch(/电脑在线就绪|电脑离线/)
    await wrapper.get('textarea').setValue('默认继续'); await wrapper.get('textarea').trigger('keydown',{key:'Enter'}); await flushPromises()
    expect(send.mock.calls[0][1].sessionMode).toBe('continue')
  })
  it('activates new for one successful send and resets the next message to continue', async () => {
    const wrapper = await page(), send = vi.spyOn(gateway,'sendMessage'), store=useRemoteChatStore()
    await wrapper.get('[aria-label=新话题]').trigger('click')
    expect(wrapper.get('[data-testid=new-topic-tag]').text()).toContain('新话题')
    await wrapper.get('textarea').setValue('新主题'); await wrapper.get('textarea').trigger('keydown',{key:'Enter'}); await flushPromises()
    expect(send.mock.calls[0][1].sessionMode).toBe('new')
    expect(wrapper.find('[data-testid=new-topic-tag]').exists()).toBe(false)
    store.commands=[]; store.runs=[]; store.conversations.forEach((c)=>{c.busy=false})
    await wrapper.get('textarea').setValue('继续'); await wrapper.get('textarea').trigger('keydown',{key:'Enter'}); await flushPromises()
    expect(send.mock.calls[1][1].sessionMode).toBe('continue')
  })
  it('retains text and new intent on failure, retries new and allows cancelling the tag', async () => {
    const wrapper = await page(), send=vi.spyOn(gateway,'sendMessage').mockRejectedValueOnce(new Error('测试网络失败'))
    await wrapper.get('[aria-label=新话题]').trigger('click'); await wrapper.get('textarea').setValue('待重试')
    await wrapper.get('textarea').trigger('keydown',{key:'Enter'}); await flushPromises()
    expect(wrapper.find('[data-testid=new-topic-tag]').exists()).toBe(true)
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('待重试')
    await wrapper.get('textarea').trigger('keydown',{key:'Enter'}); await flushPromises()
    expect(send.mock.calls.map((args)=>args[1].sessionMode)).toEqual(['new','new'])
    const store=useRemoteChatStore(); store.commands=[]; store.runs=[]; store.conversations.forEach((c)=>{c.busy=false}); await flushPromises()
    await wrapper.get('[aria-label=新话题]').trigger('click'); await wrapper.get('[data-testid=new-topic-tag] button').trigger('click')
    expect(wrapper.find('[data-testid=new-topic-tag]').exists()).toBe(false)
  })
  it.each(['busy','offline','suspended','native'] as const)('disables + with a reason for %s', async (state) => {
    const wrapper = await page(), store=useRemoteChatStore()
    if(state==='busy') store.activeConversation!.busy=true
    if(state==='offline') store.devices[0].online=false
    if(state==='suspended') store.devices[0].remoteAccess='suspended'
    if(state==='native') store.activeConversation!.conversationKind='native'
    await flushPromises()
    const plus=wrapper.get('[aria-label=新话题]')
    expect(plus.attributes('disabled')).toBeDefined(); expect(plus.attributes('aria-description')).toBeTruthy()
    await plus.trigger('click'); expect(wrapper.find('[data-testid=new-topic-tag]').exists()).toBe(false)
    if(state==='offline') expect(wrapper.get('[data-testid=connection-status]').text()).toBe('电脑离线')
  })
  it('only logs out after explicit shared confirmation and restores focus after cancel', async () => {
    const wrapper = await page(), logout=vi.spyOn(useRemoteAuthStore(),'logout').mockResolvedValue(undefined)
    const exit=wrapper.get('[aria-label=退出登录]'); (exit.element as HTMLElement).focus()
    await exit.trigger('click'); await flushPromises(); expect(logout).not.toHaveBeenCalled()
    ;(document.querySelector('[data-confirm-cancel]') as HTMLButtonElement).click(); await flushPromises()
    expect(logout).not.toHaveBeenCalled(); expect(document.activeElement).toBe(exit.element)
    await exit.trigger('click'); await flushPromises()
    ;[...document.querySelectorAll<HTMLButtonElement>('[role=dialog] button')].find((b)=>b.textContent?.trim()==='退出')!.click(); await flushPromises()
    expect(logout).toHaveBeenCalledOnce()
  })
})
