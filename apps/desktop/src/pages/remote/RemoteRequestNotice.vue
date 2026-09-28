<script setup lang="ts">
import { ref, watch } from 'vue'
import { remoteRequestFailure } from '@/shared/api/remote-diagnostics'
const copied = ref(false)
watch(remoteRequestFailure, () => { copied.value = false })
async function copyRequestId() {
  const id = remoteRequestFailure.value?.requestId
  if (!id) return
  try { await navigator.clipboard.writeText(id); copied.value = true } catch { copied.value = false }
}
</script>

<template>
  <div v-if="remoteRequestFailure" role="alert" class="shrink-0 bg-danger/10 text-danger border-b border-danger/20 px-3 py-2 text-xs">
    <div class="flex justify-between gap-2">
      <span>{{ remoteRequestFailure.message }}</span>
      <button type="button" class="shrink-0 underline" @click="remoteRequestFailure = null; copied = false">关闭</button>
    </div>
    <button v-if="remoteRequestFailure.requestId" type="button" class="block mt-1 text-[10px] select-text break-all text-left" @click="copyRequestId">
      requestId: {{ remoteRequestFailure.requestId }} {{ copied ? '已复制' : '点击复制' }}
    </button>
  </div>
</template>
