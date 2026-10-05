<script setup lang="ts">
import { watch, onBeforeUnmount, nextTick, ref } from 'vue'
import { enterOverlay, overlayId } from './overlay-stack'
import { X } from 'lucide-vue-next'

interface Props {
  open: boolean
  title?: string
  placement?: 'right' | 'left' | 'bottom'
  width?: string
  height?: string
  closable?: boolean
  initialFocus?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  placement: 'right',
  width: '380px',
  height: '400px',
  closable: true,
  initialFocus: undefined,
})

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'close'): void
}>()

function close() {
  emit('update:open', false)
  emit('close')
}

const panel = ref<HTMLElement | null>(null)
const id = overlayId()
const zIndex = ref(50)
let layer: ReturnType<typeof enterOverlay> | undefined
let generation = 0

watch(
  () => props.open,
  async (open) => {
    const current = ++generation
    if (!open) {
      layer?.leave()
      layer = undefined
      return
    }
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    if (current !== generation || !props.open) return
    layer = enterOverlay(() => panel.value, () => { if (props.closable) close() }, opener, props.initialFocus)
    zIndex.value = layer.zIndex
  },
  { immediate: true, flush: 'post' }
)

onBeforeUnmount(() => {
  generation++
  layer?.leave()
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 overflow-hidden" :style="{ zIndex }">
      <!-- Backdrop -->
      <div
        class="fixed inset-0 backdrop-blur-[2px] transition-opacity"
        style="background: var(--color-overlay)"
        data-testid="drawer-backdrop"
        @click="closable ? close() : null"
      />

      <!-- Drawer Content -->
      <div
        ref="panel"
        tabindex="-1"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="title || $slots.title ? `${id}-title` : undefined"
        :class="[
          'fixed z-10 bg-panel border-border shadow-dialog flex flex-col transition-transform duration-200 ease-out',
          placement === 'right'
            ? 'top-0 right-0 bottom-0 border-l'
            : placement === 'left'
              ? 'top-0 left-0 bottom-0 border-r'
              : 'bottom-0 left-0 right-0 border-t',
        ]"
        :style="{
          width: placement !== 'bottom' ? width : '100%',
          height: placement === 'bottom' ? height : '100%',
        }"
      >
        <!-- Header -->
        <div class="flex items-center justify-between px-4 py-3 border-b border-border-subtle shrink-0">
          <h3 :id="`${id}-title`" class="text-sm font-semibold text-content-primary">
            <slot name="title">{{ title }}</slot>
          </h3>

          <button
            v-if="closable"
            type="button"
            aria-label="关闭抽屉"
            class="min-w-[44px] min-h-[44px] flex items-center justify-center text-content-muted hover:text-content-primary rounded-[var(--radius-xs)] hover:bg-muted transition-colors"
            @click="close"
          >
            <X class="h-4 w-4" />
          </button>
        </div>

        <!-- Body -->
        <div class="p-4 overflow-y-auto flex-1 text-sm text-content-secondary">
          <slot />
        </div>

        <!-- Footer -->
        <div
          v-if="$slots.footer"
          class="flex items-center justify-end gap-2 px-4 py-3 bg-muted/30 border-t border-border-subtle shrink-0"
        >
          <slot name="footer" :close="close" />
        </div>
      </div>
    </div>
  </Teleport>
</template>
