import argparse,json,os,re,time
from pathlib import Path
from playwright.sync_api import sync_playwright
from audit_paths import ROOT, OUT, TOOLS, BASELINE
os.environ['TEMP']=os.environ['TMP']=str(ROOT/'.tmp')
FIXTURE=(TOOLS/'fixtures.js').read_text(encoding='utf-8');MEASURE=(TOOLS/'measure.js').read_text(encoding='utf-8')
parser=argparse.ArgumentParser();parser.add_argument('--profile',default='all');args=parser.parse_args()
manifest_path=OUT/'manifest.json'
manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'baseline':BASELINE,'captures':[],'browserErrors':[],'interactionNotes':[]}
manifest['baseline']=BASELINE
profiles=[(f'mobile-{w}-{mode}',w,h,mode) for w,h in [(375,812),(390,844)] for mode in ['light','dark']]+[(f'desktop-{mode}',1280,800,mode) for mode in ['light','dark']]
def save_manifest():manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True)
 try:
  for profile,width,height,mode in profiles:
   if args.profile!='all' and profile!=args.profile:continue
   manifest['browserErrors']=[item for item in manifest['browserErrors'] if item['profile']!=profile]
   manifest['interactionNotes']=[item for item in manifest['interactionNotes'] if item['profile']!=profile]
   context=browser.new_context(viewport={'width':width,'height':height},color_scheme=mode,device_scale_factor=1)
   page=context.new_page();page.set_default_timeout(10000)
   def response_check(response):
    if response.status>=400:raise RuntimeError(f'HTTP {response.status}; stop audit')
   page.on('response',response_check)
   page.on('pageerror',lambda error:manifest['browserErrors'].append({'profile':profile,'message':str(error)}))
   page.on('dialog',lambda dialog:(manifest['interactionNotes'].append({'profile':profile,'case':'native-dialog','type':dialog.type}),dialog.dismiss()))
   def deny_api(route):
    route.abort();raise RuntimeError('Unexpected real API request; stop mock audit')
   page.route(re.compile(r'^https?://[^/]+/api/'),deny_api)
   def theme():
    page.evaluate('(mode)=>document.documentElement.dataset.themeMode=mode',mode)
    page.add_style_tag(content='*,*::before,*::after{transition-duration:0s!important;animation-duration:0s!important}')
   def go(path,selector=None):
    page.goto('http://127.0.0.1:5198'+path)
    if selector:page.locator(selector).first.wait_for()
    else:page.locator('#app').wait_for();page.wait_for_timeout(300)
    theme()
   def fixture(state):page.evaluate(FIXTURE,state);page.wait_for_timeout(80)
   def shot(code,name):
    page.wait_for_timeout(120)
    path=OUT/'screenshots'/profile/f'{code}-{name}.png';path.parent.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(path))
    metrics=page.evaluate(MEASURE)
    metricpath=OUT/'metrics'/profile/f'{code}.json';metricpath.parent.mkdir(parents=True,exist_ok=True);metricpath.write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
    entry={'profile':profile,'code':code,'name':name,'path':path.relative_to(OUT).as_posix(),'metrics':metricpath.relative_to(OUT).as_posix(),'route':page.url.split('5198')[-1],'viewport':[width,height],'theme':mode}
    manifest['captures']=[entry0 for entry0 in manifest['captures'] if not(entry0['profile']==profile and entry0['code']==code)]+[entry];save_manifest()
   def button(name):return page.get_by_role('button',name=name,exact=True)
   def chat():go('/remote/chat?workerId=worker_demo','textarea');fixture('chat-base')
   if width<500:
    go('/remote/login','input');shot('M01','login');fixture('login-error');shot('M02','login-error');fixture('login-loading');shot('M03','login-loading')
    go('/remote/devices','main');fixture('devices');shot('M04','devices')
    button('演示办公电脑的更多操作').click();page.get_by_role('dialog').wait_for();shot('M05','device-menu')
    button('删除设备').click();page.get_by_role('dialog',name='确认删除设备？').wait_for();shot('M06','device-delete-confirm');button('取消').click();page.keyboard.press('Escape')
    button('远程操作').click();page.get_by_test_id('option-panel').wait_for();shot('M07','selection-sheet');page.keyboard.press('Escape')
    fixture('devices-empty');shot('M08','devices-empty');fixture('devices-loading');shot('M09','devices-loading')
    go('/remote/devices','main');fixture('devices-error');shot('M10','devices-error')
    go('/remote/pair','#pair-code');shot('M11','pairing');page.locator('#pair-code').fill('ABCD2345');page.get_by_test_id('preview-btn').click();page.get_by_text('待绑定',exact=True).wait_for();shot('M12','pairing-preview')
    go('/remote/pair','#pair-code')
    page.evaluate("""async()=>{const {getRemoteGateway}=await import('/src/shared/api/remote-provider.ts');getRemoteGateway().previewPairing=async()=>{throw new Error('审计合成：配对码已过期，请在电脑重新生成')}}""")
    page.locator('#pair-code').fill('ABCD2345');page.get_by_test_id('preview-btn').click();page.wait_for_timeout(150);shot('M13','pairing-error')
    go('/remote/pair','#pair-code');page.evaluate("""()=>{const canvas=document.createElement('canvas');canvas.width=320;canvas.height=240;const ctx=canvas.getContext('2d');const draw=()=>{ctx.fillStyle='#475569';ctx.fillRect(0,0,320,240);ctx.fillStyle='#fff';ctx.font='20px sans-serif';ctx.fillText('SYNTHETIC CAMERA',45,125)};draw();const stream=canvas.captureStream(8);window.__auditCamera=setInterval(draw,125);Object.defineProperty(navigator,'mediaDevices',{value:{getUserMedia:async()=>stream},configurable:true})}""")
    button('扫码').click();page.get_by_text('请对准电脑「连接手机」上的配对二维码',exact=True).wait_for();shot('M14','scanner-preview');button('关闭扫码').click();page.evaluate('clearInterval(window.__auditCamera)')
    page.evaluate("""()=>Object.defineProperty(navigator,'mediaDevices',{value:{getUserMedia:async()=>{throw new DOMException('synthetic denial','NotAllowedError')}},configurable:true})""");button('扫码').click();page.get_by_text(re.compile('摄像头权限被拒绝')).wait_for();shot('M15','scanner-permission');button('关闭扫码').click()
    chat();page.locator('textarea').fill('请继续核对演示项目');shot('M16','chat-idle');page.get_by_test_id('chat-header-actions').get_by_role('button',name='退出登录').focus();page.keyboard.press('Tab');manifest['interactionNotes'].append({'profile':profile,'case':'closed-sidebar-tab','focus':page.evaluate("()=>{const e=document.activeElement,r=e.getBoundingClientRect();return {label:e.getAttribute('aria-label')||e.textContent.trim(),x:r.x,right:r.right,insideSidebar:!!e.closest('aside')}}")});save_manifest();button('新话题').click();shot('M17','new-topic');button('取消新话题').click()
    page.get_by_test_id('chat-header-actions').get_by_role('button',name='退出登录').click();page.get_by_role('dialog',name='确定退出登录？').wait_for();shot('M18','logout-confirm');button('取消').click()
    button('打开对话列表').click();shot('M19','conversation-list');manifest['interactionNotes'].append({'profile':profile,'case':'open-sidebar-focus','inside':page.evaluate("!!document.activeElement.closest('aside')"),'role':page.locator('aside').get_attribute('role')});page.keyboard.press('Escape');manifest['interactionNotes'].append({'profile':profile,'case':'sidebar-escape','stillVisible':page.locator('aside').evaluate('(e)=>e.getBoundingClientRect().right>0')});save_manifest();button('新建任务').click();page.get_by_role('dialog').wait_for();shot('M20','new-conversation')
    page.locator('#new-conv-workspace').click();page.get_by_test_id('option-panel').wait_for();shot('M21','project-selector');page.keyboard.press('Escape');page.keyboard.press('Escape')
    chat();fixture('chat-empty');shot('M22','chat-empty')
    chat();fixture('chat-loading');shot('M23','chat-loading')
    chat();fixture('chat-running');shot('M24','chat-running');page.get_by_test_id('run-status-toggle').click();shot('M25','run-details')
    chat();fixture('chat-busy');shot('M26','busy')
    chat();fixture('chat-failed');shot('M27','failed')
    chat();fixture('chat-approval');shot('M28','approval')
    approval_action=page.get_by_role('button',name=re.compile('批准')).filter(has_text=re.compile('批准'))
    if approval_action.count():
     before=page.get_by_role('dialog').count();approval_action.first.click();page.wait_for_timeout(180);manifest['interactionNotes'].append({'profile':profile,'case':'approval-click','requests':page.evaluate('window.__auditApprovalCalls'),'dialogsBefore':before,'dialogsAfter':page.get_by_role('dialog').count()});save_manifest()
    chat();page.locator('textarea').fill('离线时保留的合成草稿');fixture('chat-offline');shot('M29','offline')
    chat();page.locator('textarea').fill('暂停远程时保留的合成草稿');fixture('chat-paused');shot('M30','suspended')
    chat();fixture('global-error');shot('M31','request-error')
    chat();fixture('chat-attachments');shot('M32','message-attachments')
    chat();fixture('draft-uploading');button('添加附件').click();page.get_by_test_id('select-files').set_input_files({'name':'演示上传说明.txt','mimeType':'text/plain','buffer':b'synthetic audit content'});page.get_by_text('上传中',exact=True).wait_for();shot('M33','uploading')
    chat();fixture('draft-failed');button('添加附件').click();page.get_by_test_id('select-files').set_input_files({'name':'用于审计的较长文件名称与版本说明.txt','mimeType':'text/plain','buffer':b'synthetic audit content'});page.get_by_text('上传失败',exact=True).wait_for();shot('M34','upload-failure')
    chat();fixture('chat-native');shot('M35','native-conversation')
    chat();fixture('native-index');button('打开对话列表').click();page.get_by_test_id('native-sessions').get_by_role('button',name='刷新',exact=True).click();page.get_by_test_id('native-unavailable-toggle').wait_for();shot('M36','native-collapsed');page.get_by_test_id('native-unavailable-toggle').click();shot('M37','native-unsupported');page.get_by_test_id('native-unavailable').first.click();page.get_by_role('dialog').wait_for();shot('M38','native-explanation')
    chat();button('打开对话列表').click();page.locator('button[title=对话设置]').first.click();page.get_by_role('dialog').wait_for();shot('M44','conversation-settings');page.locator('input[value=pc_only]').check();button('保存').click();page.get_by_role('dialog',name='设置为仅电脑可见确认').wait_for();shot('M45','pc-only-confirm')
    go('/remote/tokens','main');shot('M39','tokens-empty');fixture('tokens');page.get_by_role('checkbox').check();page.get_by_text('演示自动化工具',exact=True).wait_for();shot('M40','tokens')
    button('新建令牌').click();page.get_by_role('dialog').wait_for();page.get_by_label('令牌名称',exact=True).fill('审计合成工具');page.locator('input[value="devices:delete"]').check();shot('M41','token-create')
    button('签发令牌').click();page.get_by_test_id('issued-secret').wait_for();shot('M42','token-issued');page.get_by_role('dialog').get_by_role('button',name='关闭',exact=True).click()
    button('吊销').first.click();page.get_by_role('dialog',name='确认吊销 API 令牌？').wait_for();shot('M43','token-revoke-confirm')
   else:
    go('/chat','textarea');shot('D01','local-chat-running')
    fixture('local-idle');page.locator('textarea').fill('审计合成输入');shot('D02','local-chat-idle')
    button('更多任务操作').click();page.get_by_role('menuitem',name='删除对话',exact=True).click();page.get_by_role('dialog',name='删除对话？').wait_for();shot('D03','delete-conversation');button('取消').click()
    page.evaluate("async()=>{const {useChatStore}=await import('/src/stores/chat.store.ts');await useChatStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia).selectConversation('conv_develop_ui')}")
    button('更多任务操作').click();page.get_by_role('menuitem',name='删除对话',exact=True).click();page.get_by_role('dialog',name='删除对话？').wait_for();button('删除对话').click();page.get_by_role('dialog',name='删除对话未完成').wait_for();shot('D28','delete-conflict');page.keyboard.press('Escape')
    page.get_by_test_id('native-unavailable-toggle').first.click();page.get_by_test_id('native-sessions').scroll_into_view_if_needed();shot('D04','native-panel')
    go('/agents','input[placeholder*="搜索名称"]');page.locator('input[placeholder*="搜索名称"]').fill('PI');page.get_by_test_id('pi-agent-details').first.wait_for();shot('D05','agents')
    fixture('verification-running');page.get_by_test_id('image-verifications').scroll_into_view_if_needed();shot('D06','image-verifications')
    page.get_by_test_id('verification-row').first.get_by_role('button',name='验证',exact=True).click();page.get_by_role('dialog').wait_for();shot('D07','model-usage-confirm');button('取消').click()
    go('/scenes','[data-role-id]');shot('D08','scenes');button('planner Agent').click() if button('planner Agent').count() else button('analyst Agent').click();page.get_by_role('option',name='PI (pi)',exact=True).click();page.get_by_test_id('pi-role-hint').wait_for();shot('D09','pi-role')
    go('/remote-link');page.get_by_text('连接手机',exact=True).first.wait_for();shot('D10','remote-link')
    fixture('roots');page.evaluate("""async()=>{const {useRemoteLinkStore}=await import('/src/stores/remote-link.store.ts');const {getLocalChatGateway}=await import('/src/shared/api/local-chat-provider.ts');const g=getLocalChatGateway();g.setRemoteLinkState({state:'paired',serverOrigin:'https://example.invalid',workerId:'audit_worker',deviceName:'演示电脑',connectionStatus:'online',lastConnectedAt:new Date().toISOString()});await useRemoteLinkStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia).refreshLink()}""");page.get_by_test_id('authorized-roots').get_by_role('button',name='刷新',exact=True).click();page.get_by_test_id('authorized-roots').scroll_into_view_if_needed();shot('D11','authorized-roots')
    go('/remote-link?mockState=pairing');page.get_by_test_id('pair-qrcode').wait_for();shot('D12','pair-qr')
    go('/workspaces');button('添加目录').wait_for();shot('D13','workspaces');button('添加目录').click();page.get_by_role('dialog').wait_for();shot('D14','workspace-form')
    go('/settings');page.get_by_text('系统设置',exact=True).last.wait_for();shot('D15','settings-placeholder')
    for code,name,path in [('D16','overview','/overview'),('D17','teams','/teams'),('D18','tasks','/tasks'),('D19','sessions','/sessions'),('D20','approvals','/approvals'),('D21','templates','/templates'),('D22','updates','/updates'),('D24','onboarding','/onboarding')]:
     go(path);page.wait_for_timeout(250);shot(code,name)
    go('/tasks');links=page.locator('a[href^="/tasks/"]')
    if links.count():links.first.click();page.wait_for_timeout(250);shot('D25','task-detail')
    else:
     page.evaluate("""async()=>{const {getUiGateway}=await import('/src/shared/api/index.ts');const {router}=await import('/src/app/router/index.ts');const rows=await getUiGateway().listTasks({});const task=Array.isArray(rows)?rows[0]:rows.items?.[0];if(task)await router.push('/tasks/'+task.id)}""");page.wait_for_timeout(250);shot('D25','task-detail')
    go('/chat','textarea');page.evaluate("""async()=>{const {useChatStore}=await import('/src/stores/chat.store.ts');const c=useChatStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia);c.stopPolling();c.conversations=[];c.activeConversationId=null;c.messages=[];c.conversationRuns=[];c.activeRun=null}""");shot('D26','local-empty')
    page.evaluate("""async()=>{const {useChatStore}=await import('/src/stores/chat.store.ts');useChatStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia).loadError='读取对话失败，请刷新核对（审计合成状态）'}""");shot('D27','local-error')
    page.evaluate("""async()=>{const {getLocalChatGateway}=await import('/src/shared/api/local-chat-provider.ts');const {useLocalAuthStore}=await import('/src/stores/local-auth.store.ts');const {router}=await import('/src/app/router/index.ts');getLocalChatGateway().getLocalAuthStatus=async()=>({authenticated:false,protocolVersion:'0.11.0'});const a=useLocalAuthStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia);a.currentMode='real';a.authenticated=false;await router.push('/connect')}""");page.get_by_text('HQAgent 本地角色对话工作台',exact=True).wait_for();shot('D23','connect')
   print(f'{profile}: completed',flush=True);context.close();save_manifest()
 finally:browser.close();save_manifest()
print(json.dumps({'captures':len(manifest['captures']),'browserErrors':manifest['browserErrors'],'interactionNotes':manifest['interactionNotes']},ensure_ascii=False))
