import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LocalImageVerificationJobView } from '@hqagent/protocol'
import { createPinia, setActivePinia } from 'pinia'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { MockLocalChatGateway } from '@/shared/api/mock-local-chat-gateway'
import { RealLocalChatGateway } from '@/shared/api/local-chat-gateway'
import { setLocalChatGatewayForTesting } from '@/shared/api/local-chat-provider'
import { HubApiError } from '@/shared/api'
import { useImageVerificationStore } from '@/stores/image-verification.store'
import { useChatStore } from '@/stores/chat.store'
import ImageVerificationPanel from '@/pages/agents/ImageVerificationPanel.vue'
import ConversationDeletion from '@/pages/chat/components/ConversationDeletion.vue'
import SafeVerificationDiagnostics from './SafeVerificationDiagnostics.vue'
import { targetKey, cleanupLabels } from './presentation'

enableAutoUnmount(afterEach)
let gateway: MockLocalChatGateway
beforeEach(()=>{setActivePinia(createPinia());gateway=new MockLocalChatGateway();setLocalChatGatewayForTesting(gateway)})
afterEach(async()=>{
  for(const button of document.querySelectorAll<HTMLButtonElement>('[data-confirm-cancel]'))button.click()
  await flushPromises();useImageVerificationStore().stop();useChatStore().stopPolling();setLocalChatGatewayForTesting(null);vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers()
})
function confirmButton(text:string) { const button=[...document.querySelectorAll<HTMLButtonElement>('[role=dialog] button')].find(b=>b.textContent?.trim()===text);expect(button).toBeTruthy();button!.click() }
function input() { const target=gateway.verification.states[2].target;return {agentId:target.agentId,expectedTargetRevision:target.targetRevision,acknowledgeModelUsage:true as const} }
async function panel() {const wrapper=mount(ImageVerificationPanel,{attachTo:document.body});await flushPromises();return wrapper}
async function deletion() {const chat=useChatStore();await chat.init();await chat.selectConversation('conv_analyze_auth');const wrapper=mount(ConversationDeletion,{attachTo:document.body});return {chat,wrapper}}

