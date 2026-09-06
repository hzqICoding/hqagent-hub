import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
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

  // Getters
  const recentWorkspaces = computed(() => {
    return [...workspaces.value].sort(
      (a, b) => new Date(b.lastOpenedAt).getTime() - new Date(a.lastOpenedAt).getTime()
    )
  })

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
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '获取工作区列表失败'
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
      ws.lastOpenedAt = new Date().toISOString()
      currentWorkspace.value = ws
      appStore.addLog({
        level: 'info',
        source: 'WorkspaceStore',
        message: `已切换当前工作区: ${ws.name} (${ws.path})`,
      })
    }
  }

  function addWorkspace(path: string, name?: string): WorkspaceView {
    const normalizedPath = path.replace(/\\/g, '/')
    const dirName = name || normalizedPath.split('/').filter(Boolean).pop() || 'Untitled'
    const newWs: WorkspaceView = {
      id: 'ws_' + Math.random().toString(36).substring(2, 9),
      name: dirName,
      path: normalizedPath,
      vcs: 'git',
      branch: 'main',
      isClean: true,
      lastOpenedAt: new Date().toISOString(),
      memoryDirPresent: false,
    }
    workspaces.value.unshift(newWs)
    currentWorkspace.value = newWs
    appStore.addLog({
      level: 'info',
      source: 'WorkspaceStore',
      message: `已添加工作区: ${newWs.name} (${newWs.path})`,
    })
    return newWs
  }

  function removeWorkspace(id: string) {
    const index = workspaces.value.findIndex((w) => w.id === id)
    if (index !== -1) {
      const removed = workspaces.value.splice(index, 1)[0]
      if (currentWorkspace.value?.id === id) {
        currentWorkspace.value = workspaces.value[0] || null
      }
      appStore.addLog({
        level: 'info',
        source: 'WorkspaceStore',
        message: `已移除工作区: ${removed.name}`,
      })
    }
  }

  function initMemoryDir(id: string) {
    const ws = workspaces.value.find((w) => w.id === id)
    if (ws) {
      ws.memoryDirPresent = true
      appStore.addLog({
        level: 'info',
        source: 'WorkspaceStore',
        message: `已初始化 .hqagent/ 共享记忆目录: ${ws.name}`,
      })
    }
  }

  function setWorkspaceProfile(workspaceId: string, profileId?: string) {
    const ws = workspaces.value.find((w) => w.id === workspaceId)
    if (ws) {
      ws.defaultProfileId = profileId
      appStore.addLog({
        level: 'info',
        source: 'WorkspaceStore',
        message: `已更新工作区 ${ws.name} 的默认 Team Profile: ${profileId || '无'}`,
      })
    }
  }

  return {
    workspaces,
    currentWorkspace,
    recentWorkspaces,
    isLoading,
    error,
    fetchWorkspaces,
    switchWorkspace,
    addWorkspace,
    removeWorkspace,
    initMemoryDir,
    setWorkspaceProfile,
  }
})
