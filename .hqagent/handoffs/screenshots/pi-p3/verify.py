import os,json,re
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path.cwd();os.environ['TEMP']=os.environ['TMP']=str(root/'.tmp')
out=root/'.hqagent/handoffs/screenshots/pi-p3'
results=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1280,'height':800});page.set_default_timeout(15000)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 for mode in ['light','dark']:
  page.emulate_media(color_scheme=mode)
  def theme():
   page.evaluate('(mode)=>document.documentElement.dataset.themeMode=mode',mode)
   page.add_style_tag(content='*,*::before,*::after{transition-duration:0s!important;animation-duration:0s!important}')
  def shot(name):
   assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
   page.screenshot(path=str(out/f'{mode}-{name}-1280x800.png'))
  page.goto('http://127.0.0.1:5198/agents');page.locator('input[placeholder*="搜索名称"]').fill('PI');page.get_by_test_id('pi-agent-details').first.wait_for();theme()
  page.get_by_text('安全保护已就绪',exact=True).wait_for()
  assert page.get_by_test_id('pi-agent-details').count()==3
  assert page.get_by_test_id('pi-guard').filter(has_text='存在未受控扩展').count()==1
  assert page.get_by_test_id('pi-agent-details').filter(has_text='安全扩展不可用').count()==1
  assert page.get_by_test_id('pi-agent-details').filter(has_text='1aicode · deepseek/deepseek-v4-pro').count()==3
  shot('agents')
  page.goto('http://127.0.0.1:5198/scenes');page.get_by_role('button',name=re.compile('需求规划')).click();theme()
  page.get_by_role('button',name='planner Agent',exact=True).click();page.get_by_role('option',name='PI (pi)',exact=True).click()
  page.get_by_test_id('pi-role-hint').wait_for()
  assert '继承本机默认模型' in page.get_by_role('button',name='planner 模型',exact=True).inner_text()
  page.get_by_role('button',name='planner 模型',exact=True).click();page.get_by_role('option',name='1aicode · deepseek/deepseek-v4-pro',exact=True).click()
  assert '本机可用，请按需手动选择' in page.get_by_test_id('pi-role-hint').inner_text()
  assert '当前模型：1aicode · deepseek/deepseek-v4-pro' in page.get_by_test_id('pi-role-hint').inner_text()
  shot('roles')
  results.append({'mode':mode,'guardStates':['ready','uncontrolled_extensions','guard_not_loaded'],'providerModel':'1aicode · deepseek/deepseek-v4-pro','recommendationAutoSelected':False,'horizontalOverflow':False})
 assert not errors,errors
 result={'checks':results,'screenshots':len(list(out.glob('*.png'))),'browserErrors':len(errors),'source':'Chromium + synthetic protocol mocks; no model calls'}
 (out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False));browser.close()