describe('paid image verification',()=>{
  it('requires explicit usage confirmation, with exact target/revision and no invented default model',async()=>{
    const start=vi.spyOn(gateway,'startImageVerification'),wrapper=await panel()
    await wrapper.findAll('[data-testid=verification-row]')[2].findAll('button').find(b=>b.text()==='验证')!.trigger('click');await flushPromises()
    expect(document.body.textContent).toContain('这会真实调用模型多次，可能产生费用或消耗订阅额度')
    expect(start).not.toHaveBeenCalled();confirmButton('取消');await flushPromises();expect(start).not.toHaveBeenCalled()
    await wrapper.findAll('[data-testid=verification-row]')[2].findAll('button').find(b=>b.text()==='验证')!.trigger('click');await flushPromises();confirmButton('确认并开始验证');await flushPromises()
    expect(start).toHaveBeenCalledWith(input(),expect.any(String));expect(start.mock.calls[0][0]).not.toHaveProperty('modelId')
    expect(wrapper.text()).toContain('未执行')
  })
  it('reuses the same paid intent on transport failure and never retries automatically',async()=>{
    const start=vi.spyOn(gateway,'startImageVerification').mockRejectedValueOnce(new HubApiError('network','HUB_NOT_READY',503))
    const store=useImageVerificationStore();await store.load();const target=store.items[2].target
    await store.start(target);expect(store.locked(target)).toBe(true);expect(start).toHaveBeenCalledTimes(1)
    await store.start(target);expect(start).toHaveBeenCalledTimes(1)
    await store.retry(targetKey(target));expect(start).toHaveBeenCalledTimes(2);expect(start.mock.calls[0]).toEqual(start.mock.calls[1])
  })
  it('polls once per second, stops on completion and does not restart a paid job',async()=>{
    vi.useFakeTimers();const store=useImageVerificationStore(),get=vi.spyOn(gateway,'getImageVerificationJob'),start=vi.spyOn(gateway,'startImageVerification')
    store.activate();await flushPromises();await store.start(store.items[2].target)
    expect(get).not.toHaveBeenCalled();await vi.advanceTimersByTimeAsync(1000);expect(get).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(5000);expect(store.jobs[store.selectedJobId].status).toBe('succeeded')
    const count=get.mock.calls.length;await vi.advanceTimersByTimeAsync(10000);expect(get).toHaveBeenCalledTimes(count);expect(start).toHaveBeenCalledTimes(1)
  })
  it('restores activeJobId and stops polling after page unmount',async()=>{
    vi.useFakeTimers();const job=await gateway.startImageVerification(input(),'existing');const get=vi.spyOn(gateway,'getImageVerificationJob')
    const wrapper=await panel();expect(useImageVerificationStore().selectedJobId).toBe(job.jobId);expect(get).toHaveBeenCalledWith(job.jobId)
    wrapper.unmount();const count=get.mock.calls.length;await vi.advanceTimersByTimeAsync(5000);expect(get).toHaveBeenCalledTimes(count)
  })
  it('follows verification_in_progress conflict to the existing job',async()=>{
    const store=useImageVerificationStore();await store.load()
    const existing=await gateway.startImageVerification(input(),'another-confirmation')
    const start=vi.spyOn(gateway,'startImageVerification');await store.start(store.items[2].target)
    expect(start).toHaveBeenCalledTimes(1);expect(store.selectedJobId).toBe(existing.jobId);expect(store.jobs[existing.jobId]).toBeTruthy()
  })
  it('requires a new confirmation after target_changed without silently changing model or revision',async()=>{
    const wrapper=await panel();const start=vi.spyOn(gateway,'startImageVerification')
    await wrapper.findAll('[data-testid=verification-row]')[2].findAll('button').find(b=>b.text()==='验证')!.trigger('click');await flushPromises()
    gateway.verification.states[2].target.targetRevision='changed-revision'
    confirmButton('确认并开始验证');await flushPromises()
    expect(start.mock.calls[0][0].expectedTargetRevision).not.toBe('changed-revision');expect(start).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('目标配置已变化，请刷新后重新确认')
  })
  it('confirms cancellation and keeps interrupted/unconfirmed locked until cleanup is confirmed',async()=>{
    vi.useFakeTimers();const existing=await gateway.startImageVerification(input(),'interrupted')
    Object.assign(gateway.verification.jobs.get(existing.jobId)!,{status:'interrupted',cleanupState:'unconfirmed',executionMayStillBeRunning:true,slotHeld:true})
    const get=vi.spyOn(gateway,'getImageVerificationJob'),cancel=vi.spyOn(gateway,'cancelImageVerification')
    const wrapper=await panel(),store=useImageVerificationStore();expect(store.locked(store.items[2].target)).toBe(true)
    const count=get.mock.calls.length;await vi.advanceTimersByTimeAsync(5000);expect(get).toHaveBeenCalledTimes(count)
    await wrapper.findAll('button').find(b=>b.text()==='再次请求取消')!.trigger('click');await flushPromises();expect(document.body.textContent).toContain('已产生的用量无法撤回');expect(cancel).not.toHaveBeenCalled()
    confirmButton('取消');await flushPromises();expect(cancel).not.toHaveBeenCalled()
    await wrapper.findAll('button').find(b=>b.text()==='再次请求取消')!.trigger('click');await flushPromises();confirmButton('请求取消');await flushPromises()
    expect(cancel).toHaveBeenCalledWith(existing.jobId,expect.any(String));expect(store.jobs[existing.jobId].cleanupState).toBe('confirmed');expect(store.locked(store.items[2].target)).toBe(false)
  })
  it('does not let a late running poll overwrite a confirmed cancellation',async()=>{
    const store=useImageVerificationStore();await store.load();await store.start(store.items[2].target)
    const id=store.selectedJobId,old={...store.jobs[id],status:'running' as const}
    let resolve!: (job:LocalImageVerificationJobView)=>void
    vi.spyOn(gateway,'getImageVerificationJob').mockImplementationOnce(()=>new Promise(done=>{resolve=done}))
    const reading=store.refreshJob(id);await store.cancel(id);resolve(old);await reading
    expect(store.jobs[id].status).toBe('cancelled');expect(store.jobs[id].slotHeld).toBe(false)
  })
  it('reuses a cancellation key after a network failure and shows cancel_requested separately',async()=>{
    const store=useImageVerificationStore();await store.load();await store.start(store.items[2].target)
    const id=store.selectedJobId
    const cancel=vi.spyOn(gateway,'cancelImageVerification').mockRejectedValueOnce(new HubApiError('network','HUB_NOT_READY',503)).mockResolvedValueOnce({...store.jobs[id],status:'cancel_requested',cleanupState:'pending'})
    await store.cancel(id);await store.cancel(id)
    expect(cancel.mock.calls[0]).toEqual(cancel.mock.calls[1]);expect(store.jobs[id].status).toBe('cancel_requested');expect(store.locked(store.items[2].target)).toBe(true)
  })
  it('displays current and historical validity separately and supports inactive models',async()=>{
    const wrapper=await panel();expect(wrapper.text()).toContain('已验证');expect(wrapper.text()).toContain('CLI 版本已变化');expect(wrapper.text()).toContain('历史通过但当前无效')
    expect(wrapper.text()).not.toContain('historical-model');await wrapper.get('input[type=checkbox]').setValue(true);await flushPromises();expect(wrapper.text()).toContain('historical-model')
  })
  it('does not render undeclared diagnostic fields or model output',()=>{
    const diagnostics=JSON.parse('{"newStart":{"result":"ok","elapsedMs":12,"raw":"UNSAFE_MARKER"},"modelOutput":{"raw":"UNSAFE_MARKER"}}')
    const wrapper=mount(SafeVerificationDiagnostics,{props:{diagnostics}});expect(wrapper.text()).toContain('耗时（毫秒）：12');expect(wrapper.text()).not.toContain('UNSAFE_MARKER')
  })
})

