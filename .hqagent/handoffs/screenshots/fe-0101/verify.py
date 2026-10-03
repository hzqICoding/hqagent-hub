import os,json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path.cwd();os.environ['TEMP']=os.environ['TMP']=str(root/'.tmp')
out=root/'.hqagent/handoffs/screenshots/fe-0101'
results=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1280,'height':800});page.set_default_timeout(15000)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 for mode in ['light','dark']:
  page.emulate_media(color_scheme=mode)
  page.goto('http://127.0.0.1:5198/agents');page.get_by_test_id('image-verifications').wait_for()
  page.evaluate("""async()=>{
   const {getLocalChatGateway}=await import('/src/shared/api/local-chat-provider.ts');const g=getLocalChatGateway();g.verification.reset();
   const target=g.verification.states[2].target;
   const job=g.verification.start({agentId:target.agentId,expectedTargetRevision:target.targetRevision,acknowledgeModelUsage:true},'screenshot-synthetic');
   const running=g.verification.jobs.get(job.jobId);running.status='running';running.executionMayStillBeRunning=true;running.cleanupState='pending';running.probes.new.state='passed';running.probes.resume.state='passed';running.probes.mixedFive.state='running';
   g.getImageVerificationJob=async(id)=>structuredClone(g.verification.jobs.get(id));
   window.__paidStarts=0;g.startImageVerification=async()=>{window.__paidStarts++;throw new Error('Screenshot must never confirm model usage')};
   const {useImageVerificationStore}=await import('/src/stores/image-verification.store.ts');await useImageVerificationStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia).load();
  }""")
  def theme():
   page.evaluate('(mode)=>document.documentElement.dataset.themeMode=mode',mode)
   page.add_style_tag(content='*,*::before,*::after{transition-duration:0s!important;animation-duration:0s!important}')
  def shot(name):
   assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
   page.screenshot(path=str(out/f'{mode}-{name}-1280x800.png'))
  theme();page.get_by_test_id('verification-progress').wait_for()
  assert '已验证' in page.get_by_test_id('image-verifications').inner_text()
  assert '历史通过但当前无效' in page.get_by_test_id('image-verifications').inner_text()
  assert '运行中' in page.get_by_test_id('verification-progress').inner_text()
  shot('image-capabilities')
  page.get_by_test_id('verification-row').first.get_by_role('button',name='验证',exact=True).click()
  page.get_by_role('dialog',name='验证图片能力？').wait_for();shot('usage-confirmation')
  assert '可能产生费用或消耗订阅额度' in page.get_by_role('dialog').inner_text()
  page.get_by_role('button',name='取消',exact=True).click();assert page.evaluate('window.__paidStarts')==0
  page.goto('http://127.0.0.1:5198/chat');page.locator('textarea').wait_for();theme()
  page.get_by_role('button',name='更多任务操作',exact=True).click();page.get_by_role('menuitem',name='删除对话',exact=True).click()
  page.get_by_role('dialog',name='删除对话？').wait_for();shot('deletion-confirmation')
  assert 'CLI 原始记录不会被删除' in page.get_by_role('dialog').inner_text()
  page.get_by_role('button',name='删除对话',exact=True).click();page.get_by_role('dialog',name='删除对话未完成').wait_for();shot('deletion-conflict')
  assert '对话仍有未结束的运行' in page.get_by_role('dialog').inner_text()
  assert '查看运行' in page.get_by_role('dialog').inner_text()
  assert '强制删除' not in page.get_by_role('dialog').inner_text()
  results.append({'theme':mode,'capabilityStates':['verified','invalidated','running'],'paidStarts':0,'deletion':'synthetic busy conversation rejected','blockingRunLink':True,'horizontalOverflow':False})
 assert not errors,errors
 result={'checks':results,'screenshots':len(list(out.glob('*.png'))),'browserErrors':len(errors),'source':'Chromium + local protocol mocks; no real model calls or user deletion'}
 (out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False));browser.close()
