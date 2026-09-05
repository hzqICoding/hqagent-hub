<script setup lang="ts">
import { watch, onMounted, onUnmounted } from 'vue'
import { X } from 'lucide-vue-next'

interface Props {
  open: boolean
  title?: string
  placement?: 'right' | 'left' | 'bottom'
  width?: string
  height?: string
  closable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  placement: 'right',
  width: '380px',
  height: '400px',
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
    <div v-if="open" class="fixed inset-0 z-50 overflow-hidden">
      <!-- Backdrop -->
      <div
        class="fixed inset-0 bg-black/50 backdrop-blur-[1px] transition-opacity"
        @click="closable ? close() : null"
      />

      <!-- Drawer Content -->
      <div
        role="dialog"
        aria-modal="true"
        :class="[
          'fixed z-10 bg-panel border-border shadow-2xl flex flex-col transition-transform duration-200 ease-out',
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
          <h3 class="text-sm font-semibold text-content-primary">
            <slot name="title">{{ title }}</slot>
          </h3>

          <button
            v-if="closable"
            type="button"
            class="text-content-muted hover:text-content-primary rounded p-1 hover:bg-muted transition-colors"
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
