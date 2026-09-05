import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { WorkspaceView } from '@hqagent/protocol'
import { getUiGateway } from '@/shared/api'
import { useAppStore } from './app.store'

export const useWorkspaceStore = defineStore('workspace', () => {
  const gateway = getUiGateway()
  const appStore = useAppStore()

  // State
  const workspaces = ref<WorkspaceView[]>([])
  const currentWorkspace = ref<WorkspaceView | null>(null)
  const isLoading = ref<boolean>(false)
  const error = ref<string | null>(null)

  // Actions
  async function fetchWorkspaces() {
    isLoading.value = true
    error.value = null

    try {
      const data = await gateway.listWorkspaces()
      workspaces.value = data
      if (!currentWorkspace.value && data.length > 0) {
        currentWorkspace.value = data[0]
      }
    } catch (err: any) {
      const msg = err?.message || '获取工作区列表失败'
      error.value = msg
      appStore.addLog({
        level: 'error',
        source: 'WorkspaceStore',
        message: `获取工作区列表失败: ${msg}`,
      })
    } finally {
      isLoading.value = false
    }
  }

  function switchWorkspace(id: string) {
    const ws = workspaces.value.find((w) => w.id === id)
    if (ws) {
      currentWorkspace.value = ws
      appStore.addLog({
        level: 'info',
        source: 'WorkspaceStore',
        message: `已切换当前工作区: ${ws.name} (${ws.path})`,
      })
    }
  }

  return {
    workspaces,
    currentWorkspace,
    isLoading,
    error,
    fetchWorkspaces,
    switchWorkspace,
  }
})
