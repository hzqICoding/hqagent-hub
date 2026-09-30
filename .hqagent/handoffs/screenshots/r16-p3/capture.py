import os, base64
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path.cwd()
os.environ['TEMP']=os.environ['TMP']=str(root/'.tmp')
out=root/'.hqagent/handoffs/screenshots/r16-p3'
png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9l8AAAAASUVORK5CYII=')
files=[{'name':'synthetic.png','mimeType':'image/png','buffer':png},{'name':'example.txt','mimeType':'text/plain','buffer':b'Synthetic attachment for UI verification only.'}]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':375,'height':812},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(type(e).__name__))
    page.goto('http://127.0.0.1:5198/remote/devices')
    page.get_by_text('Office PC (Alex)',exact=True).wait_for()
    page.evaluate('''async () => {
      const {mockRemoteGateway:g}=await import('/src/shared/api/mock-remote-gateway.ts');
      g.runs=[]; g.approvals=[]; g.commands=[]; g.devices[0].supportedWireRevisions=[2,3,4];
      g.catalog.scenes[0].roleImageCapabilities=[{roleId:'analyst',agentId:'synthetic',imageInput:{support:'supported',cliEntry:'supported',runtimeImplemented:true,verified:true,mimeTypes:['image/png'],maxBytes:10000000}}];
    }''')
    page.get_by_text('Office PC (Alex)',exact=True).click()
    page.get_by_role('button',name='添加附件',exact=True).click()
    page.locator('[data-testid=select-files]').set_input_files(files)
    page.wait_for_function("[...document.querySelectorAll('[data-testid=attachment-status]')].filter(e=>e.textContent==='已上传').length===2")
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
    assert page.get_by_role('button',name='添加附件',exact=True).bounding_box()['width']>=44
    page.screenshot(path=str(out/'mobile-drafts-375x812.png'))
    page.locator('textarea').fill('请检查合成附件')
    page.get_by_role('button',name='发送消息',exact=True).click()
    page.wait_for_function("document.querySelectorAll('[data-testid=attachment-status]').length===0")
    page.evaluate('''async () => {
      const {mockRemoteGateway:g}=await import('/src/shared/api/mock-remote-gateway.ts');
      const message=g.messages.find(m=>m.text==='请检查合成附件');
      const image=message.attachments.find(a=>a.kind==='image');
      image.thumbnailStatus='ready'; g.attachmentLibrary.get(image.attachmentId).remote.attachment.thumbnailStatus='ready';
      message.attachments.push({...image,attachmentId:'example_pending',fileName:'pending.png',availability:'pending_upload',thumbnailStatus:'pending'});
      message.attachments.push({...image,attachmentId:'example_unavailable',fileName:'unavailable.png',availability:'unavailable',thumbnailStatus:'unavailable',errorCode:'ATTACHMENT_DOWNLOAD_FAILED'});
      message.messageRevision=(message.messageRevision||1)+1;
      const {useRemoteChatStore}=await import('/src/stores/remote-chat.store.ts');
      const pinia=document.querySelector('#app').__vue_app__.config.globalProperties.$pinia;
      await useRemoteChatStore(pinia).loadInitialMessages('conversation_demo');
    }''')
    page.get_by_text('附件待上传',exact=True).wait_for()
    page.wait_for_function("document.querySelector('img[src^=\"blob:\"]')?.complete")
    assert page.locator('img[src^="blob:"]').first.evaluate('(el)=>el.naturalWidth>0')
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
    assert page.locator('[data-testid=message-attachment]').first.evaluate('(el)=>getComputedStyle(el).color!==getComputedStyle(el).backgroundColor')
    page.screenshot(path=str(out/'mobile-messages-375x812.png'))
    page.evaluate('document.documentElement.dataset.themeMode="dark"')
    page.screenshot(path=str(out/'mobile-messages-dark-375x812.png'))
    page.evaluate('document.documentElement.dataset.themeMode="light"')
    page.evaluate('''async () => {
      const {useRemoteChatStore}=await import('/src/stores/remote-chat.store.ts');
      const pinia=document.querySelector('#app').__vue_app__.config.globalProperties.$pinia;
      useRemoteChatStore(pinia).devices[0].remoteAccess='suspended';
    }''')
    assert page.get_by_role('button',name='添加附件',exact=True).is_disabled()
    assert page.get_by_role('button',name='下载 example.txt',exact=True).is_enabled()
    print('mobile selection, statuses, suspended download, 44px target, no horizontal overflow: PASS')
    page.set_viewport_size({'width':1280,'height':800})
    page.goto('http://127.0.0.1:5198/chat')
    page.get_by_role('button',name='添加附件',exact=True).wait_for()
    conv=page.evaluate('''async () => {
      const {mockLocalChatGateway:g}=await import('/src/shared/api/mock-local-chat-gateway.ts');
      const c=await g.createLocalConversation({title:'合成本机附件验收',workspaceId:(await g.listLocalWorkspaces())[0].id,sceneId:'analyze'});
      g.attachmentLibrary.capabilities={conversationKind:'scenario',capabilityRevision:1,roles:[{roleId:'analyst',agentId:'mock',imageInput:{support:'supported',cliEntry:'supported',runtimeImplemented:true,verified:true,mimeTypes:['image/png'],maxBytes:10000000}}]};
      const {useChatStore}=await import('/src/stores/chat.store.ts');
      const store=useChatStore(document.querySelector('#app').__vue_app__.config.globalProperties.$pinia);
      await store.fetchConversations(); await store.selectConversation(c.id); return c.id;
    }''')
    page.get_by_role('button',name='添加附件',exact=True).click()
    page.locator('[data-testid=select-files]').set_input_files(files)
    page.wait_for_function("[...document.querySelectorAll('[data-testid=attachment-status]')].filter(e=>e.textContent==='已上传').length===2")
    page.screenshot(path=str(out/'desktop-drafts-1280x800.png'))
    page.evaluate('''async () => {
      const {mockLocalChatGateway:g}=await import('/src/shared/api/mock-local-chat-gateway.ts');
      for(const r of g.attachmentLibrary.records.values()) { r.local.syncStatus=r.local.attachment.kind==='image'?'available':'unavailable'; if(r.local.syncStatus==='unavailable')r.local.syncError='ATTACHMENT_QUOTA_EXCEEDED'; r.remote.attachment.thumbnailStatus='ready'; }
    }''')
    page.locator('textarea').fill('请检查本机合成附件')
    page.get_by_role('button',name='发送目标指令',exact=True).click()
    page.get_by_text('本机可用 · 同步失败',exact=True).wait_for()
    assert page.get_by_role('button',name='下载 example.txt',exact=True).is_enabled()
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
    page.screenshot(path=str(out/'desktop-messages-1280x800.png'))
    assert page.evaluate('!JSON.stringify(localStorage).includes("blob:") && !JSON.stringify(sessionStorage).includes("blob:") && !JSON.stringify(sessionStorage).includes("请检查本机合成附件")')
    print('desktop input, independent sync failure, local download and storage checks: PASS')
    print('browser errors:',len(errors)); assert not errors
    print('5 screenshots captured using synthetic attachments only')
    browser.close()
