import os,json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path.cwd();os.environ['TEMP']=os.environ['TMP']=str(root/'.tmp')
out=root/'.hqagent/handoffs/screenshots/r16-p3-fix3'
# Synthetic metadata only; no user CLI histories or active sessions are loaded.
FIXTURE="""async(remote)=>{
 const {nativeExamples}=await import('/src/shared/api/native-examples.ts');
 const {mockRemoteGateway:r}=await import('/src/shared/api/mock-remote-gateway.ts');
 const {mockLocalChatGateway:l}=await import('/src/shared/api/mock-local-chat-gateway.ts');
 const gateway=remote?r:l;
 if(remote){
  r.devices[0].supportedWireRevisions=[4];
  const {useRemoteChatStore}=await import('/src/stores/remote-chat.store.ts');
  const store=useRemoteChatStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia);
  store.devices[0].supportedWireRevisions=[4];store.stopPolling();store.stopDevicePolling();
 }
 const projects=remote?r.catalog.workspaces.map(w=>({id:w.workspaceId,name:w.name})):await l.listLocalWorkspaces();
 const make=(id,title,workspaceId,status,version,agentType='codex')=>({...nativeExamples(workspaceId)[0],nativeSessionId:id,title,agentType,format:{status,cliVersion:version,...(status==='readable'?{readerId:'synthetic'}:{reason:'该 CLI 版本尚未验证'})}});
 const items=[make('available_example','示例：梳理项目结构',projects[0].id,'readable','0.148.0'),make('unavailable_example','示例：历史接口讨论',projects[0].id,'unsupported','0.111.0'),make('unavailable_second','示例：旧版任务记录',projects[0].id,'unsupported','2.1.251','claude'),make('all_unavailable','示例：旧版页面记录',projects[1].id,'unsupported','0.98.0')];
 gateway.listNativeSessions=async()=>({items:remote?items.map(item=>({...item,workerId:'worker_demo',workerOnline:true})):items,hasMore:false});
 window.__nativeRequests=0;
 for(const method of ['readNativeMessages','getNativeSession','importNativeSession']) {gateway[method]=async()=>{window.__nativeRequests++;throw new Error('Unexpected native read/import')}};
 return projects[0].id;
}"""
results=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page();page.set_default_timeout(15000)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 for remote in [True,False]:
  width,height=(375,812) if remote else (1280,800)
  device='mobile' if remote else 'desktop'
  for mode in ['light','dark']:
   page.set_viewport_size({'width':width,'height':height});page.emulate_media(color_scheme=mode)
   page.goto('http://127.0.0.1:5198/remote/chat?workerId=worker_demo' if remote else 'http://127.0.0.1:5198/chat')
   page.locator('textarea').wait_for()
   first=page.evaluate(FIXTURE,remote)
   if remote:page.get_by_role('button',name='打开对话列表',exact=True).click()
   panel=page.get_by_test_id('native-sessions');panel.get_by_role('button',name='刷新',exact=True).click()
   panel.get_by_text('暂不支持（2）',exact=True).wait_for()
   page.evaluate('(mode)=>document.documentElement.dataset.themeMode=mode',mode)
   page.add_style_tag(content='*,*::before,*::after{transition-duration:0s!important;animation-duration:0s!important}')
   assert panel.get_by_test_id('native-readable').count()==1
   assert panel.get_by_test_id('native-unavailable').count()==0
   assert panel.get_by_test_id('native-empty-readable').count()==1
   def shot(name):
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
    page.screenshot(path=str(out/f'{mode}-{device}-{name}-{width}x{height}.png'))
   shot('collapsed')
   group=panel.locator(f'[data-workspace="{first}"]')
   toggle=group.get_by_test_id('native-unavailable-toggle');toggle.click()
   group.get_by_test_id('native-unavailable').first.scroll_into_view_if_needed()
   assert group.get_by_test_id('native-unavailable').count()==2
   assert toggle.get_attribute('aria-expanded')=='true'
   shot('expanded')
   group.get_by_test_id('native-unavailable').filter(has_text='历史接口讨论').click()
   explanation=page.get_by_test_id('native-unavailable-explanation');explanation.wait_for()
   assert 'Codex 0.111.0' in explanation.inner_text()
   assert '无法读取或续接' in explanation.inner_text()
   assert page.get_by_role('dialog').get_by_role('button',name='接着对话',exact=True).count()==0
   assert page.evaluate('window.__nativeRequests')==0
   shot('explanation')
   page.keyboard.press('Escape');assert page.get_by_role('dialog').count()==0
   assert page.evaluate("document.activeElement.dataset.testid==='native-unavailable'")
   results.append({'mode':mode,'device':device,'readable':1,'unavailableByWorkspace':[2,1],'defaultCollapsed':True,'emptyReadableWorkspaces':1,'readOrImportRequests':page.evaluate('window.__nativeRequests'),'focusReturned':True,'horizontalOverflow':False})
 assert not errors,errors
 result={'checks':results,'screenshots':len(list(out.glob('*.png'))),'browserErrors':len(errors),'source':'Chromium with synthetic mock metadata'}
 (out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False));browser.close()
