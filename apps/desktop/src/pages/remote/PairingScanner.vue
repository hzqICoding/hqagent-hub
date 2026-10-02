<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { X, ScanLine } from 'lucide-vue-next'
import { parsePairingQr } from './pairing-qr'
import { createPairingDecoder } from './pairing-decoder'

const emit = defineEmits<{ close: []; decoded: [code: string] }>()
const video = ref<HTMLVideoElement | null>(null)
const dialog = ref<HTMLElement | null>(null)
let previousFocus: HTMLElement | null = null
const closeButton = ref<HTMLButtonElement | null>(null)
const starting = ref(false)
const running = ref(false)
const message = ref('')
const fatal = ref(false)
let stream: MediaStream | undefined
let decoder: Awaited<ReturnType<typeof createPairingDecoder>> | undefined
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0
let mounted = true
let previousOverflow = ''
const help = '可改用系统相机扫码，或关闭后手动输入配对码。'
function stop() {
  generation++
  clearTimeout(timer); timer = undefined
  decoder?.dispose(); decoder = undefined
  stream?.getTracks().forEach((track) => track.stop()); stream = undefined
  if (video.value) { video.value.pause(); video.value.srcObject = null }
  running.value = false; starting.value = false
}
function close() { stop(); emit('close') }
function unavailable(text: string) { stop(); fatal.value = true; message.value = text }
function cameraFailure(error: unknown): string {
  const name = (error as { name?: string })?.name
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError') return '摄像头权限被拒绝，请在浏览器设置中允许访问摄像头。'
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') return '没有找到可用摄像头。'
  if (name === 'NotReadableError' || name === 'TrackStartError') return '摄像头被其他应用占用或暂时无法读取，请关闭其他扫码应用后重试。'
  if (name === 'SecurityError') return '当前浏览器的安全设置不允许访问摄像头。'
  return '当前浏览器无法启动扫码。微信等内置浏览器可尝试在系统浏览器中打开本页面。'
}
async function scan(current: number) {
  if (!mounted || current !== generation || !running.value || !video.value || !decoder) return
  try {
    const result = await decoder.read(video.value)
    if (!mounted || current !== generation) return
    if (result) {
      const code = parsePairingQr(result, window.location.origin)
      if (code) { stop(); emit('decoded', code); return }
      message.value = '不是本服务的配对二维码'
    }
  } catch {
    if (mounted && current === generation) unavailable('当前浏览器无法读取扫码画面，请重试或在系统浏览器中打开。')
    return
  }
  // Serial decode plus a >=125ms pause: at most 8 frames/s, no overlapping reads.
  if (mounted && current === generation) timer = setTimeout(() => { void scan(current) }, 125)
}
async function start() {
  if (starting.value || running.value) return
  stop(); fatal.value = false; message.value = ''
  if (!window.isSecureContext) { unavailable('网页扫码需要 HTTPS 安全连接，请通过本服务的 HTTPS 地址打开。'); return }
  if (!navigator.mediaDevices?.getUserMedia) { unavailable('当前浏览器不支持网页摄像头扫码。微信等内置浏览器可尝试在系统浏览器中打开本页面。'); return }
  const current = generation
  starting.value = true
  try {
    const nextStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
    if (!mounted || current !== generation) { nextStream.getTracks().forEach((track) => track.stop()); return }
    stream = nextStream
    if (!video.value) { stop(); return }
    video.value.srcObject = stream
    await video.value.play()
    if (!mounted || current !== generation) return
    const nextDecoder = await createPairingDecoder()
    if (!mounted || current !== generation) { nextDecoder.dispose(); return }
    decoder = nextDecoder
    stream.getVideoTracks().forEach((track) => track.addEventListener('ended', () => {
      if (mounted && current === generation) unavailable('摄像头已停止，请重新开启扫码。')
    }, { once: true }))
    starting.value = false; running.value = true
    timer = setTimeout(() => { void scan(current) }, 125)
  } catch (err) { if (mounted && current === generation) unavailable(cameraFailure(err)) }
}
function onKey(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); close(); return }
  if (event.key !== 'Tab') return
  const buttons = dialog.value?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')
  if (!buttons?.length) return
  const first = buttons[0], last = buttons[buttons.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
function onHidden() { if (document.hidden) unavailable('页面已切到后台，摄像头已释放。返回后请重新开启扫码。') }
onMounted(() => {
  previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  previousOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden'
  document.addEventListener('keydown', onKey); document.addEventListener('visibilitychange', onHidden)
  closeButton.value?.focus()
  void start()
})
onBeforeUnmount(() => {
  mounted = false; stop(); document.body.style.overflow = previousOverflow
  document.removeEventListener('keydown', onKey); document.removeEventListener('visibilitychange', onHidden)
  if (previousFocus?.isConnected) previousFocus.focus()
})
</script>

<template>
  <Teleport to="body">
    <section ref="dialog" role="dialog" aria-modal="true" aria-labelledby="pairing-scan-title" class="fixed inset-0 z-[100] h-dvh bg-app text-content-primary flex flex-col">
      <header class="shrink-0 flex items-center justify-between gap-3 border-b border-border px-4 py-2 bg-panel">
        <h2 id="pairing-scan-title" class="font-semibold flex items-center gap-2"><ScanLine class="w-5 h-5" />扫码配对</h2>
        <button ref="closeButton" type="button" aria-label="关闭扫码" class="min-w-[44px] min-h-[44px] flex items-center justify-center rounded-lg hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring" @click="close"><X class="w-5 h-5" /></button>
      </header>
      <div class="flex-1 min-h-0 relative overflow-hidden bg-code flex items-center justify-center">
        <video ref="video" autoplay muted playsinline class="w-full h-full object-contain" aria-label="摄像头扫码画面" />
        <div v-if="running" aria-hidden="true" class="absolute w-56 h-56 max-w-[70vw] border-2 border-primary rounded-2xl pointer-events-none" />
      </div>
      <div class="shrink-0 space-y-3 p-4 pb-[max(1rem,env(safe-area-inset-bottom))] bg-panel border-t border-border text-sm">
        <p v-if="starting" role="status">正在请求摄像头权限…</p>
        <p v-else-if="running" role="status">请对准电脑「连接手机」上的配对二维码</p>
        <p v-if="message" role="alert" class="text-status-danger">{{ message }}</p>
        <p class="text-content-secondary">识别后只获取设备预览，不会自动确认绑定。{{ help }}</p>
        <button v-if="fatal" type="button" class="min-h-[44px] px-4 rounded-lg border border-border text-content-primary hover:bg-muted" @click="start">重新开启扫码</button>
      </div>
    </section>
  </Teleport>
</template>
