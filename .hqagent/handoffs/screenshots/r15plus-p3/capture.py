import os
from pathlib import Path
from playwright.sync_api import sync_playwright
root = Path.cwd()
os.environ['TEMP'] = os.environ['TMP'] = str(root / '.tmp')
out = root / '.hqagent/handoffs/screenshots/r15plus-p3'
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 375, 'height': 812}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(type(error).__name__))
    page.goto('http://127.0.0.1:5198/remote/devices')
    page.get_by_text('Office PC (Alex)', exact=True).wait_for()
    page.get_by_role('button', name='Office PC (Alex)的更多操作').click()
    page.get_by_role('button', name='暂停远程', exact=True).wait_for()
    page.screenshot(path=str(out / 'device-menu-375x812.png'))
    page.get_by_role('button', name='暂停远程', exact=True).click()
    page.get_by_role('button', name='恢复远程', exact=True).wait_for()
    page.keyboard.press('Escape')
    page.get_by_text('Office PC (Alex)', exact=True).click()
    page.get_by_text('这台电脑的远程操作已暂停', exact=True).wait_for()
    page.screenshot(path=str(out / 'suspended-chat-375x812.png'))
    print('suspended chat overflow:', page.evaluate('document.documentElement.scrollWidth > innerWidth'))
    page.evaluate('''async () => {
      const { mockRemoteGateway: g } = await import('/src/shared/api/mock-remote-gateway.ts');
      g.apiTokens = [{tokenId:'pat_000000000000000000000000', name:'部署检查工具', tokenPrefix:'hqr_pat_000000000000000000000000',
        scopes:['devices:read'], createdAt:'2026-09-28T00:00:00Z', expiresAt:'2026-12-27T00:00:00Z', status:'active'}];
      const { router } = await import('/src/app/router/index.ts');
      await router.push('/remote/tokens');
    }''')
    page.get_by_text('部署检查工具', exact=True).wait_for()
    page.screenshot(path=str(out / 'token-list-375x812.png'))
    page.get_by_role('button', name='新建令牌', exact=True).click()
    page.get_by_label('令牌名称').fill('示例令牌（不可用于认证）')
    page.get_by_role('checkbox', name='devices:read', exact=True).check()
    page.get_by_role('button', name='签发令牌', exact=True).click()
    page.get_by_text('关闭后无法再次查看', exact=True).wait_for()
    page.screenshot(path=str(out / 'token-issued-example-375x812.png'))
    # Assert cleanup in the browser without writing the example secret to output.
    secret = page.locator('[data-testid="issued-secret"]').inner_text()
    page.get_by_role('button', name='关闭', exact=True).click()
    assert page.locator('[data-testid="issued-secret"]').count() == 0
    assert secret not in page.locator('body').inner_text()
    assert page.evaluate('!JSON.stringify(localStorage).includes("hqr_pat_") && !JSON.stringify(sessionStorage).includes("hqr_pat_")')
    print('dialog close and storage cleanup: PASS')
    print('token page overflow:', page.evaluate('document.documentElement.scrollWidth > innerWidth'))
    page.evaluate("""async () => {
      const { mockRemoteGateway: g } = await import('/src/shared/api/mock-remote-gateway.ts');
      const sample = g.apiTokens[0];
      g.apiTokens = Array.from({length:60}, (_, i) => ({...sample,
        tokenId:'pat_' + i.toString(16).padStart(24,'0'),
        tokenPrefix:'hqr_pat_' + i.toString(16).padStart(24,'0'), name:'分页示例 ' + i}));
    }""")
    page.get_by_role('checkbox', name='显示已吊销', exact=True).check()
    page.get_by_text('分页示例 0', exact=True).wait_for()
    assert page.locator('main').evaluate('(el) => el.scrollHeight > el.clientHeight')
    page.get_by_role('button', name='加载更多', exact=True).click()
    page.get_by_text('分页示例 59', exact=True).wait_for()
    assert page.locator('article').count() == 60
    print('60-token scrolling and pagination: PASS')
    print('page errors:', len(errors))
    assert not errors
    print('Screenshots: 4 captured at 375x812; token is a non-authenticating example')
    browser.close()
