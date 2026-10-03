import type { LocalImageVerificationState, LocalImageVerificationJobView, LocalImageVerificationRecord, StartLocalImageVerificationInput } from '@hqagent/protocol'
import { HubApiError } from '@/shared/api/local-hub-gateway'
import { targetKey } from './presentation'
// Synthetic metadata and progress only. No model invocation or CLI resources.
export class MockVerifications {
  states: LocalImageVerificationState[] = []
  jobs = new Map<string, LocalImageVerificationJobView>()
  private starts = new Map<string, { input: string; jobId: string }>()
  private ticks = new Map<string, number>()
  reset() {
    this.jobs.clear(); this.starts.clear(); this.ticks.clear()
    this.states = ['passed','stale','unverified'].map((status, index) => {
      const target = { agentId: index === 2 ? 'agent_codex_default' : 'agent_claude_default', agentType: index === 2 ? 'codex' : 'claude', ...(index === 1 ? { modelId: 'opus' } : {}), cliVersion: '1.2.3', transport: 'synthetic', targetRevision: `example-target-revision-${index}` }
      const record: LocalImageVerificationRecord = { recordId: `example-record-${index}`, target: { ...target, ...(index === 1 ? { cliVersion: '1.2.2' } : {}) }, passed: true, probes: { new:true,resume:true,mixedFive:true,cancel:true,error:true }, diagnostics:{},mimeTypes:['image/png'],observedAt:'2026-10-02T12:00:00Z' }
      return { target, inUse:true, usages:[], usagesTruncated:false, status: status as LocalImageVerificationState['status'], passed:status==='passed',invalidated:status==='stale',invalidationReasons:status==='stale'?['cli_version_changed']:[],...(index<2?{lastRecord:record}:{}) }
    })
    this.states.push({target:{agentId:'local.pi.synthetic',agentType:'pi',cliVersion:'1.0.1',transport:'pi-rpc-images-v1',targetRevision:'pi-verification-example'},inUse:true,usages:[],usagesTruncated:false,status:'unverified',passed:false,invalidated:false,invalidationReasons:[]})
    this.states.push({ ...this.states[1], target:{...this.states[1].target, modelId:'historical-model'}, lastRecord:{...this.states[1].lastRecord!,target:{...this.states[1].lastRecord!.target,modelId:'historical-model'}}, inUse:false })
  }
  start(input: StartLocalImageVerificationInput, key: string) {
    const previous=this.starts.get(key)
    if(previous) { if(previous.input!==JSON.stringify(input)) throw new HubApiError('幂等意图不同','IDEMPOTENCY_MISMATCH',409); return structuredClone(this.jobs.get(previous.jobId)!) }
    const state=this.states.find(s=>targetKey(s.target)===JSON.stringify([input.agentId,input.modelId??null]))
    if(!state) throw new HubApiError('目标不存在','NOT_FOUND',404)
    if(state.activeJobId && this.jobs.get(state.activeJobId)?.slotHeld) throw new HubApiError('已有作业','CONFLICT',409,{reason:'verification_in_progress',activeJobId:state.activeJobId})
    if(state.target.targetRevision!==input.expectedTargetRevision) throw new HubApiError('目标已变化','CONFLICT',409,{reason:'target_changed'})
    if(input.acknowledgeModelUsage!==true) throw new HubApiError('需确认','VALIDATION_FAILED',422)
    const now=new Date().toISOString(), jobId=crypto.randomUUID()
    const job: LocalImageVerificationJobView={jobId,target:{...state.target},status:'queued',acknowledgeModelUsage:true,acknowledgedAt:now,requestId:'request_example',createdAt:now,updatedAt:now,probes:{new:{state:'not_run'},resume:{state:'not_run'},mixedFive:{state:'not_run'},cancel:{state:'not_run'},error:{state:'not_run'}},diagnostics:{},appliedToCurrentTarget:false,cleanupState:'not_started',executionMayStillBeRunning:false,orphanProcessIds:[],slotHeld:true}
    this.jobs.set(jobId,job);this.starts.set(key,{input:JSON.stringify(input),jobId});state.activeJobId=jobId;state.lastJobId=jobId
    return structuredClone(job)
  }
  get(id: string) {
    const job=this.jobs.get(id);if(!job) throw new HubApiError('作业不存在','NOT_FOUND',404)
    if(job.status==='queued'||job.status==='running') {
      const tick=(this.ticks.get(id)||0)+1;this.ticks.set(id,tick);job.status='running';job.cleanupState='pending';job.executionMayStillBeRunning=true
      const keys=['new','resume','mixedFive','error','cancel'] as const
      keys.forEach((key,index)=>{job.probes[key].state=tick>index+1?'passed':tick===index+1?'running':'not_run'})
      if(tick>5){job.status='succeeded';job.slotHeld=false;job.executionMayStillBeRunning=false;job.cleanupState='confirmed';job.appliedToCurrentTarget=true
        job.result={recordId:`record_${id}`,target:job.target,passed:true,probes:{new:true,resume:true,mixedFive:true,error:true,cancel:true},diagnostics:{},mimeTypes:['image/png'],observedAt:new Date().toISOString(),jobId:id}
        const state=this.states.find(s=>targetKey(s.target)===targetKey(job.target));if(state){job.appliedToCurrentTarget=state.target.targetRevision===job.target.targetRevision;state.lastRecord=job.result;state.passed=job.appliedToCurrentTarget;state.status=job.appliedToCurrentTarget?'passed':'stale';state.invalidated=!job.appliedToCurrentTarget;state.invalidationReasons=job.appliedToCurrentTarget?[]:['configuration_changed'];delete state.activeJobId}
      }
    }
    return structuredClone(job)
  }
  cancel(id:string) {const job=this.jobs.get(id);if(!job) throw new HubApiError('作业不存在','NOT_FOUND',404);if(job.slotHeld){job.status='cancelled';job.slotHeld=false;job.executionMayStillBeRunning=false;job.cleanupState='confirmed';const state=this.states.find(s=>s.activeJobId===id);if(state)delete state.activeJobId}return structuredClone(job)}
}
