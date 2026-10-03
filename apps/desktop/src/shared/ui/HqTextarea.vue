<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  modelValue?: string
  placeholder?: string
  disabled?: boolean
  readonly?: boolean
  rows?: number
  mono?: boolean
  error?: string | boolean
  maxlength?: number
  showCount?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  placeholder: '',
  disabled: false,
  readonly: false,
  rows: 3,
  mono: false,
  error: false,
  showCount: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'change', value: string): void
}>()

const hasError = computed(() => Boolean(props.error))

function onInput(e: Event) {
  const target = e.target as HTMLTextAreaElement
  emit('update:modelValue', target.value)
}

function onChange(e: Event) {
  const target = e.target as HTMLTextAreaElement
  emit('change', target.value)
}
</script>

<template>
  <div class="w-full flex flex-col gap-1">
    <div
      :data-disabled="disabled || undefined"
      :data-invalid="hasError || undefined"
      :class="[
        'hq-form-field w-full border bg-panel transition-colors rounded-[var(--radius-sm)] p-2.5',
        'focus-within:ring-2 focus-within:ring-ring focus-within:border-transparent',
        hasError
          ? 'border-status-danger focus-within:ring-status-danger'
          : 'border-border hover:border-border-strong',
        disabled ? 'cursor-not-allowed' : '',
      ]"
    >
      <textarea class="hq-form-control hq-form-control--embedded"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :aria-invalid="hasError || undefined"
        :readonly="readonly"
        :rows="rows"
        :maxlength="maxlength"
        :class="[
          'w-full bg-transparent text-content-primary placeholder:text-content-disabled outline-none resize-y text-sm',
          mono ? 'font-mono' : 'font-sans',
        ]"
        @input="onInput"
        @change="onChange"
      />

      <div
        v-if="showCount && maxlength"
        class="text-right text-xs text-content-muted mt-1 select-none"
      >
        {{ (modelValue || '').length }}/{{ maxlength }}
      </div>
    </div>

    <span v-if="typeof error === 'string' && error" class="text-xs text-status-danger">
      {{ error }}
    </span>
  </div>
</template>
