import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import type { NativeSessionIndex } from '@hqagent/protocol'
import NativeSessionsPanel from './NativeSessionsPanel.vue'
import { nativeExamples } from '@/shared/api/native-examples'
import { MockLocalChatGateway } from '@/shared/api/mock-local-chat-gateway'
import { MockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setLocalChatGatewayForTesting } from '@/shared/api/local-chat-provider'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'

enableAutoUnmount(afterEach)
let local: MockLocalChatGateway
let remote: MockRemoteGateway
let sessions: NativeSessionIndex[]
let hasMore = false
function session(id: string, status: NativeSessionIndex['format']['status'], workspaceId = 'ws_a', updatedAt = '2026-10-02T10:00:00Z'): NativeSessionIndex {
  return { ...nativeExamples(workspaceId)[0], nativeSessionId:id, title:id, agentType:'codex', updatedAt,
    format:{status,cliVersion:'0.111.0',...(status==='unsupported'?{reason:'该 CLI 版本尚未验证'}:{readerId:'synthetic'})} }
}
beforeEach(() => {
  setActivePinia(createPinia()); local=new MockLocalChatGateway(); remote=new MockRemoteGateway(); remote.reset()
  setLocalChatGatewayForTesting(local); setRemoteGatewayForTesting(remote); hasMore=false
  sessions=[session('较旧可用','readable'),session('不支持 A','unsupported'),session('较新可用','readable','ws_a','2026-10-03T10:00:00Z'),session('不支持 B','unsupported','ws_b')]
  vi.spyOn(local,'listNativeSessions').mockImplementation(async()=>({items:sessions,hasMore,nextCursor:hasMore?'next':undefined}))
  vi.spyOn(remote,'listNativeSessions').mockImplementation(async()=>({items:sessions.map((item)=>({...item,workerId:'worker_demo',workerOnline:true})),hasMore,nextCursor:hasMore?'next':undefined}))
})
afterEach(() => { setLocalChatGatewayForTesting(null); setRemoteGatewayForTesting(null); vi.restoreAllMocks() })
async function panel(isRemote: boolean) {
  const wrapper=mount(NativeSessionsPanel,{attachTo:document.body,props:{remote:isRemote,workerId:isRemote?'worker_demo':undefined,revisions:[4],projects:[{id:'ws_a',name:'项目 A'},{id:'ws_b',name:'项目 B'}]},global:{stubs:{Teleport:true}}})
  await flushPromises();return wrapper
}
describe.each([false,true])('native format availability remote=%s', (isRemote) => {
  it('counts within each workspace, sorts readable newest first and folds unsupported at the end', async () => {
    const wrapper=await panel(isRemote), a=wrapper.get('[data-workspace=ws_a]'), b=wrapper.get('[data-workspace=ws_b]')
    expect(a.get('h3').text()).toBe('项目 A · 可用 2')
    expect(a.findAll('[data-testid=native-readable]').map((node)=>node.text().split('Codex')[0])).toEqual(['较新可用','较旧可用'])
    expect(a.get('[data-testid=native-unavailable-toggle]').text()).toBe('暂不支持（1）')
    expect(a.get('[data-testid=native-unavailable-toggle]').attributes('aria-expanded')).toBe('false')
    expect(a.find('[data-testid=native-unavailable]').exists()).toBe(false)
    expect(b.get('[data-testid=native-empty-readable]').text()).toBe('暂无可读取的原生会话')
    expect(b.get('[data-testid=native-unavailable-toggle]').text()).toBe('暂不支持（1）')
    await a.get('[data-testid=native-unavailable-toggle]').trigger('click')
    const unavailable=a.get('[data-testid=native-unavailable]')
    expect(unavailable.text()).toContain('Codex · CLI 0.111.0');expect(unavailable.text()).toContain('该 CLI 版本尚未验证')
    expect(a.findAll('button').at(-1)?.element).toBe(unavailable.element)
    expect(b.find('[data-testid=native-unavailable]').exists()).toBe(false)
  })
  it('keeps only five readable rows visible in a 56-session workspace', async () => {
    sessions=Array.from({length:56},(_,index)=>session(`会话 ${index}`,index<5?'readable':'unsupported'))
    const wrapper=await panel(isRemote)
    expect(wrapper.findAll('[data-testid=native-readable]')).toHaveLength(5)
    expect(wrapper.get('[data-testid=native-unavailable-toggle]').text()).toBe('暂不支持（51）')
    expect(wrapper.findAll('[data-testid=native-unavailable]')).toHaveLength(0)
  })
  it('shows an explanation without read, metadata lookup, import, or conversation navigation', async () => {
    const gateway=isRemote?remote:local
    const read=vi.spyOn(gateway,'readNativeMessages'), lookup=vi.spyOn(gateway,'getNativeSession'), resume=vi.spyOn(gateway,'importNativeSession')
    const wrapper=await panel(isRemote)
    await wrapper.get('[data-workspace=ws_a] [data-testid=native-unavailable-toggle]').trigger('click')
    await wrapper.get('[data-testid=native-unavailable]').trigger('click');await flushPromises()
    const explanation=wrapper.get('[data-testid=native-unavailable-explanation]')
    expect(explanation.text()).toContain('该会话由 Codex 0.111.0 生成，当前版本的记录格式尚未支持，无法读取或续接')
    expect(explanation.text()).toContain('原因：该 CLI 版本尚未验证')
    expect(wrapper.get('[role=dialog]').text()).not.toMatch(/接着对话|确认导入|重新读取/)
    expect(read).not.toHaveBeenCalled();expect(lookup).not.toHaveBeenCalled();expect(resume).not.toHaveBeenCalled();expect(wrapper.emitted('opened')).toBeUndefined()
  })
  it('keeps an all-unsupported workspace compact and supplies unknown-version/reason fallback', async () => {
    sessions=[session('不支持 A','unsupported')]; sessions[0].format={status:'unsupported'}
    const wrapper=await panel(isRemote)
    expect(wrapper.findAll('[data-testid=native-empty-readable]')).toHaveLength(1)
    expect(wrapper.findAll('[data-testid=native-readable]')).toHaveLength(0)
    expect(wrapper.text()).not.toContain('不支持 A')
    await wrapper.get('[data-testid=native-unavailable-toggle]').trigger('click')
    expect(wrapper.get('[data-testid=native-unavailable]').text()).toContain('CLI 版本未知')
    await wrapper.get('[data-testid=native-unavailable]').trigger('click')
    expect(wrapper.get('[data-testid=native-unavailable-explanation]').text()).toContain('当前记录格式尚未支持')
  })
  it('uses memory-only folding even if browser preference storage throws', async () => {
    const get=vi.spyOn(Storage.prototype,'getItem').mockImplementation(()=>{throw new DOMException('blocked','SecurityError')})
    const set=vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new DOMException('full','QuotaExceededError')})
    const wrapper=await panel(isRemote), toggle=wrapper.get('[data-workspace=ws_a] [data-testid=native-unavailable-toggle]')
    await toggle.trigger('click');expect(toggle.attributes('aria-expanded')).toBe('true')
    await wrapper.findAll('button').find((b)=>b.text()==='刷新')!.trigger('click');await flushPromises()
    expect(toggle.attributes('aria-expanded')).toBe('true')
    await toggle.trigger('click');expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(get).not.toHaveBeenCalled();expect(set).not.toHaveBeenCalled()
    wrapper.unmount();const fresh=await panel(isRemote)
    expect(fresh.get('[data-testid=native-unavailable-toggle]').attributes('aria-expanded')).toBe('false')
  })
  it('treats any future or malformed non-readable status as unavailable', async () => {
    sessions=[JSON.parse(JSON.stringify({...session('未知格式','unsupported'),format:{status:'future_unreadable',reason:'记录无法识别'}}))]
    const wrapper=await panel(isRemote)
    expect(wrapper.find('[data-testid=native-readable]').exists()).toBe(false)
    expect(wrapper.get('[data-testid=native-unavailable-toggle]').text()).toBe('暂不支持（1）')
  })
  it('deduplicates overlapping index pages before computing counts and ordering', async () => {
    hasMore=true;const wrapper=await panel(isRemote)
    expect(wrapper.text()).toContain('以下数量仅统计已加载的会话')
    sessions=[session('较旧可用','readable'),session('第三个可用','readable','ws_a','2026-10-04T10:00:00Z')];hasMore=false
    await wrapper.findAll('button').find((b)=>b.text()==='更多原生会话')!.trigger('click');await flushPromises()
    expect(wrapper.get('[data-workspace=ws_a] h3').text()).toContain('可用 3')
    expect(wrapper.findAll('[data-testid=native-readable]')[0].text()).toContain('第三个可用')
    expect(wrapper.get('[data-workspace=ws_a] [data-testid=native-unavailable-toggle]').text()).toBe('暂不支持（1）')
  })
  it('blocks import when the authoritative format changes to unsupported during confirmation', async () => {
    const gateway=isRemote?remote:local
    const resume=vi.spyOn(gateway,'importNativeSession')
    const changed=session('较新可用','unsupported')
    if(isRemote) vi.spyOn(remote,'getNativeSession').mockResolvedValue({...changed,workerId:'worker_demo',workerOnline:true})
    else vi.spyOn(local,'getNativeSession').mockResolvedValue(changed)
    const wrapper=await panel(isRemote)
    await wrapper.findAll('[data-testid=native-readable]')[0].trigger('click');await flushPromises()
    await wrapper.findAll('button').find((b)=>b.text()==='接着对话')!.trigger('click');await flushPromises()
    expect(wrapper.find('[data-testid=native-unavailable-explanation]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('确认终端已退出');expect(resume).not.toHaveBeenCalled()
  })
})