describe('local conversation deletion',()=>{
  it('does not delete until confirmed and reads current CAS version before confirmation',async()=>{
    const {chat,wrapper}=await deletion();const id=chat.activeConversationId!
    await gateway.updateLocalConversation(id,{title:'新版标题',expectedVersion:1},'edit')
    const remove=vi.spyOn(gateway,'deleteLocalConversation');const first=wrapper.vm.request(id);await flushPromises()
    expect(document.body.textContent).toContain('原生会话的 CLI 原始记录不会被删除');expect(remove).not.toHaveBeenCalled();confirmButton('取消');await first;expect(remove).not.toHaveBeenCalled()
    const second=wrapper.vm.request(id);await flushPromises();confirmButton('删除对话');await second
    expect(remove).toHaveBeenCalledWith(id,2,expect.any(String));expect(chat.conversations.some(c=>c.id===id)).toBe(false);expect(chat.activeConversationId).not.toBe(id)
  })
  it.each(['not_required','pending','confirmed','unconfirmed'] as const)('shows remoteCleanup=%s accurately and removes drafts only for the deleted conversation',async(state)=>{
    gateway.deletionCleanup=state;const {chat,wrapper}=await deletion();const id=chat.activeConversationId!
    chat.setConversationDraft(id,'删除的草稿');chat.setConversationDraft('other','保留草稿')
    const request=wrapper.vm.request(id);await flushPromises();confirmButton('删除对话');await request;await flushPromises()
    expect(document.body.textContent).toContain(cleanupLabels[state]);expect(chat.getConversationDraft(id)).toBe('');expect(chat.getConversationDraft('other')).toBe('保留草稿')
  })
  it('shows structured blockers with a run jump and never offers forced deletion',async()=>{
    const {chat,wrapper}=await deletion();await chat.selectConversation('conv_develop_ui')
    const request=wrapper.vm.request('conv_develop_ui');await flushPromises();confirmButton('删除对话');await request;await flushPromises()
    expect(document.body.textContent).toContain('对话仍有未结束的运行');expect(document.body.textContent).not.toContain('强制删除')
    const jump=[...document.querySelectorAll<HTMLButtonElement>('button')].find(b=>b.textContent?.includes('查看运行'))!;expect(jump).toBeTruthy();jump.click();await flushPromises();expect(wrapper.emitted('open-run')).toHaveLength(1);expect(chat.activeRun).toBeTruthy()
  })
  it('reports a version conflict without retrying deletion automatically',async()=>{
    const {chat,wrapper}=await deletion(),id=chat.activeConversationId!
    const remove=vi.spyOn(gateway,'deleteLocalConversation').mockRejectedValue(new HubApiError('changed','CONFLICT',409,{reason:'version_mismatch',currentVersion:9}))
    const request=wrapper.vm.request(id);await flushPromises();confirmButton('删除对话');await request;await flushPromises()
    expect(document.body.textContent).toContain('对话版本已变化');expect(document.body.textContent).toContain('当前版本：9');expect(remove).toHaveBeenCalledTimes(1);expect(chat.conversations.some(c=>c.id===id)).toBe(true)
  })
  it('reuses a deletion key after an uncertain response',async()=>{
    const {chat,wrapper}=await deletion();const remove=vi.spyOn(gateway,'deleteLocalConversation').mockRejectedValueOnce(new HubApiError('network','HUB_NOT_READY',503))
    const request=wrapper.vm.request(chat.activeConversationId!);await flushPromises();confirmButton('删除对话');await request;await flushPromises()
    confirmButton('重试同次删除请求');await flushPromises();expect(remove).toHaveBeenCalledTimes(2);expect(remove.mock.calls[0]).toEqual(remove.mock.calls[1])
  })
})

