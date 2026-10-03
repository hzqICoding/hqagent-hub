<script setup lang="ts">
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import { ChevronDown, Check } from 'lucide-vue-next'
import HqOptionPanel from './HqOptionPanel.vue'
import { overlayId } from './overlay-stack'
defineOptions({ inheritAttrs: false })
export interface SelectOption { label: string; value: string | number; disabled?: boolean; description?: string }
const props = withDefaults(defineProps<{ modelValue?: string | number; options: SelectOption[]; placeholder?: string; label?: string; disabled?: boolean; error?: string | boolean; size?: 'sm' | 'md' | 'lg'; searchable?: boolean; searchPlaceholder?: string }>(), { modelValue: '', placeholder: '请选择...', label: undefined, disabled: false, error: false, size: 'md', searchable: false, searchPlaceholder: '搜索选项' })
const emit = defineEmits<{ 'update:modelValue': [value: string | number]; change: [value: string | number] }>()
const trigger = ref<HTMLButtonElement | null>(null)
const listbox = ref<HTMLElement | null>(null)
const isOpen = ref(false), query = ref(''), active = ref(-1)
const id = overlayId()
let prefix = '', prefixTimer: ReturnType<typeof setTimeout> | undefined
const selectedOption = computed(() => props.options.find((option) => option.value === props.modelValue))
const visible = computed(() => props.options.filter((option) => !props.searchable || option.label.toLocaleLowerCase().includes(query.value.toLocaleLowerCase())))
const enabled = computed(() => visible.value.map((option, index) => option.disabled ? -1 : index).filter((index) => index >= 0))
function initial() { const index = visible.value.findIndex((o) => o.value === props.modelValue && !o.disabled); active.value = index >= 0 ? index : enabled.value[0] ?? -1 }
function show(last = false) { if (props.disabled) return; query.value = ''; initial(); if (last) active.value = enabled.value.at(-1) ?? -1; isOpen.value = true }
function close() { isOpen.value = false; prefix = ''; clearTimeout(prefixTimer) }
function choose(index: number) { const option = visible.value[index]; if (!option || option.disabled || props.disabled) return; emit('update:modelValue', option.value); emit('change', option.value); close() }
function move(delta: number) {
  const index = enabled.value.indexOf(active.value), length = enabled.value.length
  active.value = length ? enabled.value[(index + delta + length) % length] : -1
  void nextTick(() => listbox.value?.querySelector<HTMLElement>(`[data-option-index="${active.value}"]`)?.scrollIntoView?.({ block: 'nearest' }))
}
function onTriggerKey(event: KeyboardEvent) {
  if (['ArrowDown','ArrowUp','Enter',' '].includes(event.key)) { event.preventDefault(); show(event.key === 'ArrowUp') }
}
function onListKey(event: KeyboardEvent) {
  if (event.isComposing) return
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); move(event.key === 'ArrowDown' ? 1 : -1) }
  else if (event.key === 'Home' || event.key === 'End') { event.preventDefault(); active.value = (event.key === 'Home' ? enabled.value[0] : enabled.value.at(-1)) ?? -1 }
  else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(active.value) }
  else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey) {
    prefix += event.key.toLocaleLowerCase(); clearTimeout(prefixTimer); prefixTimer = setTimeout(() => { prefix = '' }, 600)
    const found = visible.value.findIndex((option) => !option.disabled && option.label.toLocaleLowerCase().startsWith(prefix))
    if (found >= 0) active.value = found
  }
}
function onSearchKey(event: KeyboardEvent) { if (['ArrowDown','ArrowUp','Enter'].includes(event.key)) { event.preventDefault(); if (event.key === 'Enter') choose(active.value); else { listbox.value?.focus(); move(event.key === 'ArrowDown' ? 1 : -1) } } }
watch(query, initial)
watch(() => props.disabled, (disabled) => { if (disabled) close() })
watch(() => props.options, initial)
onBeforeUnmount(() => clearTimeout(prefixTimer))
</script>
<template>
  <div class="relative w-full min-w-0">
    <button ref="trigger" v-bind="$attrs" type="button" :disabled="disabled" aria-haspopup="listbox" :aria-expanded="isOpen" :aria-controls="`${id}-listbox`" :aria-label="$attrs['aria-label'] as string || label || placeholder" :aria-invalid="Boolean(error) || undefined"
      class="hq-form-control w-full min-h-[44px] min-w-0 flex items-center justify-between gap-2 border px-3 rounded-lg text-left text-sm" @click="isOpen ? close() : show()" @keydown="onTriggerKey">
      <span v-if="selectedOption" class="truncate">{{ selectedOption.label }}</span><span v-else class="hq-form-placeholder truncate">{{ placeholder }}</span><ChevronDown class="w-4 h-4 shrink-0" />
    </button>
    <HqOptionPanel :open="isOpen" :anchor="trigger" :title="label || placeholder" :initial-focus="searchable ? '[data-select-search]' : '[role=listbox]'" @close="close">
      <input v-if="searchable" v-model="query" data-select-search :aria-label="searchPlaceholder" :placeholder="searchPlaceholder" class="hq-form-control w-full min-h-[44px] border rounded-lg px-3 mb-1" @keydown="onSearchKey" />
      <div :id="`${id}-listbox`" ref="listbox" role="listbox" tabindex="0" :aria-label="label || placeholder" :aria-activedescendant="active >= 0 ? `${id}-option-${active}` : undefined" class="outline-none" @keydown="onListKey">
        <button v-for="(option, index) in visible" :id="`${id}-option-${index}`" :key="option.value" type="button" role="option" tabindex="-1" :data-option-index="index" :disabled="option.disabled" :aria-disabled="option.disabled || undefined" :aria-selected="modelValue === option.value"
          class="hq-form-option w-full min-h-[44px] flex items-center justify-between gap-2 px-3 py-2 text-left text-sm rounded-lg" :class="index === active ? 'bg-muted' : 'hover:bg-muted'" @click="choose(index)" @pointermove="!option.disabled && (active = index)">
          <span class="min-w-0 break-words"><span class="block">{{ option.label }}</span><span v-if="option.description" class="block text-xs text-content-secondary">{{ option.description }}</span></span><Check v-if="modelValue === option.value" class="w-4 h-4 shrink-0 text-accent" />
        </button>
        <p v-if="!visible.length" class="p-3 text-sm text-content-secondary">暂无可选项</p>
      </div>
    </HqOptionPanel>
    <span v-if="typeof error === 'string' && error" role="alert" class="text-xs text-status-danger mt-1 block">{{ error }}</span>
  </div>
</template>
