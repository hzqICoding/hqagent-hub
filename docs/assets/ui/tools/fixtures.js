async (state) => {
  const {getRemoteGateway}=await import('/src/shared/api/remote-provider.ts');
  const {getLocalChatGateway}=await import('/src/shared/api/local-chat-provider.ts');
  const {useRemoteChatStore}=await import('/src/stores/remote-chat.store.ts');
  const {useChatStore}=await import('/src/stores/chat.store.ts');
  const pinia=document.querySelector('#app').__vue_app__.config.globalProperties.$pinia;
  const r=getRemoteGateway(),l=getLocalChatGateway(),s=useRemoteChatStore(pinia),c=useChatStore(pinia);
  s.stopPolling();s.stopDevicePolling();c.stopPolling();
  const now=new Date().toISOString(),later=new Date(Date.now()+3600000).toISOString();
  if(state==='devices'){
    r.devices[0].deviceName='演示办公电脑';r.devices[0].displayName='演示办公电脑';r.devices[0].supportedWireRevisions=[1,2,3,4,5];
    r.devices[1].deviceName='演示离线电脑';r.devices[1].remoteAccess='suspended';await s.fetchDevices();
  }
  if(state==='devices-empty'){s.devices=[];s.deviceError=null}
  if(state==='devices-loading'){s.devices=[];s.isLoadingDevices=true}
  if(state==='devices-error'){s.devices=[];s.deviceError='设备列表读取失败，请检查网络后重试（审计合成状态）'}
  if(state.startsWith('login-')){
    const {useRemoteAuthStore}=await import('/src/stores/remote-auth.store.ts');const a=useRemoteAuthStore(pinia);
    if(state==='login-error')a.authError='账号或口令不正确，请核对后重试（审计合成状态）';
    if(state==='login-loading'){a.isLoading=true;a.authError=null}
  }
  if(state==='chat-base'){
    r.runs=[];r.commands=[];r.approvals=[];r.devices[0].online=true;r.devices[0].busySnapshotFresh=true;r.devices[0].supportedWireRevisions=[1,2,3,4,5];r.devices[0].remoteAccess='enabled';
    r.conversations.forEach(x=>x.busy=false);
    s.runs=[];s.commands=[];s.approvals=[];s.conversations.forEach(x=>x.busy=false);s.devices[0].online=true;s.devices[0].busySnapshotFresh=true;s.devices[0].supportedWireRevisions=[1,2,3,4,5];s.devices[0].remoteAccess='enabled';
    s.sendError=null;s.actionError=null;
    s.messages=[{messageId:'audit-user',conversationId:s.activeConversationId,role:'user',text:'请检查演示项目的界面布局，并列出需要优化的交互。',createdAt:now},{messageId:'audit-assistant',conversationId:s.activeConversationId,role:'assistant',text:'这是一段审计合成回复。已检查页面结构，下一步将核对按钮、状态提示和附件展示。',createdAt:now}];
  }
  const run={runId:'run_audit',conversationId:s.activeConversationId,status:'running',workerOnline:true,observedAt:now};
  if(state==='chat-empty')s.messages=[];
  if(state==='chat-loading'){s.messages=[];s.conversations=[];s.activeConversationId=null;s.isLoadingConversations=true;s.isSnapshotRebuilding=true}
  if(state==='chat-running')s.runs=[run];
  if(state==='chat-busy'){s.runs=[];s.activeConversation.busy=true;s.activeConversation.busyFresh=true}
  if(state==='chat-failed'){
    s.runs=[{...run,status:'failed',summary:'演示任务未完成'}];
    s.commands=[{commandId:'cmd_audit_failed',conversationId:s.activeConversationId,targetWorkerId:'worker_demo',type:'run.submit',status:'failed',deliveryState:'failed',withdrawalState:'none',workerOnline:true,observedAt:now,createdAt:now,expiresAt:later,error:{code:'SESSION_NOT_RESUMABLE',message:'角色或模型配置已变化，请点右上角 + 开启新话题',retryable:false}}];
    s.sendError='角色或模型配置已变化，请点右上角 + 开启新话题';
  }
  if(state==='chat-offline'){s.devices[0].online=false;r.devices[0].online=false;r.workerOnline=false}
  if(state==='chat-paused'){s.devices[0].remoteAccess='suspended';r.devices[0].remoteAccess='suspended'}
  if(state==='chat-approval'){
    s.runs=[{...run,status:'waiting_approval'}];
    s.approvals=[{approvalId:'approval_audit',resultRef:{runId:'run_audit'},action:'shell',targetSummary:'在演示项目目录运行合成的验证指令，不涉及真实用户文件',riskLevel:'medium',status:'pending',requestedAt:now,expiresAt:later,remoteApprovalAllowed:true,workerPolicyRevision:1},
    {approvalId:'approval_audit_high',resultRef:{runId:'run_audit'},action:'git_push',targetSummary:'向演示远端分支提交合成变更',riskLevel:'high',status:'pending',requestedAt:now,expiresAt:later,remoteApprovalAllowed:false,workerPolicyRevision:1,denialCode:'REMOTE_APPROVAL_FORBIDDEN'}];
    r.approvals=structuredClone(s.approvals.map(x=>({...x,resultRef:{...x.resultRef}})));
    window.__auditApprovalCalls=0;const decide=r.decideApproval.bind(r);r.decideApproval=async(...args)=>{window.__auditApprovalCalls++;return decide(...args)};
  }
  if(state==='chat-native'){s.activeConversation.conversationKind='native';s.activeConversation.agentType='claude';s.activeConversation.nativeSourceRevision='audit_revision';s.activeConversation.nativeActivity={activity:'unknown',observedAt:now,processMatch:'unknown',recentlyModified:false};s.activeConversation.title='审计合成原生会话';}
  if(state==='native-index'){
    const {nativeExamples}=await import('/src/shared/api/native-examples.ts');const entries=nativeExamples('workspace_demo');
    entries[1].format={status:'unsupported',cliVersion:'0.111.0',reason:'该 CLI 版本尚未验证'};entries[1].title='演示：历史模型会话';
    entries[2].format={status:'unsupported',cliVersion:'2.1.251',reason:'记录格式尚未支持'};
    r.listNativeSessions=async()=>({items:entries.map(x=>({...x,workerId:'worker_demo',workerOnline:true})),hasMore:false});
  }
  if(state==='chat-attachments'){
    const base={conversationId:s.activeConversationId,role:'assistant',createdAt:now};
    const item=(id,kind,name,availability,thumbnailStatus)=>({attachmentId:id,fileName:name,kind,mimeType:kind==='image'?'image/png':'text/plain',sizeBytes:12800,sha256:'a'.repeat(64),availability,thumbnailStatus});
    const canvas=document.createElement('canvas');canvas.width=240;canvas.height=140;const ctx=canvas.getContext('2d');ctx.fillStyle='#e0e7ff';ctx.fillRect(0,0,240,140);ctx.fillStyle='#2563eb';ctx.fillRect(24,24,75,88);ctx.fillStyle='#0f172a';ctx.font='18px sans-serif';ctx.fillText('AUDIT',118,76);const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));r.getAttachmentThumbnail=async()=>blob;
    s.messages=[{...base,messageId:'audit-images',text:'以下附件均为审计合成样例：',attachments:[item('audit-ready','image','界面示例.png','available','ready'),item('audit-thumb-pending','image','缩略图生成中.png','available','pending'),item('audit-pending','image','等待电脑上传.png','pending_upload','pending'),{...item('audit-unavailable','file','无法获取的示例文件.txt','unavailable','not_applicable'),errorCode:'ATTACHMENT_DOWNLOAD_FAILED'},item('audit-file','file','演示说明文档.txt','available','not_applicable')]}];
  }
  if(state==='draft-uploading')r.uploadAttachment=async(_conversation,_file,options)=>{options.onProgress?.(.42);return new Promise(()=>{})};
  if(state==='draft-failed')r.uploadAttachment=async()=>{throw new Error('审计合成上传失败')};
  if(state==='global-error'){
    const {remoteRequestFailure}=await import('/src/shared/api/remote-diagnostics.ts');remoteRequestFailure.value={endpoint:'/api/v2/example',method:'POST',message:'本次请求未确认，请核对电脑状态后重试（审计合成状态）',requestId:'request_audit_example'};
    s.sendError='本次请求未确认，请核对电脑状态后重试（审计合成状态）';
  }
  if(state==='tokens'){
    const token={tokenId:'audit_token_1',name:'演示自动化工具',tokenPrefix:'hqr_pat_AUDIT_EXAMPLE',scopes:['devices:read','devices:manage'],createdAt:now,expiresAt:later,status:'active'};
    r.apiTokens=[token,{...token,tokenId:'audit_token_2',name:'演示已过期工具',status:'expired'}];
    r.issueApiToken=async(input)=>({secretAvailable:true,secret:'hqr_pat_AUDIT_SYNTHETIC_NOT_A_REAL_TOKEN',token:{...token,name:input.name,scopes:input.scopes}});
  }
  if(state==='roots')l.authorizedRoots={version:1,roots:[{rootId:'audit_root',displayName:'演示授权目录',path:'E:/Audit/SyntheticProjects',version:1}]};
  if(state==='local-idle'){
    const conversation=await l.createLocalConversation({title:'审计合成本地任务',workspaceId:(await l.listLocalWorkspaces())[0].id,sceneId:'analyze'});await c.fetchConversations();await c.selectConversation(conversation.id);c.stopPolling();
  }
  if(state==='verification-running'){
    l.verification.reset();const target=l.verification.states[2].target;
    const job=l.verification.start({agentId:target.agentId,expectedTargetRevision:target.targetRevision,acknowledgeModelUsage:true},'audit_fixture_only');const active=l.verification.jobs.get(job.jobId);
    active.status='running';active.cleanupState='pending';active.executionMayStillBeRunning=true;active.probes.new.state='passed';active.probes.resume.state='running';
    l.getImageVerificationJob=async(id)=>structuredClone(l.verification.jobs.get(id));
    const {useImageVerificationStore}=await import('/src/stores/image-verification.store.ts');await useImageVerificationStore(pinia).load();
  }
}