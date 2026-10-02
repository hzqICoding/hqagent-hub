<script setup lang="ts">
import { ref, onMounted, watch, nextTick, type Component } from 'vue'
import HqOptionPanel from './HqOptionPanel.vue'
import { overlayId } from './overlay-stack'
export interface DropdownItem { id?: string; label: string; action?: () => void; icon?: Component; danger?: boolean; disabled?: boolean; divider?: boolean }
const props = withDefaults(defineProps<{ items: DropdownItem[]; placement?: 'left' | 'right' }>(), { placement: 'right' })
const isOpen = ref(false), holder = ref<HTMLElement | null>(null), trigger = ref<HTMLElement | null>(null), menu = ref<HTMLElement | null>(null)
const id = overlayId()
function decorate() { trigger.value = holder.value?.querySelector('button') || holder.value; trigger.value?.setAttribute('aria-haspopup','menu'); trigger.value?.setAttribute('aria-expanded',String(isOpen.value)); trigger.value?.setAttribute('aria-controls',id); if (trigger.value === holder.value && trigger.value) { trigger.value.tabIndex = 0; trigger.value.setAttribute('role','button') } }
function toggle() { if (!(trigger.value instanceof HTMLButtonElement && trigger.value.disabled)) isOpen.value = !isOpen.value }
function triggerKey(event: KeyboardEvent) { if (['ArrowDown','ArrowUp'].includes(event.key) || (event.target === holder.value && ['Enter',' '].includes(event.key))) { event.preventDefault(); isOpen.value = true } }
function menuKey(event: KeyboardEvent) {
  const buttons = [...(menu.value?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') || [])]
  if (!buttons.length) return
  const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
  if (['ArrowDown','ArrowUp','Home','End'].includes(event.key)) { event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length; buttons[next].focus() }
}
async function action(item: DropdownItem) { if (item.disabled || item.divider) return; isOpen.value = false; await nextTick(); item.action?.() }
onMounted(decorate)
watch(isOpen, decorate)
</script>
<template>
  <div class="relative inline-block text-left">
    <div ref="holder" @click="toggle" @keydown="triggerKey"><slot :is-open="isOpen"><button type="button" class="min-h-[44px] px-3">更多操作</button></slot></div>
    <HqOptionPanel :open="isOpen" :anchor="trigger" :placement="placement" title="操作" initial-focus="[role=menuitem]:not(:disabled)" @close="isOpen = false">
      <div :id="id" ref="menu" role="menu" aria-label="操作" @keydown="menuKey">
        <template v-for="(item, index) in props.items" :key="item.id || index">
          <div v-if="item.divider" role="separator" class="my-1 border-t border-border" />
          <button v-else type="button" role="menuitem" :disabled="item.disabled" class="min-h-[44px] w-full flex items-center gap-2 px-3 py-2 text-left text-sm rounded-lg hover:bg-muted" :class="item.danger ? 'text-status-danger' : 'text-content-primary'" @click="action(item)"><component :is="item.icon" v-if="item.icon" class="w-4 h-4 shrink-0" />{{ item.label }}</button>
        </template>
      </div>
    </HqOptionPanel>
  </div>
</template>
