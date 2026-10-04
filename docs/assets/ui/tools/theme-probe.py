import os,json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
from audit_paths import ROOT as root, OUT as out, TOOLS
os.environ['TEMP']=os.environ['TMP']=str(root/'.tmp')
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1280,'height':800},color_scheme='dark')
 def response_check(response):
  if response.status>=400:raise RuntimeError(f'HTTP {response.status}; stop audit')
 page.on('response',response_check)
 def deny_api(route):
  route.abort();raise RuntimeError('Unexpected real API request; stop mock audit')
 page.route(re.compile(r'^https?://[^/]+/api/'),deny_api)
 page.goto('http://127.0.0.1:5198/chat');page.locator('textarea').wait_for();page.evaluate("document.documentElement.dataset.themeMode='dark'")
 report=page.evaluate("""()=>{
  const samples=[...document.querySelectorAll('[class]')].filter(e=>e.className.toString().includes('border-border/')).filter(e=>e.getBoundingClientRect().width>0).slice(0,12).map(e=>({classes:e.className,border:getComputedStyle(e).borderTopColor,text:getComputedStyle(e).color,variable:getComputedStyle(e).getPropertyValue('--color-border-default')}));
  function rules(list){return [...list].flatMap(r=>r.cssRules?rules(r.cssRules):[r.cssText]).filter(Boolean)}
  const css=[...document.styleSheets].flatMap(sheet=>{try{return rules(sheet.cssRules)}catch{return []}});
  return {samples,matchingRules:css.filter(rule=>rule.includes('border-border\\/'))};
 }""")
 (out/'theme-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False));browser.close()
