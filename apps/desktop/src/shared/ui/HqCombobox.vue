<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ChevronDown, Check, Search } from 'lucide-vue-next'
import type { SelectOption } from './HqSelect.vue'

interface Props {
  modelValue?: string | number
  options: SelectOption[]
  placeholder?: string
  searchPlaceholder?: string
  disabled?: boolean
  error?: string | boolean
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  placeholder: '搜索或选择...',
  searchPlaceholder: '输入关键词搜索...',
  disabled: false,
  error: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | number): void
  (e: 'change', value: string | number): void
}>()

const isOpen = ref(false)
const searchQuery = ref('')
const containerRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)

const selectedOption = computed(() => {
  return props.options.find((opt) => opt.value === props.modelValue)
})

const filteredOptions = computed(() => {
  if (!searchQuery.value.trim()) return props.options
  const q = searchQuery.value.toLowerCase()
  return props.options.filter(
    (opt) =>
      opt.label.toLowerCase().includes(q) ||
      (opt.description && opt.description.toLowerCase().includes(q))
  )
})

function toggle() {
  if (!props.disabled) {
    isOpen.value = !isOpen.value
    if (isOpen.value) {
      searchQuery.value = ''
      setTimeout(() => inputRef.value?.focus(), 50)
    }
  }
}

function selectOption(opt: SelectOption) {
  if (opt.disabled) return
  emit('update:modelValue', opt.value)
  emit('change', opt.value)
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
        'w-full flex items-center justify-between h-9 px-3 text-sm border bg-panel transition-colors text-left outline-none rounded-[var(--radius-sm)]',
        'focus-visible:ring-2 focus-visible:ring-ring focus-visible:border-transparent',
        error ? 'border-status-danger' : 'border-border hover:border-border-strong',
        disabled ? 'opacity-50 cursor-not-allowed bg-muted' : 'cursor-pointer',
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

    <!-- Popover with Search and Options -->
    <div
      v-if="isOpen"
      class="absolute z-50 mt-1 w-full bg-elevated border border-border rounded-[var(--radius-sm)] shadow-popover p-1.5 focus:outline-none"
    >
      <!-- Search Input -->
      <div class="flex items-center px-2 py-1 bg-app border border-border-subtle rounded mb-1.5">
        <Search class="h-3.5 w-3.5 text-content-muted mr-1.5 shrink-0" />
        <input
          ref="inputRef"
          v-model="searchQuery"
          type="text"
          :placeholder="searchPlaceholder"
          class="w-full bg-transparent text-xs text-content-primary outline-none placeholder:text-content-disabled"
        />
      </div>

      <!-- List -->
      <div class="max-h-52 overflow-y-auto">
        <div
          v-for="opt in filteredOptions"
          :key="opt.value"
          :class="[
            'flex items-center justify-between px-2.5 py-1.5 text-sm cursor-pointer select-none rounded transition-colors',
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

        <div
          v-if="filteredOptions.length === 0"
          class="text-xs text-content-muted py-3 text-center"
        >
          无匹配结果
        </div>
      </div>
    </div>
  </div>
</template>