it('uses local v2 Cookie endpoints, explicit idempotency and exact payloads',async()=>{
  const gateway=new RealLocalChatGateway();const fetch=vi.fn(async()=>new Response(JSON.stringify({success:true,data:{},protocolVersion:'0.10.1'}),{status:200}));vi.stubGlobal('fetch',fetch)
  await gateway.listImageVerifications({includeInactiveModels:true});await gateway.startImageVerification({agentId:'agent',expectedTargetRevision:'revision',acknowledgeModelUsage:true},'start-key');await gateway.getImageVerificationJob('job');await gateway.cancelImageVerification('job','cancel-key');await gateway.deleteLocalConversation('conversation',7,'delete-key')
  expect(fetch.mock.calls.map(call=>String((call as unknown[])[0]))).toEqual(['/api/v2/agents/image-verifications?limit=50&includeInactiveModels=true','/api/v2/agents/image-verification-jobs','/api/v2/agents/image-verification-jobs/job','/api/v2/agents/image-verification-jobs/job/cancellations','/api/v2/conversations/conversation?expectedVersion=7'])
  const calls=fetch.mock.calls as unknown as [string,RequestInit][]
  expect(JSON.parse(calls[1][1].body as string)).toEqual({agentId:'agent',expectedTargetRevision:'revision',acknowledgeModelUsage:true});expect(calls[3][1].body).toBe('{}');expect(calls[4][1].body).toBeUndefined();expect(calls[4][1].headers).toMatchObject({'Idempotency-Key':'delete-key'});expect(calls.every(call=>call[1].credentials==='include'&&call[1].cache==='no-store')).toBe(true)
})
