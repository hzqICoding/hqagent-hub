import json,os,threading
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
from playwright.sync_api import sync_playwright
root=Path.cwd();os.environ['TEMP']=os.environ['TMP']=str(root/'.tmp')
folder=root/'.tmp/qr-freeze-browser'
class Handler(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  if self.path=='/favicon.ico':self.send_response(204);self.end_headers();return
  super().do_GET()
server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(folder)))
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True)
  page=browser.new_page(viewport={'width':1280,'height':800})
  errors=[];failed=[];page.on('pageerror',lambda error:errors.append(str(error)))
  def on_response(response):
   if response.status>=400:
    failed.append({'status':response.status})
    raise RuntimeError(f'Test server HTTP {response.status}; stopping')
  page.on('response',on_response)
  page.goto(f'http://127.0.0.1:{server.server_port}/')
  page.wait_for_function('window.__freezeResult !== undefined',timeout=45000)
  result=page.evaluate('window.__freezeResult')
  if not result['ok']:raise AssertionError(result)
  assert not errors,errors
  assert not failed,failed
  audit=json.loads((folder/'module-audit.json').read_text(encoding='utf-8'))
  assert audit['legacyQrModules']==0 and audit['uqrIncluded']
  report={**result['result'],'moduleAudit':audit,'browserErrors':len(errors),'httpErrors':len(failed),'engine':'Chromium; fresh production ES module graph; mock APIs and synthetic camera'}
  output=root/'.hqagent/handoffs/qr-freeze-validation';output.mkdir(parents=True,exist_ok=True)
  (output/'frozen-browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps(report,ensure_ascii=False));browser.close()
finally:server.shutdown();server.server_close()
