<script setup lang="ts">
import { watch, onBeforeUnmount, nextTick, ref } from 'vue'
import { enterOverlay, overlayId } from './overlay-stack'
import { X } from 'lucide-vue-next'

interface Props {
  open: boolean
  title?: string
  description?: string
  width?: string
  closable?: boolean
  closeOnBackdrop?: boolean
  initialFocus?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  description: '',
  width: '480px',
  closable: true,
  closeOnBackdrop: true,
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
watch(() => props.open, async (open) => {
  const current = ++generation
  if (!open) { layer?.leave(); layer = undefined; return }
  const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
  await nextTick()
  if (current !== generation || !props.open) return
  layer = enterOverlay(() => panel.value, () => { if (props.closable) close() }, opener, props.initialFocus)
  zIndex.value = layer.zIndex
}, { immediate: true, flush: 'post' })
onBeforeUnmount(() => { generation++; layer?.leave() })
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 flex items-center justify-center p-4"
      :style="{ zIndex }"
    >
      <!-- Backdrop -->
      <div
        class="fixed inset-0 backdrop-blur-[2px] transition-opacity"
        style="background: var(--color-overlay)"
        data-testid="dialog-backdrop"
        @click="closable && closeOnBackdrop ? close() : null"
      />

      <!-- Content -->
      <div
        ref="panel"
        tabindex="-1"
        :aria-labelledby="title || $slots.title ? `${id}-title` : undefined"
        :aria-describedby="description ? `${id}-description` : undefined"
        role="dialog"
        aria-modal="true"
        class="relative w-full bg-elevated border border-border rounded-[var(--radius-lg)] shadow-dialog overflow-hidden z-10 flex flex-col max-h-[90vh]"
        :style="{ maxWidth: width }"
      >
        <!-- Header -->
        <div class="flex items-center justify-between px-5 py-4 border-b border-border-subtle shrink-0">
          <div>
            <h3 :id="`${id}-title`" v-if="title || $slots.title" class="text-base font-semibold text-content-primary">
              <slot name="title">{{ title }}</slot>
            </h3>
            <p :id="`${id}-description`" v-if="description" class="text-sm text-content-secondary mt-2 whitespace-pre-line leading-relaxed">
              {{ description }}
            </p>
          </div>

          <button
            v-if="closable"
            type="button"
            aria-label="关闭弹窗"
            class="min-w-[44px] min-h-[44px] flex items-center justify-center text-content-muted hover:text-content-primary rounded-[var(--radius-xs)] hover:bg-muted transition-colors"
            @click="close"
          >
            <X class="h-4 w-4" />
          </button>
        </div>

        <!-- Body -->
        <div v-if="$slots.default" class="p-5 overflow-y-auto flex-1 text-sm text-content-secondary">
          <slot />
        </div>

        <!-- Footer -->
        <div
          v-if="$slots.footer"
          class="flex items-center justify-end gap-2.5 px-5 py-3.5 bg-muted/40 border-t border-border-subtle shrink-0"
        >
          <slot name="footer" :close="close" />
        </div>
      </div>
    </div>
  </Teleport>
</template>
