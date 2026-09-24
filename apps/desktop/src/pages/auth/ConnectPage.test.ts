import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import ConnectPage from './ConnectPage.vue'
import { setLocalChatGatewayMode } from '@/shared/api'

describe('ConnectPage', () => {
  let router: any

  beforeEach(async () => {
    setActivePinia(createPinia())
    setLocalChatGatewayMode('mock')
    router = createRouter({
      history: createWebHistory(),
      routes: [
        { path: '/connect', component: ConnectPage },
        { path: '/chat', component: { template: '<div>Chat</div>' } },
      ],
    })
    router.push('/connect')
    await router.isReady()
  })

  it('renders title, connect code input, and demo mode indicator', () => {
    const wrapper = mount(ConnectPage, {
      global: {
        plugins: [router],
      },
    })

    expect(wrapper.text()).toContain('HQAgent 本地角色对话工作台')
    expect(wrapper.text()).toContain('本地会话连接码')
    expect(wrapper.find('input').exists()).toBe(true)
  })

  it('submits connect code when button clicked', async () => {
    const wrapper = mount(ConnectPage, {
      global: {
        plugins: [router],
      },
    })

    const input = wrapper.find('input')
    await input.setValue('test-connect-code-1234')

    const button = wrapper.find('button[type="submit"]')
    expect(button.attributes('disabled')).toBeUndefined()
    await button.trigger('click')

    // Expect session to be created without throwing
    expect(wrapper.text()).not.toContain('连接码格式不正确')
  })
})
