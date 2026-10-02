<script setup lang="ts">
import HqSelect, { type SelectOption } from './HqSelect.vue'
defineOptions({ inheritAttrs: false })
export type ComboboxOption = SelectOption
withDefaults(defineProps<{ modelValue?: string | number; options: SelectOption[]; placeholder?: string; searchPlaceholder?: string; disabled?: boolean; error?: string | boolean }>(), { modelValue: '', placeholder: '请选择...', searchPlaceholder: '搜索...', disabled: false, error: false })
defineEmits<{ 'update:modelValue': [value: string | number]; change: [value: string | number] }>()
</script>
<template><HqSelect v-bind="$attrs" :model-value="modelValue" :options="options" :placeholder="placeholder" :search-placeholder="searchPlaceholder" :disabled="disabled" :error="error" searchable @update:model-value="$emit('update:modelValue', $event)" @change="$emit('change', $event)" /></template>
