<script setup lang="ts">
import { watch, onMounted, onUnmounted } from 'vue'
import { X } from 'lucide-vue-next'

interface Props {
  open: boolean
  title?: string
  description?: string
  width?: string
  closable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  description: '',
  width: '480px',
  closable: true,
})

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'close'): void
}>()

function close() {
  emit('update:open', false)
  emit('close')
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open && props.closable) {
    close()
  }
}

watch(
  () => props.open,
  (isOpen) => {
    if (typeof document !== 'undefined') {
      if (isOpen) {
        document.body.style.overflow = 'hidden'
      } else {
        document.body.style.overflow = ''
      }
    }
  }
)

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  if (typeof document !== 'undefined') {
    document.body.style.overflow = ''
  }
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex items-center justify-center p-4"
    >
      <!-- Backdrop -->
      <div
        class="fixed inset-0 bg-black/60 backdrop-blur-[2px] transition-opacity"
        @click="closable ? close() : null"
      />

      <!-- Content -->
      <div
        role="dialog"
        aria-modal="true"
        class="relative w-full bg-elevated border border-border rounded-[var(--radius-lg)] shadow-dialog overflow-hidden z-10 flex flex-col max-h-[90vh]"
        :style="{ maxWidth: width }"
      >
        <!-- Header -->
        <div class="flex items-center justify-between px-5 py-4 border-b border-border-subtle shrink-0">
          <div>
            <h3 v-if="title || $slots.title" class="text-base font-semibold text-content-primary">
              <slot name="title">{{ title }}</slot>
            </h3>
            <p v-if="description" class="text-xs text-content-muted mt-0.5">
              {{ description }}
            </p>
          </div>

          <button
            v-if="closable"
            type="button"
            class="text-content-muted hover:text-content-primary rounded-[var(--radius-xs)] p-1 hover:bg-muted transition-colors"
            @click="close"
          >
            <X class="h-4 w-4" />
          </button>
        </div>

        <!-- Body -->
        <div class="p-5 overflow-y-auto flex-1 text-sm text-content-secondary">
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
