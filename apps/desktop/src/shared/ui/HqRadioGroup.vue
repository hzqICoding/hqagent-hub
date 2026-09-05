<script setup lang="ts">
export interface RadioOption {
  label: string
  value: string | number
  disabled?: boolean
  description?: string
}

interface Props {
  modelValue?: string | number
  options: RadioOption[]
  disabled?: boolean
  direction?: 'horizontal' | 'vertical'
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  disabled: false,
  direction: 'vertical',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | number): void
  (e: 'change', value: string | number): void
}>()

function select(opt: RadioOption) {
  if (props.disabled || opt.disabled) return
  emit('update:modelValue', opt.value)
  emit('change', opt.value)
}
</script>

<template>
  <div
    role="radiogroup"
    :class="[
      'flex',
      direction === 'horizontal' ? 'flex-row flex-wrap gap-4' : 'flex-col gap-2',
    ]"
  >
    <label
      v-for="opt in options"
      :key="opt.value"
      :class="[
        'inline-flex items-start gap-2.5 select-none',
        disabled || opt.disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
      ]"
      @click.prevent="select(opt)"
    >
      <div
        :class="[
          'h-4 w-4 rounded-full border flex items-center justify-center transition-colors outline-none shrink-0 mt-0.5',
          'focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-app',
          opt.value === modelValue
            ? 'border-action-primary'
            : 'border-border bg-panel hover:border-border-strong',
        ]"
        tabindex="0"
        role="radio"
        :aria-checked="opt.value === modelValue"
        @keydown.space.prevent="select(opt)"
      >
        <div
          v-if="opt.value === modelValue"
          class="h-2 w-2 rounded-full bg-action-primary"
        />
      </div>

      <div class="text-sm">
        <div class="text-content-primary leading-tight">{{ opt.label }}</div>
        <div v-if="opt.description" class="text-xs text-content-muted mt-0.5">
          {{ opt.description }}
        </div>
      </div>
    </label>
  </div>
</template>
