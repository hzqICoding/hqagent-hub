import os, json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path.cwd()
os.environ['TEMP']=os.environ['TMP']=str(root/'.tmp')
out=root/'.hqagent/handoffs/screenshots/r16-p3-fix1'
results=[]
AUDIT=r'''(selector) => {
  function rgba(value) {
    const parts=value.match(/[\d.]+/g)?.map(Number);
    if (!value.startsWith('rgb') || !parts || parts.length<3) throw new Error('Unsupported computed color');
    return [parts[0],parts[1],parts[2],parts[3]??1];
  }
  function blend(a,b) { return [0,1,2].map(i=>a[i]*a[3]+b[i]*(1-a[3])).concat(1); }
  function background(el) {
    if(!el) return [255,255,255,1];
    const c=rgba(getComputedStyle(el).backgroundColor);
    return c[3]===1 ? c : blend(c,background(el.parentElement));
  }
  function lum(c) { const rgb=c.slice(0,3).map(v=>{v/=255;return v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4}); return rgb[0]*0.2126+rgb[1]*0.7152+rgb[2]*0.0722; }
  function check(el, style, kind) {
    const bg=background(el), foreground=style.getPropertyValue('-webkit-text-fill-color')||style.color;
    let fg=rgba(foreground);
    for(let parent=el;parent;parent=parent.parentElement) fg[3]*=Number(getComputedStyle(parent).opacity);
    fg=blend(fg,bg);
    const a=lum(fg),b=lum(bg),ratio=(Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
    const label=el.closest('[data-probe]')?.getAttribute('data-probe') || el.tagName.toLowerCase();
    if(ratio<4.5) throw new Error(`${label} ${kind} contrast ${ratio.toFixed(2)} < 4.5 (${style.color} on ${getComputedStyle(el).backgroundColor})`);
    return {label,kind,ratio:Number(ratio.toFixed(2))};
  }
  const checks=[];
  for(const el of document.querySelectorAll(selector)) {
    if(!el.getClientRects().length) continue;
    checks.push(check(el,getComputedStyle(el),'text'));
    if(el.getAttribute('placeholder')) checks.push(check(el,getComputedStyle(el,'::placeholder'),'placeholder'));
    const placeholder=el.querySelector('.hq-form-placeholder');
    if(placeholder) checks.push(check(placeholder,getComputedStyle(placeholder),'placeholder'));
  }
  if(!checks.length) throw new Error('No rendered form controls');
  return {count:checks.length,minContrast:Math.min(...checks.map(c=>c.ratio))};
}'''
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':375,'height':812},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(type(e).__name__))
    def theme(mode):
        page.evaluate('(mode)=>document.documentElement.dataset.themeMode=mode',mode)
        page.add_style_tag(content='*,*::before,*::after{transition-duration:0s!important;animation-duration:0s!important}')
    def shot(mode,name,selector='.hq-form-control'):
        result=page.evaluate(AUDIT,selector)
        results.append({'mode':mode,'view':name,**result})
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        page.screenshot(path=str(out/f'{mode}-{name}.png'))
    for mode in ['light','dark']:
        page.emulate_media(color_scheme=mode)
        page.set_viewport_size({'width':375,'height':812})
        page.goto('http://127.0.0.1:5198/remote/login')
        page.locator('#remote-username').wait_for() if page.locator('#remote-username').count() else page.locator('input').first.wait_for()
        theme(mode); shot(mode,'mobile-login-375x812')
        page.goto('http://127.0.0.1:5198/remote/pair'); page.locator('#pair-code').wait_for()
        theme(mode); shot(mode,'mobile-pair-375x812')
        page.goto('http://127.0.0.1:5198/remote/chat?workerId=worker_demo'); page.locator('textarea').wait_for()
        page.evaluate('''async()=>{
          const {useRemoteChatStore}=await import('/src/stores/remote-chat.store.ts');
          const store=useRemoteChatStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia);
          store.runs=[]; store.approvals=[]; store.conversations.forEach(c=>c.busy=false);
        }''')
        theme(mode); page.locator('textarea').fill('主题验收示例文字')
        shot(mode,'mobile-chat-375x812','footer .hq-form-control')
        header=page.evaluate(AUDIT,'header button[title="切换电脑"],header button[aria-label="打开对话列表"],header button[aria-label="退出登录"]')
        results.append({'mode':mode,'view':'mobile-header',**header})
        page.set_viewport_size({'width':1280,'height':800})
        page.goto('http://127.0.0.1:5198/chat'); page.locator('textarea').wait_for()
        page.evaluate('''async()=>{
          const {mockLocalChatGateway:g}=await import('/src/shared/api/mock-local-chat-gateway.ts');
          const c=await g.createLocalConversation({title:'主题验收示例任务',workspaceId:(await g.listLocalWorkspaces())[0].id,sceneId:'analyze'});
          const {useChatStore}=await import('/src/stores/chat.store.ts');
          const store=useChatStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia);
          await store.fetchConversations();await store.selectConversation(c.id);
        }''')
        theme(mode); page.locator('textarea').fill('桌面输入框主题验收示例')
        shot(mode,'desktop-chat-1280x800')
        page.evaluate('''async()=>{
          const {mockLocalChatGateway:g}=await import('/src/shared/api/mock-local-chat-gateway.ts');
          g.getRemoteLink=async()=>({state:'unpaired'});
          const {router}=await import('/src/app/router/index.ts');await router.push('/remote-link');
        }''')
        page.get_by_placeholder('https://hqremote.hylucky.top').wait_for()
        assert page.get_by_placeholder('https://hqremote.hylucky.top').input_value()=='https://hqremote.hylucky.top'
        theme(mode); shot(mode,'desktop-remote-link-1280x800')
        page.goto('http://127.0.0.1:5198/workspaces'); page.get_by_role('button',name='添加目录',exact=True).click()
        page.get_by_role('dialog').wait_for(); theme(mode)
        shot(mode,'desktop-workspace-form-1280x800','[role=dialog] .hq-form-control')
        page.keyboard.press('Escape')
        # Mount the actual shared components plus native input types/states.
        page.evaluate('''async()=>{
          const {mountFormContrastFixture}=await import('/src/shared/theme/forms.browser-fixture.ts');
          const host=document.createElement('div');host.id='contrast-fixture';host.style.cssText='position:fixed;inset:0;overflow:auto;z-index:9999';document.body.append(host);
          window.__unmountContrast=mountFormContrastFixture(host);
        }''')
        theme(mode)
        for state in ['normal','focus','autofill']:
            if state=='focus':page.locator('#contrast-fixture input').first.focus()
            if state=='autofill':
                cdp=page.context.new_cdp_session(page)
                cdp.send('DOM.enable');cdp.send('CSS.enable')
                doc=cdp.send('DOM.getDocument')
                node=cdp.send('DOM.querySelector',{'nodeId':doc['root']['nodeId'],'selector':'#contrast-fixture input'})
                cdp.send('CSS.forcePseudoState',{'nodeId':node['nodeId'],'forcedPseudoClasses':['autofill']})
            result=page.evaluate(AUDIT,'#contrast-fixture .hq-form-control, #contrast-fixture .hq-choice-label')
            results.append({'mode':mode,'view':f'shared-controls-{state}',**result})
        page.evaluate('window.__unmountContrast();document.querySelector("#contrast-fixture").remove()')
    # Real jsqr fallback reading a synthetic canvas MediaStream, no actual camera/secret.
    page.goto('http://127.0.0.1:5198/remote/pair'); page.locator('#pair-code').wait_for()
    page.evaluate('''async()=>{
      const QRCode=(await import('/node_modules/.vite/deps/qrcode.js')).default;
      const canvas=document.createElement('canvas');await QRCode.toCanvas(canvas,location.origin+'/remote/pair#code=ABCD2345',{width:480,margin:4});
      const stream=canvas.captureStream(8);window.__qrStops=0;
      for(const track of stream.getTracks()){const stop=track.stop.bind(track);track.stop=()=>{window.__qrStops++;stop()}}
      Object.defineProperty(window,'BarcodeDetector',{value:undefined,configurable:true});
      Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async()=>stream,configurable:true});
      const {mockRemoteGateway:g}=await import('/src/shared/api/mock-remote-gateway.ts');
      window.__qrConfirmations=0;const confirm=g.confirmPairing.bind(g);g.confirmPairing=(...args)=>{window.__qrConfirmations++;return confirm(...args)};
    }''')
    assert page.evaluate('!performance.getEntriesByType("resource").some(e=>e.name.toLowerCase().includes("/jsqr"))')
    page.get_by_role('button',name='扫码',exact=True).click()
    page.get_by_text('待绑定',exact=True).wait_for()
    assert page.locator('#pair-code').input_value()=='ABCD2345'
    assert page.evaluate('window.__qrStops')==1
    assert page.evaluate('performance.getEntriesByType("resource").some(e=>e.name.toLowerCase().includes("/jsqr"))')
    assert page.evaluate('window.__qrConfirmations')==0
    assert page.evaluate('!JSON.stringify(localStorage).includes("ABCD2345") && !JSON.stringify(sessionStorage).includes("ABCD2345") && !location.href.includes("ABCD2345")')
    assert not errors
    print(json.dumps({'contrastChecks':results,'screenshots':12,'syntheticJsqrStream':'PASS','cameraReleased':'PASS','automaticBinding':'not performed','browserErrors':len(errors)},ensure_ascii=False))
    browser.close()
