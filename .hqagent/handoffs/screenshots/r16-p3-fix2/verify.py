import os, json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path.cwd()
os.environ['TEMP']=os.environ['TMP']=str(root/'.tmp')
out=root/'.hqagent/handoffs/screenshots/r16-p3-fix2'
results=[]
AUDIT="(selector) => {\n  function rgba(value) {\n    const parts=value.match(/[\\d.]+/g)?.map(Number);\n    if (!value.startsWith('rgb') || !parts || parts.length<3) throw new Error('Unsupported computed color');\n    return [parts[0],parts[1],parts[2],parts[3]??1];\n  }\n  function blend(a,b) { return [0,1,2].map(i=>a[i]*a[3]+b[i]*(1-a[3])).concat(1); }\n  function background(el) {\n    if(!el) return [255,255,255,1];\n    const c=rgba(getComputedStyle(el).backgroundColor);\n    return c[3]===1 ? c : blend(c,background(el.parentElement));\n  }\n  function lum(c) { const rgb=c.slice(0,3).map(v=>{v/=255;return v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4}); return rgb[0]*0.2126+rgb[1]*0.7152+rgb[2]*0.0722; }\n  function check(el, style, kind) {\n    const bg=background(el), foreground=style.getPropertyValue('-webkit-text-fill-color')||style.color;\n    let fg=rgba(foreground);\n    for(let parent=el;parent;parent=parent.parentElement) fg[3]*=Number(getComputedStyle(parent).opacity);\n    fg=blend(fg,bg);\n    const a=lum(fg),b=lum(bg),ratio=(Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);\n    const label=el.closest('[data-probe]')?.getAttribute('data-probe') || el.tagName.toLowerCase();\n    if(kind==='placeholder' && style.fontWeight!=='400') throw new Error('Placeholder must use regular weight');\n    const required=kind==='placeholder'?3:4.5;\n    if(ratio<required) throw new Error(`${label} ${kind} contrast ${ratio.toFixed(2)} < ${required} (${style.color} on ${getComputedStyle(el).backgroundColor})`);\n    return {label,kind,ratio:Number(ratio.toFixed(2))};\n  }\n  const checks=[];\n  for(const el of document.querySelectorAll(selector)) {\n    if(!el.getClientRects().length) continue;\n    checks.push(check(el,getComputedStyle(el),'text'));\n    if(el.getAttribute('placeholder')) checks.push(check(el,getComputedStyle(el,'::placeholder'),'placeholder'));\n    const placeholder=el.querySelector('.hq-form-placeholder');\n    if(placeholder) checks.push(check(placeholder,getComputedStyle(placeholder),'placeholder'));\n  }\n  if(!checks.length) throw new Error('No rendered form controls');\n  return {count:checks.length,minContrast:Math.min(...checks.map(c=>c.ratio))};\n}"
READY="""async()=>{
 const {mockRemoteGateway:g}=await import('/src/shared/api/mock-remote-gateway.ts');g.runs=[];g.commands=[];g.approvals=[];g.conversations.forEach(c=>c.busy=false);
 const {useRemoteChatStore}=await import('/src/stores/remote-chat.store.ts');
 const store=useRemoteChatStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia);
 store.runs=[];store.commands=[];store.approvals=[];store.conversations.forEach(c=>c.busy=false);
 store.stopPolling();store.stopDevicePolling();
}"""
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page(viewport={'width':375,'height':812},device_scale_factor=1)
 page.set_default_timeout(12000)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 def theme(mode):
  page.evaluate('(mode)=>document.documentElement.dataset.themeMode=mode',mode)
  page.add_style_tag(content='*,*::before,*::after{transition-duration:0s!important;animation-duration:0s!important}')
 def shot(mode,name):
  assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),name
  page.screenshot(path=str(out/f'{mode}-{name}.png'))
 def geometry():
  return page.evaluate("""()=>{
    const rect=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom}};
    const text=rect('.hq-composer-text'),clip=rect('.hq-composer-icon'),send=rect('.hq-composer-send');
    if(send.width!==48 || send.height!==44 || clip.height!==44 || text.height<44 || Math.abs(send.bottom-text.bottom)>1) throw Error('Composer geometry mismatch');
    return {text,clip,send};
  }""")
 for mode in ['light','dark']:
  page.emulate_media(color_scheme=mode);page.set_viewport_size({'width':375,'height':812})
  page.goto('http://127.0.0.1:5198/remote/chat?workerId=worker_demo');page.locator('textarea').wait_for();page.evaluate(READY);theme(mode)
  page.get_by_role('button',name='新话题',exact=True).wait_for(state='visible')
  assert page.get_by_role('button',name='新话题',exact=True).is_enabled()
  page.locator('textarea').fill('请继续分析项目结构')
  results.append({'mode':mode,'view':'mobile-composer','geometry':geometry(),**page.evaluate(AUDIT,'.hq-composer-text')})
  assert page.evaluate("[...document.querySelectorAll('[data-testid=chat-header-actions] button')].every(b=>b.getBoundingClientRect().width===44 && b.getBoundingClientRect().height===44)")
  results.append({'mode':mode,'view':'mobile-header',**page.evaluate(AUDIT,'[data-testid=connection-status],header button[title="切换电脑"],header button[aria-label="管理设备"],header button[aria-label="退出登录"]')})
  shot(mode,'mobile-chat-375x812')
  page.get_by_role('button',name='新话题',exact=True).click();page.get_by_test_id('new-topic-tag').wait_for()
  shot(mode,'mobile-new-topic-375x812')
  page.locator('textarea').fill('多行输入排版测试\n第二行：发送按钮保持原尺寸\n第三行：与输入框底部对齐')
  results.append({'mode':mode,'view':'multiline','geometry':geometry()})
  shot(mode,'mobile-multiline-375x812');page.locator('textarea').fill('请继续分析项目结构')
  page.get_by_test_id('chat-header-actions').get_by_role('button',name='退出登录',exact=True).click();page.get_by_role('dialog',name='确定退出登录？').wait_for()
  assert page.evaluate("document.activeElement.hasAttribute('data-confirm-cancel')")
  shot(mode,'mobile-logout-375x812');page.get_by_role('button',name='取消',exact=True).click()
  assert page.evaluate("document.activeElement.getAttribute('aria-label')==='退出登录'")
  page.evaluate("""async()=>{const {useRemoteChatStore}=await import('/src/stores/remote-chat.store.ts');useRemoteChatStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia).devices[0].online=false}""")
  page.get_by_test_id('connection-status').filter(has_text='电脑离线').wait_for();assert page.get_by_role('button',name='新话题',exact=True).is_disabled()
  results.append({'mode':mode,'view':'offline-status',**page.evaluate(AUDIT,'[data-testid=connection-status]')});shot(mode,'mobile-offline-375x812')
  page.goto('http://127.0.0.1:5198/remote/devices');page.get_by_role('button',name='远程操作',exact=True).wait_for();theme(mode)
  page.get_by_role('button',name='远程操作',exact=True).click();page.get_by_role('dialog',name='远程操作',exact=True).wait_for()
  assert page.evaluate("document.body.style.overflow==='hidden'")
  shot(mode,'mobile-select-375x812');page.keyboard.press('Escape')
  assert page.evaluate("document.activeElement.getAttribute('aria-label')==='远程操作'")
  page.goto('http://127.0.0.1:5198/remote/pair');page.locator('#pair-code').wait_for();theme(mode)
  results.append({'mode':mode,'view':'pair-placeholder',**page.evaluate(AUDIT,'#pair-code')});shot(mode,'mobile-pair-placeholder-375x812')
  page.set_viewport_size({'width':1280,'height':800});page.goto('http://127.0.0.1:5198/chat');page.locator('textarea').wait_for()
  page.evaluate("""async()=>{
   const {mockLocalChatGateway:g}=await import('/src/shared/api/mock-local-chat-gateway.ts');
   const c=await g.createLocalConversation({title:'输入区验收示例任务',workspaceId:(await g.listLocalWorkspaces())[0].id,sceneId:'analyze'});
   const {useChatStore}=await import('/src/stores/chat.store.ts');
   const store=useChatStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia);
   await store.fetchConversations();await store.selectConversation(c.id);store.stopPolling();
  }""")
  theme(mode);page.locator('textarea').fill('桌面对话输入区验收示例')
  results.append({'mode':mode,'view':'desktop-composer','geometry':geometry(),**page.evaluate(AUDIT,'.hq-composer-text')});shot(mode,'desktop-chat-1280x800')
  page.evaluate("""async()=>{
   const {mountFormContrastFixture}=await import('/src/shared/theme/forms.browser-fixture.ts');
   const host=document.createElement('div');host.id='contrast-fixture';host.style.cssText='position:fixed;inset:0;overflow:auto;z-index:9999';document.body.append(host);window.__unmountContrast=mountFormContrastFixture(host);
  }""")
  theme(mode)
  for state in ['normal','focus','autofill']:
   if state=='focus':page.locator('#contrast-fixture input').first.focus()
   if state=='autofill':
    cdp=page.context.new_cdp_session(page);cdp.send('DOM.enable');cdp.send('CSS.enable');doc=cdp.send('DOM.getDocument');node=cdp.send('DOM.querySelector',{'nodeId':doc['root']['nodeId'],'selector':'#contrast-fixture input'});cdp.send('CSS.forcePseudoState',{'nodeId':node['nodeId'],'forcedPseudoClasses':['autofill']})
   results.append({'mode':mode,'view':f'shared-controls-{state}',**page.evaluate(AUDIT,'#contrast-fixture .hq-form-control,#contrast-fixture .hq-choice-label')})
  page.evaluate('window.__unmountContrast();document.querySelector("#contrast-fixture").remove()')
 assert not errors,errors
 result={'checks':results,'screenshots':len(list(out.glob('*.png'))),'browserErrors':len(errors),'source':'Chromium + local mock fixtures; no real account/device'}
 (out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result,ensure_ascii=False));browser.close()
