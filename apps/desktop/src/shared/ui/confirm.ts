import { createVNode, render, getCurrentScope, onScopeDispose } from 'vue'
import HqConfirmDialog from './HqConfirmDialog.vue'

export interface ConfirmOptions {
  title: string
  description?: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
  signal?: AbortSignal
}
interface Request { options: ConfirmOptions; settle: (value: boolean) => void; cleanup?: () => void; host?: HTMLElement }
const queue: Request[] = []
function showNext() {
  const request = queue[0]
  if (!request || request.host) return
  const host = document.createElement('div'); request.host = host; document.body.append(host)
  const { signal: _signal, ...props } = request.options
  render(createVNode(HqConfirmDialog, { ...props, onAnswer: (value: boolean) => finish(request, value) }), host)
}
function finish(request: Request, result: boolean) {
  const index = queue.indexOf(request)
  if (index < 0) return
  queue.splice(index, 1); request.cleanup?.()
  if (request.host) { render(null, request.host); request.host.remove() }
  request.settle(result)
  // Let overlay focus restoration finish before opening another queued confirmation.
  queueMicrotask(showNext)
}
export function confirm(options: ConfirmOptions): Promise<boolean> {
  if (typeof document === 'undefined' || options.signal?.aborted) return Promise.resolve(false)
  return new Promise((settle) => {
    const request: Request = { options, settle }
    const abort = () => finish(request, false)
    options.signal?.addEventListener('abort', abort, { once: true })
    request.cleanup = () => options.signal?.removeEventListener('abort', abort)
    queue.push(request); showNext()
  })
}
/** Page-scoped confirmations resolve false when the caller leaves the page. */
export function useConfirm() {
  const controller = new AbortController()
  if (getCurrentScope()) onScopeDispose(() => controller.abort())
  return (options: Omit<ConfirmOptions, 'signal'>) => confirm({ ...options, signal: controller.signal }).then((result) => result && !controller.signal.aborted)
}
