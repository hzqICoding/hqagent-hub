import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import PairingScanner from './PairingScanner.vue'
import RemotePairingPage from './RemotePairingPage.vue'
import { createPairingDecoder } from './pairing-decoder'
import { MockRemoteGateway } from '@/shared/api/mock-remote-gateway'
import { setRemoteGatewayForTesting } from '@/shared/api/remote-provider'

const { jsDecode } = vi.hoisted(() => ({ jsDecode: vi.fn() }))
vi.mock('jsqr', () => ({ default: jsDecode }))
let detect: ReturnType<typeof vi.fn>
let gum: ReturnType<typeof vi.fn>
let stop: ReturnType<typeof vi.fn>
let draw: ReturnType<typeof vi.fn>
let media: MediaStream
const options = { global: { stubs: { Teleport: true } } }
function readyVideo() { return document.createElement('video') }
beforeEach(() => {
  setActivePinia(createPinia()); localStorage.clear(); sessionStorage.clear()
  window.history.replaceState(null, '', '/remote/pair')
  vi.stubGlobal('isSecureContext', true)
  stop = vi.fn()
  const track = { stop, addEventListener: vi.fn() }
  media = { getTracks: () => [track], getVideoTracks: () => [track] } as unknown as MediaStream
  gum = vi.fn().mockResolvedValue(media)
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: gum } })
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
  vi.spyOn(HTMLMediaElement.prototype, 'readyState', 'get').mockReturnValue(2)
  vi.spyOn(HTMLVideoElement.prototype, 'videoWidth', 'get').mockReturnValue(1920)
  vi.spyOn(HTMLVideoElement.prototype, 'videoHeight', 'get').mockReturnValue(1080)
  draw = vi.fn()
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: draw, getImageData: (_x: number, _y: number, width: number, height: number) => ({ data: new Uint8ClampedArray(4), width, height }) } as unknown as CanvasRenderingContext2D)
  detect = vi.fn().mockResolvedValue([])
  vi.stubGlobal('BarcodeDetector', class {
    static getSupportedFormats = vi.fn().mockResolvedValue(['qr_code'])
    detect = detect
  })
  jsDecode.mockReset()
})
afterEach(() => { setRemoteGatewayForTesting(null); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })
enableAutoUnmount(afterEach)

