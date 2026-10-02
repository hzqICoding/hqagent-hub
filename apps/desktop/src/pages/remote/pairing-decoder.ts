// Browser API compatibility shapes; these are not HTTP/Worker protocol DTOs.
interface QrDetector { detect(source: HTMLCanvasElement): Promise<{ rawValue: string }[]> }
interface QrDetectorConstructor {
  new(options: { formats: string[] }): QrDetector
  getSupportedFormats(): Promise<string[]>
}

/** One decoder per camera view; pixels remain in a bounded in-memory canvas. */
export async function createPairingDecoder() {
  let native: QrDetector | undefined
  const Detector = (globalThis as typeof globalThis & { BarcodeDetector?: QrDetectorConstructor }).BarcodeDetector
  if (Detector?.getSupportedFormats) {
    try {
      if ((await Detector.getSupportedFormats()).includes('qr_code')) native = new Detector({ formats: ['qr_code'] })
    } catch { /* Fall back to the explicitly lazy decoder. */ }
  }
  let decode: typeof import('jsqr').default | undefined
  let disposed = false
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) throw new Error('QR_CANVAS_UNAVAILABLE')
  async function fallback() {
    if (!decode) decode = (await import('jsqr')).default
  }
  // Import only on opening a scanner without a usable native QR detector.
  if (!native) await fallback()
  return {
    async read(video: HTMLVideoElement): Promise<string | null> {
      if (disposed || !video.videoWidth || !video.videoHeight || video.readyState < 2) return null
      const scale = Math.min(1, 640 / Math.max(video.videoWidth, video.videoHeight))
      canvas.width = Math.max(1, Math.round(video.videoWidth * scale))
      canvas.height = Math.max(1, Math.round(video.videoHeight * scale))
      context!.drawImage(video, 0, 0, canvas.width, canvas.height)
      if (native) {
        try {
          const results = await native.detect(canvas)
          return disposed ? null : results.find((result) => typeof result.rawValue === 'string')?.rawValue || null
        } catch { if (disposed) return null; native = undefined; await fallback() }
      }
      if (disposed) return null
      const frame = context!.getImageData(0, 0, canvas.width, canvas.height)
      return decode!(frame.data, frame.width, frame.height, { inversionAttempts: 'dontInvert' })?.data || null
    },
    dispose() { disposed = true; native = undefined; decode = undefined; canvas.width = 0; canvas.height = 0 },
  }
}
