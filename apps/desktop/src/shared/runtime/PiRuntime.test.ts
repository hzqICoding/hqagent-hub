import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { LocalHubGateway } from '@/shared/api/local-hub-gateway'
import { RealLocalChatGateway } from '@/shared/api/local-chat-gateway'
import { RemoteGateway, RemoteApiError } from '@/shared/api/remote-gateway'
import { clientFetch, applyClientFeatures } from '@/shared/api/client-features'
import { MockLocalChatGateway } from '@/shared/api/mock-local-chat-gateway'
import { MockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setLocalChatGatewayForTesting } from '@/shared/api/local-chat-provider'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'
import { useChatStore } from '@/stores/chat.store'
import { useRemoteChatStore } from '@/stores/remote-chat.store'
import { useImageVerificationStore } from '@/stores/image-verification.store'
import { getRemoteErrorMessage } from '@/shared/i18n/remote-errors'
import PiAgentDetails from '@/pages/agents/PiAgentDetails.vue'
import ImageVerificationPanel from '@/pages/agents/ImageVerificationPanel.vue'
import ScenesPage from '@/pages/scenes/ScenesPage.vue'
import NativeSessionsPanel from '@/pages/native/NativeSessionsPanel.vue'
import PiGuardStatus from './PiGuardStatus.vue'
import RuntimeIcon from './RuntimeIcon.vue'
import { piAgents, piModels, piNativeExample } from './pi-examples'
import { piGuardReady, piModelLabel, piSuggestion, PI_GUARD_BLOCKED, remotePiBlock } from './pi'
import { nativeExamples } from '@/shared/api/native-examples'
import { validateImageCapabilities, remoteCapabilities } from '@/shared/attachments/validation'

enableAutoUnmount(afterEach)
let local:MockLocalChatGateway,remote:MockRemoteGateway
beforeEach(()=>{setActivePinia(createPinia());local=new MockLocalChatGateway();remote=new MockRemoteGateway();remote.reset();setLocalChatGatewayForTesting(local);setRemoteGatewayForTesting(remote)})
afterEach(()=>{useChatStore().stopPolling();useRemoteChatStore().reset();useImageVerificationStore().stop();setLocalChatGatewayForTesting(null);setRemoteGatewayForTesting(null);vi.restoreAllMocks();vi.unstubAllGlobals()})
async function choose(label:string){await flushPromises();const option=[...document.querySelectorAll<HTMLButtonElement>('[role=option]')].find(node=>node.textContent?.trim()===label);expect(option).toBeTruthy();option!.click();await flushPromises()}

describe('PI client projection',()=>{
  it('adds pi-v1 to v1, v2, cloud lists, writes, events and WS tickets without changing authentication',async()=>{
    const requests:{url:string;init:RequestInit}[]=[]
    vi.stubGlobal('fetch',vi.fn(async(url:string,init:RequestInit)=>{requests.push({url,init});return new Response(JSON.stringify({success:true,data:{ticket:'synthetic_ticket'},protocolVersion:'0.11.0'}))}))
    class Socket {static CONNECTING=0;static OPEN=1;readyState=0;close(){}}
    vi.stubGlobal('WebSocket',Socket)
    const hub=new LocalHubGateway({baseUrl:'http://127.0.0.1:9999',token:'synthetic_token'}),v2=new RealLocalChatGateway(),cloud=new RemoteGateway()
    await hub.listAgents();const subscription=hub.subscribeEvents({afterSeq:0},()=>{});await flushPromises();subscription.unsubscribe()
    await v2.listLocalAgents();await v2.listLocalEvents();await v2.startImageVerification({agentId:'pi',expectedTargetRevision:'revision',acknowledgeModelUsage:true},'synthetic_key')
    await cloud.getWorkerCatalog('worker');await cloud.listEvents();await cloud.sendMessage('conversation',{text:'text',clientMessageId:'test',sessionMode:'continue'})
    expect(requests).toHaveLength(8)
    for(const {init} of requests)expect(new Headers(init.headers).get('X-HQ-Client-Features')).toBe('pi-v1')
    expect(requests.filter(r=>r.url.includes('ws-ticket'))).toHaveLength(1)
    expect(new Headers(requests[0].init.headers).get('Authorization')).toBe('Bearer synthetic_token')
    expect(requests[2].init.credentials).toBe('include');expect(new Headers(requests[2].init.headers).has('Authorization')).toBe(false)
  })
  it('enforces one feature set for caller overrides and binary uploads',async()=>{
    const fetch=vi.fn(async()=>new Response('ok'));vi.stubGlobal('fetch',fetch)
    await clientFetch('/test',{headers:{'x-hq-client-features':'old','X-Other':'keep'}})
    const init=(fetch.mock.calls[0] as unknown as [string,RequestInit])[1]
    expect(new Headers(init.headers).get('X-HQ-Client-Features')).toBe('pi-v1');expect(new Headers(init.headers).get('X-Other')).toBe('keep')
    const setRequestHeader=vi.fn();applyClientFeatures({setRequestHeader});expect(setRequestHeader).toHaveBeenCalledWith('X-HQ-Client-Features','pi-v1')
  })
})

