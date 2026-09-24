import { defineStore } from 'pinia'
import { ref } from 'vue'
import type {
  LocalSceneView,
  SaveLocalSceneInput,
  LocalAgentModelsView,
  AgentView,
} from '@hqagent/protocol'
import { getLocalChatGateway, HubApiError } from '@/shared/api'

export const useScenesStore = defineStore('scenes', () => {
  const scenes = ref<LocalSceneView[]>([])
  const currentScene = ref<LocalSceneView | null>(null)
  const availableAgents = ref<AgentView[]>([])
  const agentModelsMap = ref<Record<string, LocalAgentModelsView>>({})
  const isLoading = ref(false)
  const isSaving = ref(false)
  const error = ref<string | null>(null)
  const conflictError = ref<{ currentVersion: number; message: string } | null>(null)
  let generation = 0

  async function fetchScenes(): Promise<void> {
    const currentGeneration = generation
    isLoading.value = true
    error.value = null
    conflictError.value = null
    try {
      const gateway = getLocalChatGateway()
      const [scenesRes, agentsRes] = await Promise.all([
        gateway.listLocalScenes(),
        gateway.listLocalAgents(),
      ])
      if (currentGeneration !== generation) return
      scenes.value = scenesRes
      availableAgents.value = agentsRes
      if (!currentScene.value && scenesRes.length > 0) {
        currentScene.value = JSON.parse(JSON.stringify(scenesRes[0]))
      } else if (currentScene.value) {
        currentScene.value = JSON.parse(JSON.stringify(
          scenesRes.find((s) => s.id === currentScene.value?.id) || scenesRes[0] || null))
      }
    } catch (err: unknown) {
      error.value = err instanceof Error ? err.message : '加载场景列表失败'
    } finally {
      isLoading.value = false
    }
  }

  function selectScene(sceneId: string): void {
    const s = scenes.value.find((sc) => sc.id === sceneId)
    if (s) {
      currentScene.value = JSON.parse(JSON.stringify(s)) // edit buffer
      conflictError.value = null
    }
  }

  async function fetchAgentModels(agentId: string): Promise<LocalAgentModelsView | null> {
    const currentGeneration = generation
    if (!agentId) return null
    if (agentModelsMap.value[agentId]) {
      return agentModelsMap.value[agentId]
    }
    try {
      const gateway = getLocalChatGateway()
      const modelsView = await gateway.getAgentModels(agentId)
      if (currentGeneration !== generation) return null
      agentModelsMap.value[agentId] = modelsView
      return modelsView
    } catch {
      return null
    }
  }

  function reset(): void {
    generation++
    scenes.value = []
    currentScene.value = null
    availableAgents.value = []
    agentModelsMap.value = {}
    error.value = null
    conflictError.value = null
  }

  async function saveScene(
    sceneId: string,
    input: SaveLocalSceneInput
  ): Promise<LocalSceneView> {
    isSaving.value = true
    conflictError.value = null
    error.value = null
    try {
      const gateway = getLocalChatGateway()
      const updated = await gateway.saveLocalScene(sceneId, input)
      const idx = scenes.value.findIndex((s) => s.id === sceneId)
      if (idx !== -1) {
        scenes.value[idx] = updated
      }
      currentScene.value = JSON.parse(JSON.stringify(updated))
      return updated
    } catch (err: unknown) {
      if (err instanceof HubApiError && (err.status === 409 || err.code === 'CONFLICT')) {
        const detail = err.detail as { currentVersion?: number } | undefined
        conflictError.value = {
          currentVersion: detail?.currentVersion ?? (currentScene.value?.version || 1) + 1,
          message: err.message || '配置已在别处被修改，请刷新最新版本后再编辑保存',
        }
      } else {
        error.value = err instanceof Error ? err.message : '保存场景失败'
      }
      throw err
    } finally {
      isSaving.value = false
    }
  }

  return {
    scenes,
    currentScene,
    availableAgents,
    agentModelsMap,
    isLoading,
    isSaving,
    error,
    conflictError,
    fetchScenes,
    selectScene,
    fetchAgentModels,
    saveScene,
    reset,
  }
})
