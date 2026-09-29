import os
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path.cwd()
os.environ['TEMP']=os.environ['TMP']=str(root/'.tmp')
out=root/'.hqagent/handoffs/screenshots/r3-p3'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':375,'height':812}, device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e: errors.append(type(e).__name__))
    page.goto('http://127.0.0.1:5198/remote/devices')
    page.get_by_text('Office PC (Alex)',exact=True).wait_for()
    page.evaluate('''async () => {
      const { mockRemoteGateway:g }=await import('/src/shared/api/mock-remote-gateway.ts');
      g.devices[0].supportedWireRevisions=[2,3];
      g.catalog.authorizedRoots=[{rootId:'root_example', displayName:'合成开发目录',version:1}];
    }''')
    page.get_by_text('Office PC (Alex)',exact=True).click()
    page.get_by_role('button',name='打开对话列表').click()
    page.get_by_text('示例：梳理项目结构',exact=True).wait_for()
    page.wait_for_function("new DOMMatrix(getComputedStyle(document.querySelector('aside')).transform).m41 === 0")
    page.screenshot(path=str(out/'native-list-375x812.png'))
    page.get_by_text('示例：梳理项目结构',exact=True).click()
    page.get_by_text('这是用于界面验收的合成会话内容，不来自真实终端历史。',exact=True).wait_for()
    page.get_by_role('button',name='接着对话',exact=True).click()
    page.get_by_text('我已在终端退出该会话',exact=True).wait_for()
    page.screenshot(path=str(out/'native-import-375x812.png'))
    assert page.get_by_role('button',name='确认导入',exact=True).is_disabled()
    page.keyboard.press('Escape')
    page.get_by_role('button',name='新建任务',exact=True).click()
    page.get_by_role('button',name='添加项目',exact=True).click()
    page.get_by_label('授权根目录',exact=True).select_option('root_example')
    page.get_by_role('button',name='示例资料',exact=True).click()
    page.get_by_text('非 Git 仓库只能运行只读任务',exact=True).wait_for()
    page.screenshot(path=str(out/'directory-375x812.png'))
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
    print('mobile native read / unchecked confirmation / directory browsing: PASS')
    page.keyboard.press('Escape')
    page.set_viewport_size({'width':1280,'height':800})
    page.goto('http://127.0.0.1:5198/remote-link')
    page.get_by_test_id('authorized-roots').wait_for()
    page.evaluate('''async () => {
      const {mockLocalChatGateway:g}=await import('/src/shared/api/mock-local-chat-gateway.ts');
      g.authorizedRoots={version:2,roots:[{rootId:'root_example',displayName:'合成开发目录',path:'E:/SyntheticProjects',version:1}]};
    }''')
    page.get_by_test_id('authorized-roots').get_by_role('button',name='刷新',exact=True).click()
    page.get_by_text('E:/SyntheticProjects',exact=True).wait_for()
    page.screenshot(path=str(out/'authorized-roots-1280x800.png'))
    print('desktop authorized roots: PASS')
    page.get_by_role('link',name='本地对话',exact=True).click()
    page.get_by_text('示例：梳理项目结构',exact=True).wait_for()
    page.get_by_text('示例：梳理项目结构',exact=True).click()
    page.get_by_role('button',name='接着对话',exact=True).click()
    page.get_by_role('checkbox',name='我已在终端退出该会话',exact=True).check()
    page.get_by_role('button',name='确认导入',exact=True).click()
    page.get_by_text('已在本机导入，尚未配对手机',exact=True).wait_for()
    page.get_by_text('这是用于界面验收的合成会话内容，不来自真实终端历史。',exact=True).wait_for()
    assert page.evaluate('!JSON.stringify(localStorage).includes("合成会话内容") && !JSON.stringify(sessionStorage).includes("合成会话内容")')
    print('desktop local import, history and in-memory-only content: PASS')
    print('browser errors:',len(errors))
    assert not errors
    print('Screenshots: 3 mobile + 1 desktop; synthetic content only')
    browser.close()