describe('PI presentation and guard',()=>{
  it.each(piAgents())('shows $displayName version, guard and namespace-preserving models without raw paths',async(agent)=>{
    const wrapper=mount(PiAgentDetails,{props:{agent:{...agent,diagnosticMessage:'PRIVATE_PATH_MARKER',executablePath:'PRIVATE_SOURCE_MARKER'}}});await flushPromises()
    expect(wrapper.text()).toContain(piModelLabel(piModels(agent.id).models[0].id));expect(wrapper.text()).not.toContain('PRIVATE_')
    expect(wrapper.get('[data-testid=pi-guard]').text()).toContain(agent.guard?.status==='ready'?'安全保护已就绪':PI_GUARD_BLOCKED)
  })
  it('fails closed for missing guard, unverified isolation or a non-empty reason even with ready status',()=>{
    expect(piGuardReady(undefined)).toBe(false)
    for(const guard of [undefined,{...piAgents()[0].guard!,isolation:'unknown' as const},{...piAgents()[0].guard!,reasons:['uncontrolled_extensions' as const]}])expect(mount(PiGuardStatus,{props:{guard}}).text()).toContain(PI_GUARD_BLOCKED)
    expect(mount(RuntimeIcon,{props:{agent:'pi'}}).get('[aria-label=PI]').text()).toBe('π')
  })
  it.each(['PI_TOOL_CALL_BLOCKED','PI_GUARD_UNAVAILABLE','PI_UNCONTROLLED_EXTENSIONS'])('maps %s to Chinese',code=>{expect(getRemoteErrorMessage(code)).toMatch(/PI.*[一-鿿]/)})
  it('shows PI verification target and requires the existing cost confirmation',async()=>{
    const start=vi.spyOn(local,'startImageVerification'),wrapper=mount(ImageVerificationPanel,{attachTo:document.body});await flushPromises()
    const row=wrapper.findAll('[data-testid=verification-row]').find(row=>row.text().includes('local.pi.synthetic'))!;expect(row).toBeTruthy()
    await row.findAll('button').find(button=>button.text()==='验证')!.trigger('click');await flushPromises()
    expect(document.body.textContent).toContain('可能产生费用或消耗订阅额度');expect(start).not.toHaveBeenCalled()
    ;(document.querySelector('[data-confirm-cancel]') as HTMLButtonElement).click();await flushPromises()
  })
  it('renders readable PI saved branches and folds the phase-one unsupported reader',async()=>{
    const pi=piNativeExample('ws');const readable={...nativeExamples('ws')[0],agentType:'pi' as const,title:'已保存树示例',format:{status:'readable' as const,readerId:'pi.jsonl.v3.tree',pi:{readerId:'pi.jsonl.v3.tree' as const,sessionVersion:3 as const,structure:'tree' as const,branchSelection:'last_persisted_entry' as const}}}
    vi.spyOn(local,'listNativeSessions').mockResolvedValue({items:[pi,readable],hasMore:false})
    const wrapper=mount(NativeSessionsPanel,{props:{projects:[{id:'ws',name:'项目'}]}});await flushPromises()
    expect(wrapper.text()).toContain('PI · 已保存分支');expect(wrapper.text()).toContain('暂不支持（1）');expect(wrapper.find('[data-testid=pi-icon]').exists()).toBe(true)
  })
})

