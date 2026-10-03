import { nextTick } from 'vue'

type Layer = { root: () => HTMLElement | null; dismiss: () => void; opener: HTMLElement | null; zIndex: number }
const layers: Layer[] = []
let previousOverflow = ''
let serial = 0
export const overlayId = () => `hq-overlay-${++serial}`
function focusables(root: HTMLElement) {
  return [...root.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input:not(:disabled),textarea:not(:disabled),select:not(:disabled),[tabindex]:not([tabindex="-1"])')]
    .filter((node) => node.tabIndex >= 0 && !node.hasAttribute('disabled') && !node.hidden && getComputedStyle(node).display !== 'none' && getComputedStyle(node).visibility !== 'hidden')
}
function onKey(event: KeyboardEvent) {
  const layer = layers.at(-1), root = layer?.root()
  if (!layer || !root) return
  if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); layer.dismiss(); return }
  if (event.key !== 'Tab') return
  const nodes = focusables(root)
  if (!nodes.length) { event.preventDefault(); root.focus(); return }
  const first = nodes[0], last = nodes[nodes.length - 1]
  if (!root.contains(document.activeElement) || (event.shiftKey && document.activeElement === first)) { event.preventDefault(); (event.shiftKey ? last : first).focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
/** Shared stack keeps nested dialogs/sheets from unlocking each other's scroll or Esc. */
export function enterOverlay(root: () => HTMLElement | null, dismiss: () => void, opener: HTMLElement | null, initialFocus?: string) {
  if (!layers.length) { previousOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden'; document.addEventListener('keydown', onKey, true) }
  const layer: Layer = { root, dismiss, opener, zIndex: (layers.at(-1)?.zIndex || 40) + 10 }
  layers.push(layer)
  const node = root()
  if (node) (initialFocus ? node.querySelector<HTMLElement>(initialFocus) : focusables(node)[0])?.focus()
  if (node && !node.contains(document.activeElement)) node.focus()
  return {
    zIndex: layer.zIndex,
    leave() {
      const index = layers.indexOf(layer)
      if (index < 0) return
      const wasTop = layers.at(-1) === layer
      layers.splice(index, 1)
      const next = layers.at(-1)
      if (!layers.length) { document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', onKey, true) }
      if (wasTop) void nextTick(() => {
        if (layers.at(-1) !== next) return
        if (opener?.isConnected && (!next || next.root()?.contains(opener))) opener.focus()
        else if (next?.root()) (focusables(next.root()!)[0] || next.root())?.focus()
        else document.querySelector<HTMLElement>('main button:not(:disabled),header button:not(:disabled)')?.focus()
      })
    },
  }
}
