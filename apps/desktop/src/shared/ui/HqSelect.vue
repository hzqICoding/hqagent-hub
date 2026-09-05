<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ChevronDown, Check } from 'lucide-vue-next'

export interface SelectOption {
  label: string
  value: string | number
  disabled?: boolean
  description?: string
}

interface Props {
  modelValue?: string | number
  options: SelectOption[]
  placeholder?: string
  disabled?: boolean
  error?: string | boolean
  size?: 'sm' | 'md' | 'lg'
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  placeholder: '请选择...',
  disabled: false,
  error: false,
  size: 'md',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | number): void
  (e: 'change', value: string | number): void
}>()

const isOpen = ref(false)
const containerRef = ref<HTMLElement | null>(null)

const selectedOption = computed(() => {
  return props.options.find((opt) => opt.value === props.modelValue)
})

const hasError = computed(() => Boolean(props.error))

const sizeClasses = computed(() => {
  switch (props.size) {
    case 'sm':
      return 'h-7 px-2 text-xs rounded-[var(--radius-xs)]'
    case 'lg':
      return 'h-11 px-4 text-base rounded-[var(--radius-md)]'
    case 'md':
    default:
      return 'h-9 px-3 text-sm rounded-[var(--radius-sm)]'
  }
})

function toggle() {
  if (!props.disabled) {
    isOpen.value = !isOpen.value
  }
}

function selectOption(option: SelectOption) {
  if (option.disabled) return
  emit('update:modelValue', option.value)
  emit('change', option.value)
  isOpen.value = false
}

function handleClickOutside(e: MouseEvent) {
  if (containerRef.value && !containerRef.value.contains(e.target as Node)) {
    isOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<template>
  <div ref="containerRef" class="relative w-full">
    <button
      type="button"
      :disabled="disabled"
      :class="[
        'w-full flex items-center justify-between border bg-panel transition-colors text-left outline-none',
        'focus-visible:ring-2 focus-visible:ring-ring focus-visible:border-transparent',
        hasError
          ? 'border-status-danger'
          : 'border-border hover:border-border-strong',
        disabled ? 'opacity-50 cursor-not-allowed bg-muted' : 'cursor-pointer',
        sizeClasses,
      ]"
      @click="toggle"
    >
      <span v-if="selectedOption" class="text-content-primary truncate">
        {{ selectedOption.label }}
      </span>
      <span v-else class="text-content-disabled truncate">
        {{ placeholder }}
      </span>

      <ChevronDown
        :class="[
          'h-4 w-4 text-content-muted shrink-0 transition-transform duration-150',
          isOpen ? 'rotate-180 text-content-primary' : '',
        ]"
      />
    </button>

    <!-- Dropdown Menu -->
    <div
      v-if="isOpen"
      class="absolute z-50 mt-1 w-full max-h-60 overflow-y-auto bg-elevated border border-border rounded-[var(--radius-sm)] shadow-popover py-1 focus:outline-none"
    >
      <div
        v-for="opt in options"
        :key="opt.value"
        :class="[
          'flex items-center justify-between px-3 py-2 text-sm cursor-pointer select-none transition-colors',
          opt.disabled
            ? 'opacity-40 cursor-not-allowed text-content-disabled'
            : 'text-content-primary hover:bg-muted',
          opt.value === modelValue ? 'bg-accent-soft/30 font-medium' : '',
        ]"
        @click="selectOption(opt)"
      >
        <div>
          <div>{{ opt.label }}</div>
          <div v-if="opt.description" class="text-xs text-content-muted">
            {{ opt.description }}
          </div>
        </div>
        <Check v-if="opt.value === modelValue" class="h-4 w-4 text-accent shrink-0" />
      </div>
    </div>

    <span v-if="typeof error === 'string' && error" class="text-xs text-status-danger mt-1 block">
      {{ error }}
    </span>
  </div>
</template>
