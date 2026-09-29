<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import type { RemoteLinkView, RemoteSyncSettingsView } from '@hqagent/protocol'
import { getLocalChatGateway } from '@/shared/api'
import { nativeSyncNotice } from './native-utils'
const link = ref<RemoteLinkView | null>(null)
const settings = ref<RemoteSyncSettingsView | null>(null)
let alive = true
let timer: ReturnType<typeof setInterval> | undefined
async function refresh() {
  try {
    const [nextLink, nextSettings] = await Promise.all([getLocalChatGateway().getRemoteLink(), getLocalChatGateway().getRemoteSyncSettings()])
    if (alive) { link.value = nextLink; settings.value = nextSettings }
  } catch { if (alive) { link.value = null; settings.value = null } }
}
onMounted(() => { void refresh(); timer = setInterval(() => { if (!document.hidden) void refresh() }, 15000) })
onBeforeUnmount(() => { alive = false; clearInterval(timer) })
</script>
<template><div class="p-3 text-xs text-warning flex items-center justify-between gap-2"><p>{{ nativeSyncNotice(link, settings) }}</p><button type="button" class="shrink-0 underline" @click="refresh">刷新同步条件</button></div></template>
