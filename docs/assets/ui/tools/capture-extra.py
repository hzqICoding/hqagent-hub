import os,json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
from audit_paths import ROOT as root, OUT as out, TOOLS
os.environ['TEMP']=os.environ['TMP']=str(root/'.tmp')
manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'));measure=(TOOLS/'measure.js').read_text(encoding='utf-8')
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 try:
  for mode in ['light','dark']:
   profile='desktop-'+mode;context=browser.new_context(viewport={'width':1280,'height':800},color_scheme=mode);page=context.new_page()
   def response_check(response):
    if response.status>=400:raise RuntimeError(f'HTTP {response.status}; stop audit')
   page.on('response',response_check)
   def deny_api(route):route.abort();raise RuntimeError('Unexpected real API request')
   page.route(re.compile(r'^https?://[^/]+/api/'),deny_api)
   def shot(code,name):
    page.evaluate('(mode)=>document.documentElement.dataset.themeMode=mode',mode);page.wait_for_timeout(150)
    path=out/'screenshots'/profile/f'{code}-{name}.png';page.screenshot(path=str(path));metric=out/'metrics'/profile/f'{code}.json';metric.write_text(json.dumps(page.evaluate(measure),ensure_ascii=False,indent=2),encoding='utf-8')
    manifest['captures']=[r for r in manifest['captures'] if not(r['profile']==profile and r['code']==code)];manifest['captures'].append({'profile':profile,'code':code,'name':name,'path':path.relative_to(out).as_posix(),'metrics':metric.relative_to(out).as_posix(),'route':page.url.split('5198')[-1],'viewport':[1280,800],'theme':mode})
   page.goto('http://127.0.0.1:5198/approvals');page.get_by_role('button',name=re.compile('批准')).first.wait_for();page.get_by_role('button',name=re.compile('批准')).first.click();page.get_by_role('dialog').wait_for();shot('D29','approval-confirm')
   page.goto('http://127.0.0.1:5198/workspaces');page.get_by_role('button',name='添加目录',exact=True).wait_for()
   page.wait_for_timeout(650)
   page.evaluate("""async()=>{const {useWorkspaceStore}=await import('/src/stores/workspace.store.ts');const store=useWorkspaceStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia);store.workspaces[0].memoryDirPresent=false;store.workspaces[0].name='审计合成工作区';store.workspaces[0].path='E:/Audit/SyntheticProject'}""");shot('D30','workspace-missing-memory')
   page.goto('http://127.0.0.1:5198/dev/ui-kit');page.get_by_text('组件状态矩阵',exact=False).first.wait_for() if page.get_by_text('组件状态矩阵',exact=False).count() else page.wait_for_timeout(300);shot('D31','ui-kit-dev-only')
   context.close()
 finally:browser.close();(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'captures':len(manifest['captures']),'extraStates':['desktop approval confirmation','workspace missing-memory','development UI kit']},ensure_ascii=False))
