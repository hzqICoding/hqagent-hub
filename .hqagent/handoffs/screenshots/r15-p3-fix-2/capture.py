import os
from pathlib import Path
from playwright.sync_api import sync_playwright
root = Path.cwd()
os.environ['TEMP'] = os.environ['TMP'] = str(root / '.tmp')
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width':375,'height':812}, device_scale_factor=1)
    page.goto('http://127.0.0.1:5198/remote/devices')
    page.get_by_text('Office PC (Alex)', exact=True).wait_for()
    page.evaluate('''async () => {
      const { mockRemoteGateway: g } = await import('/src/shared/api/mock-remote-gateway.ts');
      g.devices[1].status = 'revoked';
      const { useRemoteChatStore } = await import('/src/stores/remote-chat.store.ts');
      const pinia = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia;
      await useRemoteChatStore(pinia).fetchDevices();
    }''')
    out = root / '.hqagent/handoffs/screenshots/r15-p3-fix-2'
    page.screenshot(path=str(out / 'devices-375x812.png'))
    page.get_by_text('Office PC (Alex)', exact=True).click()
    page.locator('[data-testid=run-status-toggle]').wait_for()
    page.screenshot(path=str(out / 'status-collapsed-375x812.png'))
    print('collapsed overflow:', page.evaluate('document.documentElement.scrollWidth > innerWidth'))
    page.locator('[data-testid=run-status-toggle]').click()
    page.screenshot(path=str(out / 'status-expanded-375x812.png'))
    print('expanded overflow:', page.evaluate('document.documentElement.scrollWidth > innerWidth'))
    page.get_by_role('button', name='打开对话列表').click()
    page.get_by_role('button', name='在Web-Ecommerce新建任务').click()
    page.get_by_role('dialog').wait_for()
    page.screenshot(path=str(out / 'create-task-375x812.png'))
    print('dialog selected workspace:', page.locator('#new-conv-workspace').input_value())
    print('Screenshots: 4 captured at 375x812')
    browser.close()
