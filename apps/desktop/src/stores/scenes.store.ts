import { defineStore } from 'pinia'
import { ref } from 'vue'
import type {
  LocalSceneView,
  CreateLocalSceneInput,
  SaveLocalSceneInput,
  LocalRoleTemplateView,
  CreateLocalRoleTemplateInput,
  UpdateLocalRoleTemplateInput,
  LocalAgentModelsView,
  AgentView,
} from '@hqagent/protocol'
import { getLocalChatGateway, HubApiError } from '@/shared/api'
import { completeOperation, definiteRejection, pendingOperation } from '@/shared/api/local-pending-operation'

export const useScenesStore = defineStore('scenes', () => {
  const scenes = ref<LocalSceneView[]>([])
  const currentScene = ref<LocalSceneView | null>(null)
  const roleTemplates = ref<LocalRoleTemplateView[]>([])
  const availableAgents = ref<AgentView[]>([])
  const agentModelsMap = ref<Record<string, LocalAgentModelsView>>({})
  const isLoading = ref(false)
  const isSaving = ref(false)
  const isCreating = ref(false)
  const isTemplateSaving = ref(false)
  const error = ref<string | null>(null)
  const conflictError = ref<{ currentVersion: number; message: string } | null>(null)
  const templateConflictError = ref<{ currentVersion: number; message: string } | null>(null)
  let generation = 0

  async function fetchScenes(rediscover = false): Promise<void> {
    const currentGeneration = generation
    isLoading.value = true
    error.value = null
    conflictError.value = null
    try {
      const gateway = getLocalChatGateway()
      const [scenesRes, templatesRes, agentsRes] = await Promise.all([
        gateway.listLocalScenes(),
        gateway.listLocalRoleTemplates(),
        rediscover ? gateway.discoverLocalAgents().then(result => result.discovered) : gateway.listLocalAgents(),
      ])
      if (currentGeneration !== generation) return
      scenes.value = scenesRes
      roleTemplates.value = templatesRes
      availableAgents.value = agentsRes
      if (rediscover) agentModelsMap.value = {}
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

  async function fetchRoleTemplates(): Promise<void> {
    try {
      roleTemplates.value = await getLocalChatGateway().listLocalRoleTemplates()
      templateConflictError.value = null
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载角色模板失败'
      throw err
    }
  }

  function reset(): void {
    generation++
    scenes.value = []
    currentScene.value = null
    roleTemplates.value = []
    availableAgents.value = []
    agentModelsMap.value = {}
    error.value = null
    conflictError.value = null
    templateConflictError.value = null
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

  async function createScene(input: CreateLocalSceneInput): Promise<LocalSceneView> {
    const identity = `scene:create:${JSON.stringify(input)}`
    const operation = pendingOperation(identity, input)
    isCreating.value = true
    error.value = null
    try {
      const created = await getLocalChatGateway().createLocalScene(operation.payload, operation.id)
      completeOperation(identity)
      scenes.value = [...scenes.value.filter((scene) => scene.id !== created.id), created]
      currentScene.value = JSON.parse(JSON.stringify(created))
      return created
    } catch (err) {
      if (definiteRejection(err)) completeOperation(identity)
      error.value = err instanceof Error ? err.message : '创建场景失败'
      throw err
    } finally {
      isCreating.value = false
    }
  }

  async function createRoleTemplate(
    input: CreateLocalRoleTemplateInput
  ): Promise<LocalRoleTemplateView> {
    const identity = `role-template:create:${JSON.stringify(input)}`
    const operation = pendingOperation(identity, input)
    isTemplateSaving.value = true
    templateConflictError.value = null
    try {
      const created = await getLocalChatGateway().createLocalRoleTemplate(operation.payload, operation.id)
      completeOperation(identity)
      roleTemplates.value = [...roleTemplates.value.filter((item) => item.id !== created.id), created]
      return created
    } catch (err) {
      if (definiteRejection(err)) completeOperation(identity)
      error.value = err instanceof Error ? err.message : '创建角色模板失败'
      throw err
    } finally {
      isTemplateSaving.value = false
    }
  }

  async function updateRoleTemplate(
    templateId: string,
    input: UpdateLocalRoleTemplateInput
  ): Promise<LocalRoleTemplateView> {
    const identity = `role-template:update:${templateId}:${JSON.stringify(input)}`
    const operation = pendingOperation(identity, input)
    isTemplateSaving.value = true
    templateConflictError.value = null
    try {
      const updated = await getLocalChatGateway().updateLocalRoleTemplate(
        templateId,
        operation.payload,
        operation.id
      )
      completeOperation(identity)
      roleTemplates.value = roleTemplates.value.map((item) => item.id === templateId ? updated : item)
      return updated
    } catch (err) {
      if (definiteRejection(err)) completeOperation(identity)
      if (err instanceof HubApiError && (err.status === 409 || err.code === 'CONFLICT')) {
        const detail = err.detail as { currentVersion?: number } | undefined
        templateConflictError.value = {
          currentVersion: detail?.currentVersion ?? input.expectedVersion + 1,
          message: err.message || '角色模板已在其他窗口修改，请刷新后重试',
        }
      } else {
        error.value = err instanceof Error ? err.message : '更新角色模板失败'
      }
      throw err
    } finally {
      isTemplateSaving.value = false
    }
  }

  return {
    scenes,
    currentScene,
    roleTemplates,
    availableAgents,
    agentModelsMap,
    isLoading,
    isSaving,
    isCreating,
    isTemplateSaving,
    error,
    conflictError,
    templateConflictError,
    fetchScenes,
    selectScene,
    fetchAgentModels,
    fetchRoleTemplates,
    saveScene,
    createScene,
    createRoleTemplate,
    updateRoleTemplate,
    reset,
  }
})