describe('PI role selection',()=>{
  it('splits only the first slash and does not auto-select the suggested pro model',async()=>{
    const wrapper=mount(ScenesPage,{attachTo:document.body});await flushPromises()
    await wrapper.get('[aria-label="analyst Agent"]').trigger('click');await choose('PI (pi)')
    expect(wrapper.get('[data-testid=pi-role-hint]').text()).toContain('本机可用，请按需手动选择')
    expect(wrapper.get('[aria-label="analyst 模型"]').text()).toContain('继承本机默认模型')
    await wrapper.get('[aria-label="analyst 模型"]').trigger('click');await choose('1aicode · deepseek/deepseek-v4-pro')
    const save=vi.spyOn(local,'saveLocalScene')
    await wrapper.findAll('button').find(button=>button.text()==='保存场景配置')!.trigger('click');await flushPromises()
    expect(save.mock.calls[0][1].roles[0].modelId).toBe('1aicode/deepseek/deepseek-v4-pro')
    expect(piSuggestion('developer')).toBe('1aicode/deepseek/deepseek-v4-flash')
  })
  it('marks unavailable recommendations and never substitutes another provider',async()=>{
    vi.spyOn(local,'getAgentModels').mockResolvedValue({agentInstanceId:'local.pi.synthetic',verified:true,models:[{id:'other/deepseek/deepseek-v4-pro',name:'pro',efforts:[],isDefault:true}]})
    const wrapper=mount(ScenesPage,{attachTo:document.body});await flushPromises();await wrapper.get('[aria-label="analyst Agent"]').trigger('click');await choose('PI (pi)')
    expect(wrapper.text()).toContain('本机不可用，不会自动选择或切换渠道');expect(wrapper.get('[aria-label="analyst 模型"]').text()).toContain('继承本机默认模型')
  })
})

describe('PI send gates',()=>{
  it.each([true,false])('local scenario checks exact PI guard before dispatch ready=%s',async(ready)=>{
    const store=useChatStore();await store.init();await store.selectConversation('conv_analyze_auth')
    const scene=store.scenes.find(scene=>scene.id===store.activeConversation?.sceneId)!;scene.roles[0].agentInstanceId=ready?'local.pi.synthetic':'local.pi.synthetic.1'
    const send=vi.spyOn(local,'sendLocalMessage')
    if(ready){await store.sendMessage('PI 示例');expect(send).toHaveBeenCalledTimes(1)}
    else{expect(store.piGuardIssue).toBe(PI_GUARD_BLOCKED);await expect(store.sendMessage('PI 示例')).rejects.toMatchObject({code:'PI_GUARD_UNAVAILABLE'});expect(send).not.toHaveBeenCalled()}
  })
  it('requires revision5 and blocks missing catalog guard before sending',async()=>{
    remote.runs=[];remote.commands=[];remote.devices[0].supportedWireRevisions=[5]
    const store=useRemoteChatStore();await store.fetchDevices();await store.selectDevice('worker_demo');store.activeConversation!.conversationKind='native';store.activeConversation!.agentType='pi'
    const send=vi.spyOn(remote,'sendMessage')
    expect(store.piGuardIssue).toBe(PI_GUARD_BLOCKED);await expect(store.sendMessage('PI 示例')).rejects.toMatchObject({code:'PI_GUARD_UNAVAILABLE'});expect(send).not.toHaveBeenCalled()
    remote.catalog.runtimes=[{agentId:'local.pi.synthetic',agentType:'pi',guard:piAgents()[0].guard,nativeSessionsSupported:false}]
    expect(remotePiBlock(store.activeConversation!,remote.catalog,[4])).toContain('等待远程线路升级')
    await store.sendMessage('PI 示例');expect(send).toHaveBeenCalledTimes(1)
    store.commands=[];store.runs=[];store.conversations.forEach(conversation=>{conversation.busy=false})
    send.mockRejectedValueOnce(new RemoteApiError({code:'REMOTE_REVISION_REQUIRED',status:409,message:'revision'}))
    await expect(store.sendMessage('PI 等待协商')).rejects.toMatchObject({code:'REMOTE_REVISION_REQUIRED'})
    expect(store.sendError).toContain('等待远程线路升级')
  })
  it('does not assume PI image support from a vision model or an unbound native capability',()=>{
    const image={attachmentId:'synthetic',kind:'image' as const,mimeType:'image/png' as const,sizeBytes:1,fileName:'synthetic.png',sha256:'a'.repeat(64)}
    const capability={...local.attachmentLibrary.capabilities.roles[0].imageInput,support:'supported' as const,cliEntry:'supported' as const,runtimeImplemented:true,verified:true,mimeTypes:['image/png' as const],maxBytes:100}
    expect(()=>validateImageCapabilities([image],{conversationKind:'native',capabilityRevision:1,roles:[],native:{agentType:'pi',imageInput:capability}})).toThrow('当前 Agent 不支持图片')
    const conversation={...remote.conversations[0],conversationKind:'native' as const,agentType:'pi' as const}
    remote.catalog.nativeImageCapabilities=[{agentType:'pi',agentId:'local.pi.synthetic',modelId:'1aicode/deepseek/vision',transport:'pi-rpc-images-v1',imageInput:capability}]
    expect(remoteCapabilities(conversation,remote.catalog).native).toBeUndefined()
  })
})
