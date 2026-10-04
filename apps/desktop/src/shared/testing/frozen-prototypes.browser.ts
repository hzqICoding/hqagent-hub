// Browser-only regression entry. Never imported by the application.
import type { Component } from 'vue'
import type { MessageAttachmentView } from '@hqagent/protocol'

type Report = { prototypesFrozen: boolean; overrideMistakeBlocked: boolean; pages: string[]; components: string[]; qrDecoded: boolean; qrDecodedSizes: number[]; scannerDecoded: boolean; cameraReleased: boolean }
export async function runFrozenPrototypeRegression(): Promise<Report> {
  Object.freeze(Object.prototype); Object.freeze(Function.prototype); Object.freeze(Array.prototype)
  const frozen = () => [Object.prototype, Function.prototype, Array.prototype].every(Object.isFrozen)
  if (!frozen()) throw new Error('Prototypes are not frozen')
  let overrideMistakeBlocked = false
  try { const probe = {}; probe.toString = () => 'unsafe override' } catch { overrideMistakeBlocked = true }
  if (!overrideMistakeBlocked) throw new Error('Override-mistake regression control did not throw')

  await import('@/shared/theme/index.css')

  // All runtime imports happen after freezing, including Vue and its actual production dependencies.
  const { createApp, h, nextTick } = await import('vue')
  const { createPinia, setActivePinia } = await import('pinia')
  const { createMemoryHistory, createRouter } = await import('vue-router')
  const { i18n } = await import('@/shared/i18n')
  const { default: App } = await import('@/App.vue')
  const api = await import('@/shared/api')
  api.setLocalChatGatewayMode('mock'); api.mockLocalChatGateway.reset(); api.mockGateway.setDelay(0)
  const pinia = createPinia(); setActivePinia(pinia)
  const report: Report = { prototypesFrozen: true, overrideMistakeBlocked, pages: [], components: [], qrDecoded: false, qrDecodedSizes: [], scannerDecoded: false, cameraReleased: false }
  const errors: unknown[] = []
  async function until(check: () => boolean, label: string) {
    const deadline = Date.now() + 12000
    while (!check()) {
      if (errors.length) throw errors[0]
      if (Date.now() > deadline) throw new Error(`Frozen render timed out: ${label}; scanner=${document.querySelector('[aria-labelledby=pairing-scan-title]')?.textContent || 'absent'}; video=${document.querySelector('video')?.readyState}`)
      await new Promise(resolve => setTimeout(resolve, 25)); await nextTick()
    }
    if (errors.length) throw errors[0]
  }
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/', component: { render: () => h('p', '冻结原型回归') } },
    { path: '/chat', component: () => import('@/pages/chat/ChatPage.vue') },
    { path: '/remote-link', component: () => import('@/pages/remote-link/RemoteLinkPage.vue') },
    { path: '/agents', component: () => import('@/pages/agents/AgentsPage.vue') },
    { path: '/scenes', component: () => import('@/pages/scenes/ScenesPage.vue') },
    { path: '/remote/pair', component: () => import('@/pages/remote/RemotePairingPage.vue') },
  ] })
  router.onError(error => errors.push(error))
  const host = document.createElement('div'); host.id = 'app'; document.body.append(host)
  const app = createApp(App)
  app.config.errorHandler = error => errors.push(error)
  app.use(pinia); app.use(router); app.use(i18n)
  await router.push('/'); await router.isReady(); app.mount(host)
  const temporaryApps: ReturnType<typeof createApp>[] = []
  const temporaryHosts: HTMLElement[] = []
  const frame = document.createElement('canvas'); frame.width = frame.height = 200
  let stream: MediaStream | undefined
  let frameTimer: ReturnType<typeof setInterval> | undefined
  try {
    await router.push('/chat'); await until(() => Boolean(host.querySelector('textarea')), 'ChatPage')
    report.pages.push('ChatPage')
    // Exercise the navigation that failed in WebView2: lazy chunk import after ChatPage has rendered.
    const linkState = { state: 'pairing' as const, serverOrigin: location.origin, deviceName: '冻结原型验收', pairRequestId: 'synthetic_pairing', pairCode: 'ABCD2345', expiresAt: new Date(Date.now()+300000).toISOString() }
    api.mockLocalChatGateway.setRemoteLinkState(linkState)
    const connect = [...host.querySelectorAll<HTMLButtonElement>('button')].find(button => button.textContent?.includes('连接手机'))
    if (!connect) throw new Error('Connect-phone navigation entry missing')
    connect.click()
    await until(() => Boolean(host.querySelector<HTMLImageElement>('[data-testid=pair-qrcode]')?.complete && host.querySelector<HTMLImageElement>('[data-testid=pair-qrcode]')?.naturalWidth), 'RemoteLinkPage QR')
    report.pages.push('RemoteLinkPage')
    const qr = host.querySelector<HTMLImageElement>('[data-testid=pair-qrcode]')!
    const ctx = frame.getContext('2d', { willReadFrequently: true })!
    const jsQR = (await import('jsqr')).default
    const expected = `${location.origin}/remote/pair#code=${linkState.pairCode}`
    for (const size of [140,168,200]) {
      frame.width = frame.height = size; ctx.drawImage(qr,0,0,size,size)
      const pixels = ctx.getImageData(0,0,size,size)
      if (jsQR(pixels.data,size,size)?.data !== expected) throw new Error(`QR decode failed at ${size}px`)
      report.qrDecodedSizes.push(size)
    }
    const pixels = ctx.getImageData(0,0,200,200)
    report.qrDecoded = qr.naturalWidth === 200 && qr.naturalHeight === 200
    if (!report.qrDecoded || qr.getAttribute('width') !== '200' || qr.getAttribute('height') !== '200') throw new Error('QR payload/dimensions changed')
    await api.mockLocalChatGateway.cancelRemotePairing()
    const { useRemoteLinkStore } = await import('@/stores/remote-link.store')
    await useRemoteLinkStore(pinia).refreshLink(); await nextTick()
    if (host.querySelector('[data-testid=pair-qrcode]')) throw new Error('Cancelled pairing retained QR')
    await router.push('/agents'); await until(() => Boolean(host.querySelector('[data-testid=pi-agent-details]')), 'AgentsPage'); report.pages.push('AgentsPage')
    await router.push('/scenes'); await until(() => Boolean(host.querySelector('[data-role-id]')), 'ScenesPage'); report.pages.push('ScenesPage')
    await router.push('/remote/pair'); await until(() => Boolean(host.querySelector('#pair-code')), 'RemotePairingPage'); report.pages.push('RemotePairingPage')

    async function render(name: string, component: Component, props: Record<string, unknown>, check: (root: HTMLElement) => boolean) {
      const root = document.createElement('div'); document.body.append(root); temporaryHosts.push(root)
      const instance = createApp(component, props); instance.config.errorHandler = error => errors.push(error)
      instance.use(pinia); instance.use(router); instance.use(i18n); instance.mount(root); temporaryApps.push(instance)
      await until(() => check(root), name); report.components.push(name)
      return instance
    }
    const draft = (await import('@/shared/attachments/AttachmentDrafts.vue')).default
    await render('AttachmentDrafts',draft,{conversationId:'synthetic_conversation'},root=>Boolean(root.querySelector('[data-testid=attachment-drafts]')))
    const attachment: MessageAttachmentView = {attachmentId:'synthetic_attachment',fileName:'合成附件.txt',kind:'file',mimeType:'text/plain',sizeBytes:4,sha256:'a'.repeat(64),availability:'pending_upload',thumbnailStatus:'not_applicable'}
    await render('AttachmentItem',(await import('@/shared/attachments/AttachmentItem.vue')).default,{attachment,remote:true},root=>Boolean(root.textContent?.includes('合成附件.txt')))
    await render('MessageAttachments',(await import('@/shared/attachments/MessageAttachments.vue')).default,{attachments:[attachment],remote:true},root=>Boolean(root.querySelector('[aria-label=消息附件]')))
    await render('ImageVerificationPanel',(await import('@/pages/agents/ImageVerificationPanel.vue')).default,{},root=>Boolean(root.querySelector('[data-testid=verification-row]')))
    await render('NativeSessionsPanel',(await import('@/pages/native/NativeSessionsPanel.vue')).default,{projects:[]},root=>Boolean(root.querySelector('[data-testid=native-readable]')))

    // Synthetic canvas stream exercises the actual lazy jsqr fallback under frozen prototypes.
    // No hardware camera, real pairing code, model call or confirmation is used.
    stream = frame.captureStream(8)
    frameTimer = setInterval(() => ctx.putImageData(pixels,0,0),125)
    Object.defineProperty(navigator, 'mediaDevices', {configurable:true,value:{getUserMedia:async()=>stream}})
    Object.defineProperty(window, 'BarcodeDetector', {configurable:true,value:undefined})
    let decoded = ''
    await render('PairingScanner',(await import('@/pages/remote/PairingScanner.vue')).default,{onDecoded:(code:string)=>{decoded=code}},()=>Boolean(document.querySelector('video')))
    await until(()=>Boolean(decoded),'PairingScanner decoding')
    report.scannerDecoded = decoded === linkState.pairCode
    report.cameraReleased = stream.getTracks().every(track=>track.readyState==='ended')
    if (!report.scannerDecoded || !report.cameraReleased) throw new Error('Frozen scanner decode/release failed')
    if (!frozen()) throw new Error('Application changed freeze state')
    return report
  } finally {
    for (const instance of temporaryApps.reverse()) instance.unmount()
    for (const root of temporaryHosts) root.remove()
    clearInterval(frameTimer)
    stream?.getTracks().forEach(track=>track.stop()); frame.remove()
    app.unmount(); host.remove()
  }
}
