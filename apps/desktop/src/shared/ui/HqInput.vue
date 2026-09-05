<script setup lang="ts">
import { computed } from 'vue'
import { X } from 'lucide-vue-next'

interface Props {
  modelValue?: string | number
  type?: string
  placeholder?: string
  disabled?: boolean
  readonly?: boolean
  error?: string | boolean
  size?: 'sm' | 'md' | 'lg'
  clearable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  type: 'text',
  placeholder: '',
  disabled: false,
  readonly: false,
  error: false,
  size: 'md',
  clearable: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'change', value: string): void
  (e: 'clear'): void
  (e: 'focus', ev: FocusEvent): void
  (e: 'blur', ev: FocusEvent): void
}>()

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

function onInput(e: Event) {
  const target = e.target as HTMLInputElement
  emit('update:modelValue', target.value)
}

function onChange(e: Event) {
  const target = e.target as HTMLInputElement
  emit('change', target.value)
}

function clear() {
  emit('update:modelValue', '')
  emit('clear')
}
</script>

<template>
  <div class="w-full flex flex-col gap-1">
    <div
      :class="[
        'flex items-center w-full border bg-panel transition-colors',
        'focus-within:ring-2 focus-within:ring-ring focus-within:border-transparent',
        hasError
          ? 'border-status-danger focus-within:ring-status-danger'
          : 'border-border hover:border-border-strong',
        disabled ? 'opacity-50 cursor-not-allowed bg-muted' : '',
        sizeClasses,
      ]"
    >
      <div v-if="$slots.prefix" class="mr-2 shrink-0 text-content-muted flex items-center">
        <slot name="prefix" />
      </div>

      <input
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        class="w-full bg-transparent text-content-primary placeholder:text-content-disabled outline-none disabled:cursor-not-allowed"
        @input="onInput"
        @change="onChange"
        @focus="emit('focus', $event)"
        @blur="emit('blur', $event)"
      />

      <button
        v-if="clearable && !disabled && !readonly && modelValue"
        type="button"
        class="ml-1 text-content-muted hover:text-content-primary shrink-0"
        @click.stop="clear"
      >
        <X class="h-3.5 w-3.5" />
      </button>

      <div v-if="$slots.suffix" class="ml-2 shrink-0 text-content-muted flex items-center">
        <slot name="suffix" />
      </div>
    </div>

    <span v-if="typeof error === 'string' && error" class="text-xs text-status-danger">
      {{ error }}
    </span>
  </div>
</template>
