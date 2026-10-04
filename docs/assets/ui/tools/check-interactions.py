import json,os,re
from pathlib import Path
from playwright.sync_api import sync_playwright
from audit_paths import ROOT as root, OUT as out, TOOLS
os.environ['TEMP']=os.environ['TMP']=str(root/'.tmp')
fixture=(TOOLS/'fixtures.js').read_text(encoding='utf-8');measure=(TOOLS/'measure.js').read_text(encoding='utf-8');manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 try:
  for width,height in [(375,812),(390,844)]:
   for mode in ['light','dark']:
    profile=f'mobile-{width}-{mode}';context=browser.new_context(viewport={'width':width,'height':height},color_scheme=mode);page=context.new_page()
    def on_response(response):
     if response.status>=400:raise RuntimeError(f'HTTP {response.status}; stop audit')
    page.on('response',on_response)
    def reject_api(route):route.abort();raise RuntimeError('Unexpected real API request')
    page.route(re.compile(r'^https?://[^/]+/api/'),reject_api)
    page.goto('http://127.0.0.1:5198/remote/chat?workerId=worker_demo');page.locator('textarea').wait_for();page.evaluate(fixture,'chat-base')
    page.evaluate("""async()=>{const {useRemoteChatStore}=await import('/src/stores/remote-chat.store.ts');const {getRemoteGateway}=await import('/src/shared/api/remote-provider.ts');const s=useRemoteChatStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia);s.messages=[];s.conversations=[];s.activeConversationId=null;s.isLoadingConversations=false;s.isSnapshotRebuilding=false;window.__auditSendCalls=0;getRemoteGateway().sendMessage=async()=>{window.__auditSendCalls++;return null}}""")
    page.evaluate('(mode)=>document.documentElement.dataset.themeMode=mode',mode)
    page.locator('textarea').fill('首次使用时尝试发送的审计合成草稿');send=page.get_by_role('button',name='发送消息',exact=True);enabled=send.is_enabled();send.click();page.wait_for_timeout(150)
    info=page.evaluate("""async()=>{const {useRemoteChatStore}=await import('/src/stores/remote-chat.store.ts');const s=useRemoteChatStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia);return {calls:window.__auditSendCalls,activeConversationId:s.activeConversationId,error:s.sendError,hasDraft:document.querySelector('textarea').value.length>0}}""")
    manifest['interactionNotes']=[r for r in manifest['interactionNotes'] if not(r['profile']==profile and r['case']=='send-without-conversation')]
    manifest['interactionNotes'].append({'profile':profile,'case':'send-without-conversation','buttonEnabled':enabled,**info})
    path=out/'screenshots'/profile/'M46-no-conversation-send.png';page.screenshot(path=str(path))
    metrics=out/'metrics'/profile/'M46.json';metrics.write_text(json.dumps(page.evaluate(measure),ensure_ascii=False,indent=2),encoding='utf-8')
    manifest['captures']=[r for r in manifest['captures'] if not(r['profile']==profile and r['code']=='M46')]
    manifest['captures'].append({'profile':profile,'code':'M46','name':'no-conversation-send','path':path.relative_to(out).as_posix(),'metrics':metrics.relative_to(out).as_posix(),'route':'/remote/chat?workerId=worker_demo','viewport':[width,height],'theme':mode})
    context.close()
 finally:browser.close();(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([r for r in manifest['interactionNotes'] if r['case']=='send-without-conversation'],ensure_ascii=False))