describe('in-page pairing scanner', () => {
  it('prefers the native QR detector, downsamples, stops tracks and emits only a code', async () => {
    vi.useFakeTimers()
    detect.mockResolvedValue([{ rawValue: `${window.location.origin}/remote/pair#code=ABCD1234` }])
    const wrapper = mount(PairingScanner, options); await flushPromises()
    expect(gum).toHaveBeenCalledWith({ video: { facingMode: 'environment' } })
    await vi.advanceTimersByTimeAsync(125)
    expect(wrapper.emitted('decoded')).toEqual([['ABCD1234']])
    expect(stop).toHaveBeenCalledTimes(1)
    expect(draw.mock.calls[0].slice(-2)).toEqual([640, 360])
    expect(jsDecode).not.toHaveBeenCalled()
    expect(wrapper.get('video').element.srcObject ?? null).toBeNull()
    expect(JSON.stringify(localStorage)).not.toContain('ABCD1234'); expect(JSON.stringify(sessionStorage)).not.toContain('ABCD1234')
    expect(window.location.href).not.toContain('ABCD1234')
  })
  it('rejects external links with a fixed warning and never emits or navigates', async () => {
    vi.useFakeTimers()
    detect.mockResolvedValue([{ rawValue: 'https://outside.invalid/remote/pair#code=ABCD1234' }])
    const before = window.location.href
    const wrapper = mount(PairingScanner, options); await flushPromises(); await vi.advanceTimersByTimeAsync(125)
    expect(wrapper.text()).toContain('不是本服务的配对二维码')
    expect(wrapper.text()).not.toContain('outside.invalid')
    expect(wrapper.emitted('decoded')).toBeUndefined(); expect(window.location.href).toBe(before)
    await wrapper.get('[aria-label="关闭扫码"]').trigger('click')
    expect(stop).toHaveBeenCalledTimes(1)
  })
  it('fills the parent input and previews successfully without automatically binding', async () => {
    const gateway = new MockRemoteGateway(); gateway.reset(); setRemoteGatewayForTesting(gateway)
    const preview = vi.spyOn(gateway, 'previewPairing'), confirm = vi.spyOn(gateway, 'confirmPairing')
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/remote/pair', component: RemotePairingPage }] })
    await router.push('/remote/pair')
    detect.mockResolvedValue([{ rawValue: `${window.location.origin}/remote/pair#code=ABCD1234` }])
    const wrapper = mount(RemotePairingPage, { global: { plugins: [router], stubs: { Teleport: true } } })
    await wrapper.findAll('button').find((button) => button.text() === '扫码')!.trigger('click')
    await vi.waitFor(() => expect(preview).toHaveBeenCalledWith({ pairCode: 'ABCD1234' }))
    await flushPromises()
    expect((wrapper.get('#pair-code').element as HTMLInputElement).value).toBe('ABCD1234')
    expect(wrapper.text()).toContain('待绑定'); expect(confirm).not.toHaveBeenCalled()
    expect(wrapper.find('[aria-label="关闭扫码"]').exists()).toBe(false)
    expect(stop).toHaveBeenCalledTimes(1)
  })
  it.each([
    ['NotAllowedError', '摄像头权限被拒绝'], ['NotFoundError', '没有找到可用摄像头'],
    ['NotReadableError', '摄像头被其他应用占用'], ['SecurityError', '安全设置不允许访问摄像头'],
  ])('reports %s with system-camera and manual alternatives', async (name, text) => {
    gum.mockRejectedValue(new DOMException('synthetic', name))
    const wrapper = mount(PairingScanner, options); await flushPromises()
    expect(wrapper.text()).toContain(text); expect(wrapper.text()).toContain('系统相机扫码'); expect(wrapper.text()).toContain('手动输入配对码')
  })
  it('does not request a camera in an insecure context', async () => {
    vi.stubGlobal('isSecureContext', false)
    const wrapper = mount(PairingScanner, options); await flushPromises()
    expect(wrapper.text()).toContain('HTTPS'); expect(gum).not.toHaveBeenCalled()
  })
  it('explains unsupported webviews without trying an absent API', async () => {
    vi.stubGlobal('navigator', {})
    const wrapper = mount(PairingScanner, options); await flushPromises()
    expect(wrapper.text()).toContain('当前浏览器不支持'); expect(wrapper.text()).toContain('微信')
    expect(gum).not.toHaveBeenCalled()
  })
  it('stops on route/component unmount and ignores a late permission result', async () => {
    let resolve!: (stream: MediaStream) => void
    gum.mockImplementation(() => new Promise((done) => { resolve = done }))
    const wrapper = mount(PairingScanner, options); await flushPromises(); wrapper.unmount()
    resolve(media); await flushPromises()
    expect(stop).toHaveBeenCalledTimes(1); expect(detect).not.toHaveBeenCalled()
  })
  it('stops all tracks and timers when closed during decoding, ignoring its late result', async () => {
    vi.useFakeTimers()
    let resolve!: (result: {rawValue: string}[]) => void
    detect.mockImplementation(() => new Promise((done) => { resolve = done }))
    const wrapper = mount(PairingScanner, options); await flushPromises(); await vi.advanceTimersByTimeAsync(125)
    await wrapper.get('[aria-label="关闭扫码"]').trigger('click')
    resolve([{rawValue:'ABCD1234'}]); await flushPromises(); await vi.advanceTimersByTimeAsync(1000)
    expect(stop).toHaveBeenCalledTimes(1); expect(wrapper.emitted('decoded')).toBeUndefined(); expect(detect).toHaveBeenCalledTimes(1)
  })
  it('limits decoding to eight attempts per second and stops on unmount', async () => {
    vi.useFakeTimers()
    const wrapper = mount(PairingScanner, options); await flushPromises(); await vi.advanceTimersByTimeAsync(1000)
    expect(detect.mock.calls.length).toBeLessThanOrEqual(8)
    wrapper.unmount(); await vi.advanceTimersByTimeAsync(1000)
    expect(detect.mock.calls.length).toBeLessThanOrEqual(8); expect(stop).toHaveBeenCalledTimes(1)
  })
  it('releases the camera when the page goes into the background', async () => {
    const wrapper = mount(PairingScanner, options); await flushPromises()
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
    document.dispatchEvent(new Event('visibilitychange'))
    expect(stop).toHaveBeenCalledTimes(1)
    await flushPromises(); expect(wrapper.text()).toContain('摄像头已释放')
  })
})

describe('lazy decoder fallback', () => {
  it.each([false, true])('uses jsqr only when native QR support is absent (%s)', async (hasDetector) => {
    if (!hasDetector) vi.stubGlobal('BarcodeDetector', undefined)
    else vi.stubGlobal('BarcodeDetector', class { static getSupportedFormats = async () => ['ean_13'] })
    jsDecode.mockReturnValue({ data: 'ABCD1234' })
    const decoder = await createPairingDecoder()
    expect(await decoder.read(readyVideo())).toBe('ABCD1234')
    expect(jsDecode.mock.calls[0].slice(1, 3)).toEqual([640, 360])
    decoder.dispose(); expect(await decoder.read(readyVideo())).toBeNull()
  })
  it('falls back when a native implementation rejects camera frames', async () => {
    detect.mockRejectedValue(new Error('not supported'))
    jsDecode.mockReturnValue({ data: 'ABCD1234' })
    const decoder = await createPairingDecoder(); expect(await decoder.read(readyVideo())).toBe('ABCD1234')
    decoder.dispose()
  })
})
