<script setup lang="ts">
import { ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { X } from 'lucide-vue-next'
import { enterOverlay, overlayId } from './overlay-stack'
const props = withDefaults(defineProps<{ open: boolean; anchor: HTMLElement | null; title?: string; initialFocus?: string; placement?: 'left' | 'right' }>(), { title: '请选择', initialFocus: undefined, placement: 'left' })
const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement | null>(null)
const mobile = ref(false)
const position = ref<Record<string, string>>({})
const zIndex = ref(50)
const id = overlayId()
let layer: ReturnType<typeof enterOverlay> | undefined
let generation = 0
function locate() {
  mobile.value = window.innerWidth < 640
  if (mobile.value || !props.anchor) { position.value = {}; return }
  const rect = props.anchor.getBoundingClientRect()
  const width = Math.min(Math.max(rect.width, 200), window.innerWidth - 24)
  const below = window.innerHeight - rect.bottom - 16, above = rect.top - 16
  const up = below < 200 && above > below
  const height = Math.min(360, Math.max(100, up ? above : below))
  position.value = { width: `${width}px`, maxHeight: `${height}px`, left: `${Math.max(12, Math.min(props.placement === 'right' ? rect.right - width : rect.left, window.innerWidth - width - 12))}px`, ...(up ? { bottom: `${window.innerHeight - rect.top + 4}px` } : { top: `${rect.bottom + 4}px` }) }
}
function release() { layer?.leave(); layer = undefined; window.removeEventListener('resize', locate) }
watch(() => props.open, async (open) => {
  const current = ++generation
  if (!open) { release(); return }
  const opener = props.anchor || (document.activeElement instanceof HTMLElement ? document.activeElement : null)
  locate(); await nextTick()
  if (current !== generation || !props.open) return
  layer = enterOverlay(() => panel.value, () => emit('close'), opener, props.initialFocus)
  zIndex.value = layer.zIndex
  window.addEventListener('resize', locate)
}, { immediate: true, flush: 'post' })
onBeforeUnmount(() => { generation++; release() })
</script>
<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0" :style="{ zIndex }">
      <div class="absolute inset-0" :style="{ background: mobile ? 'var(--color-overlay)' : 'transparent' }" data-testid="option-backdrop" @click="$emit('close')" />
      <section ref="panel" tabindex="-1" :role="mobile ? 'dialog' : undefined" :aria-modal="mobile || undefined" :aria-labelledby="mobile ? `${id}-title` : undefined"
        class="fixed bg-elevated text-content-primary border border-border shadow-popover flex flex-col overflow-hidden"
        :class="mobile ? 'inset-x-0 bottom-0 rounded-t-2xl max-h-[80dvh] pb-[env(safe-area-inset-bottom)]' : 'rounded-lg'" :style="position" data-testid="option-panel">
        <header v-if="mobile" class="flex items-center justify-between px-4 py-2 border-b border-border shrink-0"><h2 :id="`${id}-title`" class="font-semibold text-sm">{{ title }}</h2><button type="button" aria-label="关闭选择面板" class="min-w-[44px] min-h-[44px] flex items-center justify-center" @click="$emit('close')"><X class="w-5 h-5" /></button></header>
        <div class="overflow-y-auto min-h-0 p-1"><slot /></div>
      </section>
    </div>
  </Teleport>
</template>
