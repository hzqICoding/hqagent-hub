<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { useLocalAuthStore } from '@/stores/local-auth.store'

const auth = useLocalAuthStore()
const connected = ref(false)
const everConnected = ref(false)
const message = ref('正在启动本机 Hub，连接就绪后将自动进入。')
const reason = ref('')
const updateAgentMissing = ref(false)
let stopped = false
let timer: ReturnType<typeof setTimeout> | undefined

async function refresh() {
  try {
    connected.value = await auth.checkAuthStatus()
    if (stopped) return
    if (connected.value) everConnected.value = true
    reason.value = connected.value ? '' : auth.authError || ''
    const status = await invoke<{ childProcesses: { component: string; state: string }[] }>('get_shell_status')
    updateAgentMissing.value = status.childProcesses.some(p => p.component === 'update-agent' && p.state === 'missing')
    const core = status.childProcesses.find(p => p.component === 'core')
    message.value = '正在启动本机 Hub，连接就绪后将自动进入。'
    if (core?.state === 'missing') reason.value = '未找到 Hub 程序，请检查安装或 desktop-shell.json 的 coreExecutable 配置。'
  } catch {
    connected.value = false
    reason.value = auth.authError || '暂时无法读取本机 Hub 状态，正在自动重试。'
  } finally {
    if (!stopped) timer = setTimeout(() => { void refresh() }, 2000)
  }
}

onMounted(() => {
  void refresh()
})
onUnmounted(() => { stopped = true; clearTimeout(timer) })
</script>

<template>
  <div class="h-full flex flex-col min-h-0">
    <div v-if="!connected || updateAgentMissing" class="shrink-0 px-4 py-2 border-b border-border/30 bg-panel text-xs flex items-center gap-4">
      <span role="status">{{ connected ? 'Hub：运行中' : 'Hub：连接中' }}</span>
      <span v-if="updateAgentMissing" class="text-text-muted">更新组件未安装</span>
    </div>
    <div v-if="!connected" role="status" class="p-6 text-sm">
      <p>{{ message }}</p>
      <p v-if="reason" class="mt-2 text-text-muted">{{ reason }}</p>
    </div>
    <!-- Preserve mounted pages/drafts during a crash; block interaction until reconnected. -->
    <div v-if="everConnected" v-show="connected" class="flex-1 min-h-0"><slot /></div>
  </div>
</template>
