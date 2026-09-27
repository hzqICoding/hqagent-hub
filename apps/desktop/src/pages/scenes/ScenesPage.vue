<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type {
  LocalBaseRoleId,
  LocalRoleConfig,
  LocalRoleTemplateView,
  ReviewMode,
} from '@hqagent/protocol'
import { useScenesStore } from '@/stores/scenes.store'
import {
  HqBadge,
  HqButton,
  HqDialog,
  HqInput,
  HqRadioGroup,
  HqSelect,
  HqSwitch,
  HqTextarea,
  useToast,
} from '@/shared/ui'
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Info,
  Library,
  Lock,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Trash2,
} from 'lucide-vue-next'

const scenesStore = useScenesStore()
const toast = useToast()

const baseRoleIds: LocalBaseRoleId[] = ['analyst', 'planner', 'developer', 'reviewer']
const builtinSceneIds = new Set(['analyze', 'plan', 'develop'])
const selectedSceneId = ref('')
const editableRoles = ref<LocalRoleConfig[]>([])
const sceneName = ref('')
const sceneDescription = ref('')
const reviewMode = ref<ReviewMode>('independent')
const localValidationError = ref<string | null>(null)
const stageSelection = ref('')

const isCreateSceneOpen = ref(false)
const newSceneName = ref('')
const newSceneDescription = ref('')
const newSceneSource = ref<'blank' | 'copy'>('blank')
const createSceneError = ref<string | null>(null)

const isTemplateManagerOpen = ref(false)
const selectedTemplateId = ref<'new' | string>('new')
const templateName = ref('')
const templateBaseRoleId = ref<LocalBaseRoleId>('analyst')
const templateInstructions = ref('')
const templateError = ref<string | null>(null)

const currentSourceScene = computed(() =>
  scenesStore.scenes.find((scene) => scene.id === selectedSceneId.value) || null
)
const isBuiltinScene = computed(() => {
  const scene = currentSourceScene.value
  return Boolean(scene && (scene.isBuiltin ?? builtinSceneIds.has(scene.id)))
})
const isCustomScene = computed(() => Boolean(currentSourceScene.value) && !isBuiltinScene.value)
const usesOriginalPlannerReview = computed(() => reviewMode.value === 'original_planner')
const showReviewMode = computed(() =>
  isCustomScene.value
    || editableRoles.value.some((role) => role.roleId === 'developer' || role.roleId === 'reviewer')
)

const originalPlannerValidationError = computed(() => {
  if (!usesOriginalPlannerReview.value) return null
  const planner = findRole('planner')
  const developer = findRole('developer')
  const reviewer = findRole('reviewer')
  if (!planner?.enabled || !developer?.enabled || !reviewer?.enabled) {
    return '原规划者验收需要启用 Planner、Developer 与 Reviewer。'
  }
  if (isCustomScene.value) {
    const enabledIds = editableRoles.value.filter((role) => role.enabled).map((role) => role.roleId)
    if (enabledIds.join(',') !== 'planner,developer,reviewer') {
      return '自定义场景的原规划者验收要求启用顺序严格为 Planner → Developer → Reviewer。'
    }
  }
  if (!planner.agentInstanceId?.trim()) {
    return '原规划者验收需要先为 Planner 配置执行 Agent。'
  }
  return null
})

const sceneValidationError = computed(() => {
  if (!currentSourceScene.value) return null
  if (editableRoles.value.length < 1 || editableRoles.value.length > 4) {
    return '场景需要配置 1 到 4 个顺序阶段。'
  }
  if (new Set(editableRoles.value.map((role) => role.roleId)).size !== editableRoles.value.length) {
    return '同一基础角色在场景中最多出现一次。'
  }
  if (!editableRoles.value.some((role) => role.enabled)) {
    return '场景至少需要一个启用阶段。'
  }
  const missingAgent = editableRoles.value.find((role) => role.enabled && !role.agentInstanceId.trim())
  if (missingAgent) return `${roleDisplayName(missingAgent)} 尚未配置执行 Agent。`
  if (isCustomScene.value && !sceneName.value.trim()) return '自定义场景名称不能为空。'
  return originalPlannerValidationError.value
})

const displayedValidationError = computed(
  () => localValidationError.value ?? sceneValidationError.value
)

const reviewModeOptions = [
  {
    label: '独立 Reviewer',
    value: 'independent',
    description: 'Reviewer 使用自己的 Agent、模型与会话独立审查。',
  },
  {
    label: '原规划者验收',
    value: 'original_planner',
    description: '开发完成后恢复本轮 Planner 原生会话，按冻结证据验收。',
  },
]

const newSceneSourceOptions = [
  {
    label: '空白场景',
    value: 'blank',
    description: '从一个 Analyst 阶段开始，再按执行顺序添加阶段。',
  },
  {
    label: '复制当前场景',
    value: 'copy',
    description: '复制当前阶段、Agent 与职责，保存为互不联动的自定义副本。',
  },
]

const stageOptions = computed(() => {
  const used = new Set(editableRoles.value.map((role) => role.roleId))
  const baseOptions = baseRoleIds.map((roleId) => ({
    label: `基础角色 · ${roleMeta(roleId).title}`,
    value: `base:${roleId}`,
    disabled: used.has(roleId),
  }))
  const templateOptions = scenesStore.roleTemplates.map((template) => ({
    label: `角色模板 · ${template.name}（${roleMeta(template.baseRoleId).shortTitle}）`,
    value: `template:${template.id}`,
    disabled: used.has(template.baseRoleId),
  }))
  return [...baseOptions, ...templateOptions]
})

onMounted(async () => {
  await scenesStore.fetchScenes()
  if (scenesStore.scenes.length > 0) {
    selectedSceneId.value = scenesStore.scenes[0].id
    syncEditBuffer()
  }
})

watch(selectedSceneId, syncEditBuffer)
watch(editableRoles, applyOriginalPlannerInheritance, { deep: true })

function syncEditBuffer() {
  const scene = currentSourceScene.value
  if (!scene) return
  scenesStore.selectScene(scene.id)
  sceneName.value = scene.name
  sceneDescription.value = scene.description
  editableRoles.value = JSON.parse(JSON.stringify(scene.roles))
  reviewMode.value = scene.reviewMode ?? 'independent'
  localValidationError.value = null
  stageSelection.value = ''
  applyOriginalPlannerInheritance()
  for (const role of editableRoles.value) {
    if (role.agentInstanceId) void scenesStore.fetchAgentModels(role.agentInstanceId)
  }
}

function findRole(roleId: string) {
  return editableRoles.value.find((role) => role.roleId === roleId)
}

function roleMeta(roleId: string) {
  switch (roleId) {
    case 'analyst':
      return {
        title: '代码分析 (Analyst)',
        shortTitle: 'Analyst',
        description: '只读梳理代码、依赖与问题边界。',
        readOnly: true,
        defaultInstructions: '分析现有代码与依赖，梳理事实、风险与约束。',
      }
    case 'planner':
      return {
        title: '需求规划 (Planner)',
        shortTitle: 'Planner',
        description: '只读形成实施方案、阶段与验收标准。',
        readOnly: true,
        defaultInstructions: '输出可执行计划、接口影响、风险与验收标准。',
      }
    case 'developer':
      return {
        title: '项目开发 (Developer)',
        shortTitle: 'Developer',
        description: '在授权工作树中实施代码与验证。',
        readOnly: false,
        defaultInstructions: '按计划实施代码修改并完成必要验证。',
      }
    case 'reviewer':
      return {
        title: usesOriginalPlannerReview.value ? '验收阶段 (Reviewer)' : '代码审查 (Reviewer)',
        shortTitle: 'Reviewer',
        description: usesOriginalPlannerReview.value
          ? '验收身份继承 Planner 的 Agent、模型与原生会话。'
          : '独立检查实现质量、安全边界与验收证据。',
        readOnly: true,
        defaultInstructions: '依据验收标准检查变更、风险与证据并给出结论。',
      }
    default:
      return {
        title: roleId,
        shortTitle: roleId,
        description: '自定义场景阶段。',
        readOnly: false,
        defaultInstructions: '',
      }
  }
}

function roleDisplayName(role: LocalRoleConfig) {
  return role.roleName?.trim() || roleMeta(role.roleId).title
}

function isRoleOptional(role: LocalRoleConfig) {
  if (isCustomScene.value) return true
  if (role.roleId === 'reviewer') return true
  return currentSourceScene.value?.id === 'develop' && role.roleId === 'planner'
}

function isRequiredByOriginalPlanner(role: LocalRoleConfig) {
  return usesOriginalPlannerReview.value
    && ['planner', 'developer', 'reviewer'].includes(role.roleId)
}

function applyOriginalPlannerInheritance() {
  if (!usesOriginalPlannerReview.value) return
  const planner = findRole('planner')
  const developer = findRole('developer')
  const reviewer = findRole('reviewer')
  if (!planner || !developer || !reviewer) return
  planner.enabled = true
  developer.enabled = true
  reviewer.enabled = true
  reviewer.agentInstanceId = planner.agentInstanceId
  reviewer.modelId = planner.modelId
  reviewer.reasoningEffort = planner.reasoningEffort
}

function handleReviewModeChange(value: string | number) {
  reviewMode.value = value as ReviewMode
  localValidationError.value = null
  applyOriginalPlannerInheritance()
}

function handleRoleEnabledChange(role: LocalRoleConfig, enabled: boolean) {
  localValidationError.value = null
  if (!enabled && isRequiredByOriginalPlanner(role)) {
    role.enabled = true
    localValidationError.value = '原规划者验收要求 Planner、Developer、Reviewer 保持启用。'
    return
  }
  role.enabled = enabled
  applyOriginalPlannerInheritance()
}

function handleAgentChange(role: LocalRoleConfig, agentId: string) {
  role.agentInstanceId = agentId
  role.modelId = ''
  role.reasoningEffort = ''
  if (agentId) void scenesStore.fetchAgentModels(agentId)
}

function selectedModel(role: LocalRoleConfig) {
  return scenesStore.agentModelsMap[role.agentInstanceId]?.models.find((model) => model.id === role.modelId)
}

function effortOptions(role: LocalRoleConfig) {
  return [
    { label: '继承 Runtime 默认', value: '' },
    ...(selectedModel(role)?.efforts || []).map((effort) => ({ label: effort, value: effort })),
  ]
}

function makeBaseRole(roleId: LocalBaseRoleId): LocalRoleConfig {
  return {
    roleId,
    roleName: roleMeta(roleId).title,
    agentInstanceId: scenesStore.availableAgents[0]?.id || '',
    instructions: roleMeta(roleId).defaultInstructions,
    enabled: true,
  }
}

function addStage() {
  if (!stageSelection.value || editableRoles.value.length >= 4) return
  const [kind, id] = stageSelection.value.split(':', 2)
  let role: LocalRoleConfig | null = null
  if (kind === 'base' && baseRoleIds.includes(id as LocalBaseRoleId)) {
    role = makeBaseRole(id as LocalBaseRoleId)
  } else if (kind === 'template') {
    const template = scenesStore.roleTemplates.find((item) => item.id === id)
    if (template) {
      role = {
        ...makeBaseRole(template.baseRoleId),
        roleName: template.name,
        instructions: template.instructions,
        roleTemplateId: template.id,
        roleTemplateVersion: template.version,
      }
    }
  }
  if (!role || editableRoles.value.some((item) => item.roleId === role!.roleId)) return
  editableRoles.value.push(role)
  stageSelection.value = ''
  applyOriginalPlannerInheritance()
}

function moveStage(index: number, direction: -1 | 1) {
  const target = index + direction
  if (target < 0 || target >= editableRoles.value.length) return
  const copy = [...editableRoles.value]
  ;[copy[index], copy[target]] = [copy[target], copy[index]]
  editableRoles.value = copy
}

function removeStage(index: number) {
  const role = editableRoles.value[index]
  if (role && isRequiredByOriginalPlanner(role)) {
    localValidationError.value = '请先切换为独立 Reviewer，再移除原规划者验收需要的阶段。'
    return
  }
  editableRoles.value.splice(index, 1)
}

async function handleSave() {
  const current = scenesStore.currentScene
  if (!current || sceneValidationError.value) {
    localValidationError.value = sceneValidationError.value
    return
  }
  applyOriginalPlannerInheritance()
  try {
    await scenesStore.saveScene(current.id, {
      roles: editableRoles.value,
      expectedVersion: current.version,
      reviewMode: reviewMode.value,
      ...(isCustomScene.value
        ? { name: sceneName.value.trim(), description: sceneDescription.value.trim() }
        : {}),
    })
    syncEditBuffer()
    toast.success('场景配置已保存，后续新 Run 将使用新快照。')
  } catch {
    // Store exposes conflict/error state.
  }
}

async function handleRefresh() {
  await scenesStore.fetchScenes(true)
  if (!scenesStore.scenes.some((scene) => scene.id === selectedSceneId.value)) {
    selectedSceneId.value = scenesStore.scenes[0]?.id || ''
  }
  syncEditBuffer()
}

function openCreateSceneDialog() {
  newSceneName.value = ''
  newSceneDescription.value = ''
  newSceneSource.value = currentSourceScene.value ? 'copy' : 'blank'
  createSceneError.value = null
  isCreateSceneOpen.value = true
}

async function createScene() {
  if (!newSceneName.value.trim()) return
  const roles = newSceneSource.value === 'copy' && currentSourceScene.value
    ? JSON.parse(JSON.stringify(editableRoles.value))
    : [makeBaseRole('analyst')]
  const copiedEnabledOrder = (roles as LocalRoleConfig[])
    .filter((role) => role.enabled)
    .map((role) => role.roleId)
    .join(',')
  const copiedReviewMode = newSceneSource.value === 'copy'
    && reviewMode.value === 'original_planner'
    && copiedEnabledOrder === 'planner,developer,reviewer'
      ? 'original_planner'
      : 'independent'
  try {
    const created = await scenesStore.createScene({
      name: newSceneName.value.trim(),
      description: newSceneDescription.value.trim(),
      roles,
      reviewMode: copiedReviewMode,
    })
    selectedSceneId.value = created.id
    isCreateSceneOpen.value = false
    syncEditBuffer()
  } catch (error) {
    createSceneError.value = error instanceof Error ? error.message : '创建场景失败'
  }
}

function openTemplateManager() {
  isTemplateManagerOpen.value = true
  selectTemplate(scenesStore.roleTemplates[0]?.id || 'new')
}

function selectTemplate(templateId: string) {
  selectedTemplateId.value = templateId
  templateError.value = null
  const template = scenesStore.roleTemplates.find((item) => item.id === templateId)
  if (template) {
    templateName.value = template.name
    templateBaseRoleId.value = template.baseRoleId
    templateInstructions.value = template.instructions
  } else {
    selectedTemplateId.value = 'new'
    templateName.value = ''
    templateBaseRoleId.value = 'analyst'
    templateInstructions.value = ''
  }
}

async function saveTemplate() {
  if (!templateName.value.trim()) return
  try {
    let saved: LocalRoleTemplateView
    if (selectedTemplateId.value === 'new') {
      saved = await scenesStore.createRoleTemplate({
        name: templateName.value.trim(),
        baseRoleId: templateBaseRoleId.value,
        instructions: templateInstructions.value,
      })
    } else {
      const current = scenesStore.roleTemplates.find((item) => item.id === selectedTemplateId.value)
      if (!current) return
      saved = await scenesStore.updateRoleTemplate(current.id, {
        expectedVersion: current.version,
        name: templateName.value.trim(),
        instructions: templateInstructions.value,
      })
    }
    selectTemplate(saved.id)
  } catch (error) {
    templateError.value = error instanceof Error ? error.message : '保存模板失败'
  }
}

async function refreshTemplates() {
  const selected = selectedTemplateId.value
  await scenesStore.fetchRoleTemplates()
  selectTemplate(
    selected !== 'new' && scenesStore.roleTemplates.some((item) => item.id === selected)
      ? selected
      : scenesStore.roleTemplates[0]?.id || 'new'
  )
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg-app overflow-hidden">
    <div class="px-3 sm:px-4 py-2 bg-panel-header border-b border-border flex items-center justify-between gap-2 sm:gap-3 text-xs text-text flex-wrap">
      <div class="flex items-center gap-2 min-w-0">
        <Info class="w-4 h-4 text-primary shrink-0" />
        <span class="font-medium text-text">场景与角色配置</span>
        <span class="text-text-muted hidden md:inline truncate">
          场景按顺序执行阶段；模板应用后保存为副本，不会随模板更新。
        </span>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <HqButton size="sm" variant="secondary" class="min-h-[36px] sm:min-h-0" @click="openTemplateManager">
          <Library class="w-3.5 h-3.5 mr-1" />
          角色模板
        </HqButton>
        <HqButton size="sm" variant="secondary" class="min-h-[36px] sm:min-h-0" @click="handleRefresh">
          <RefreshCw class="w-3.5 h-3.5 mr-1" />
          刷新配置
        </HqButton>
      </div>
    </div>

    <div class="flex-1 flex flex-col md:flex-row overflow-hidden">
      <aside class="w-full md:w-64 border-b md:border-b-0 md:border-r border-border bg-panel p-2.5 sm:p-3 shrink-0 select-none overflow-y-auto">
        <div class="flex items-center justify-between gap-2 px-1 mb-2 sm:mb-3">
          <h3 class="text-xs font-semibold text-text">场景清单</h3>
          <HqButton size="sm" variant="primary" class="min-h-[36px] sm:min-h-0" @click="openCreateSceneDialog">
            <Plus class="w-3.5 h-3.5 mr-1" />
            新建
          </HqButton>
        </div>
        <div class="flex flex-row md:flex-col gap-2 overflow-x-auto md:overflow-x-visible pb-1 md:pb-0">
          <button
            v-for="scene in scenesStore.scenes"
            :key="scene.id"
            type="button"
            class="w-52 sm:w-60 md:w-full p-2.5 sm:p-3 rounded-[var(--radius-md)] border text-left transition-all space-y-1.5 shrink-0 cursor-pointer"
            :class="selectedSceneId === scene.id
              ? 'border-primary bg-primary/10 shadow-xs'
              : 'border-border bg-bg-app hover:border-border-strong'"
            @click="selectedSceneId = scene.id"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="font-medium text-xs text-text truncate">{{ scene.name }}</span>
              <HqBadge size="sm" :variant="(scene.isBuiltin ?? builtinSceneIds.has(scene.id)) ? 'neutral' : 'primary'">
                {{ (scene.isBuiltin ?? builtinSceneIds.has(scene.id)) ? '内置' : '自定义' }}
              </HqBadge>
            </div>
            <p class="text-[11px] text-text-muted leading-relaxed line-clamp-2">{{ scene.description }}</p>
            <div class="flex items-center justify-between text-[10px] text-text-muted pt-1 border-t border-border/50">
              <span>v{{ scene.version }}</span>
              <span>{{ scene.roles.length }} 个阶段</span>
            </div>
          </button>
        </div>
      </aside>

      <main class="flex-1 flex flex-col overflow-hidden bg-bg-app">
        <header class="p-3 sm:p-4 border-b border-border bg-panel flex items-center justify-between gap-2 sm:gap-4 shrink-0 flex-wrap">
          <div v-if="scenesStore.currentScene" class="min-w-0">
            <div class="flex items-center gap-2 mb-1 flex-wrap">
              <h2 class="text-sm font-semibold text-text truncate">{{ sceneName }}</h2>
              <span class="font-mono text-xs text-text-muted">v{{ scenesStore.currentScene.version }}</span>
              <HqBadge size="sm" :variant="isBuiltinScene ? 'neutral' : 'primary'">
                {{ isBuiltinScene ? '内置场景' : '自定义场景' }}
              </HqBadge>
            </div>
            <p class="text-xs text-text-muted truncate">{{ sceneDescription }}</p>
          </div>
          <HqButton
            v-if="scenesStore.currentScene"
            variant="primary"
            size="sm"
            class="min-h-[44px] sm:min-h-0"
            :disabled="scenesStore.isSaving || Boolean(sceneValidationError)"
            :loading="scenesStore.isSaving"
            @click="handleSave"
          >
            <Save class="w-3.5 h-3.5 mr-1.5" />
            保存场景配置
          </HqButton>
        </header>

        <div
          v-if="scenesStore.conflictError"
          class="m-4 mb-0 p-3 rounded-[var(--radius-md)] bg-danger/10 border border-danger/30 text-xs text-danger flex items-center justify-between gap-3"
        >
          <span>{{ scenesStore.conflictError.message }}</span>
          <HqButton size="sm" variant="secondary" @click="handleRefresh">拉取最新版本</HqButton>
        </div>
        <div
          v-if="displayedValidationError"
          class="mx-4 mt-4 p-3 rounded-[var(--radius-md)] bg-danger/10 border border-danger/30 text-xs text-danger flex items-center gap-2"
        >
          <AlertCircle class="w-4 h-4 shrink-0" />
          <span>{{ displayedValidationError }}</span>
        </div>

        <div v-if="scenesStore.currentScene" class="flex-1 overflow-y-auto p-4 space-y-4">
          <section
            v-if="isCustomScene"
            class="p-4 rounded-[var(--radius-lg)] border border-border bg-panel shadow-xs space-y-3"
          >
            <div>
              <h3 class="text-xs font-semibold text-text">场景信息</h3>
              <p class="text-[11px] text-text-muted mt-1">名称和说明只影响场景展示，执行权限仍由每个阶段的基础角色决定。</p>
            </div>
            <HqInput v-model="sceneName" placeholder="场景名称" :maxlength="120" />
            <HqTextarea v-model="sceneDescription" :rows="2" :maxlength="2000" placeholder="说明适用范围与预期产出" />
          </section>

          <section
            v-if="showReviewMode"
            class="p-4 rounded-[var(--radius-lg)] border border-border bg-panel shadow-xs space-y-3"
          >
            <div>
              <h3 class="text-xs font-semibold text-text">验收方式</h3>
              <p class="text-[11px] text-text-muted mt-1">配置会冻结到新 Run；模板和场景后续修改不会改写历史快照。</p>
            </div>
            <HqRadioGroup
              :model-value="reviewMode"
              :options="reviewModeOptions"
              @update:model-value="handleReviewModeChange"
            />
            <div
              v-if="usesOriginalPlannerReview"
              class="p-2.5 rounded-[var(--radius-sm)] bg-primary/10 border border-primary/20 text-[11px] text-text"
            >
              Reviewer 的 Agent、Model 与 Reasoning Effort 继承 Planner；自定义场景的启用阶段必须严格为 Planner → Developer → Reviewer。
            </div>
          </section>

          <section
            v-for="(role, index) in editableRoles"
            :key="`${role.roleId}:${index}`"
            :data-role-id="role.roleId"
            class="p-4 rounded-[var(--radius-lg)] border border-border bg-panel shadow-xs space-y-3"
          >
            <div class="flex items-start justify-between gap-3 pb-2 border-b border-border">
              <div class="flex items-start gap-2 min-w-0">
                <span class="w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-xs shrink-0">
                  {{ index + 1 }}
                </span>
                <div class="min-w-0">
                  <h4 class="text-xs font-semibold text-text truncate">{{ roleDisplayName(role) }}</h4>
                  <p class="text-[11px] text-text-muted">{{ roleMeta(role.roleId).description }}</p>
                  <p v-if="role.roleTemplateId" class="text-[10px] text-primary mt-1">
                    来自角色模板 v{{ role.roleTemplateVersion }}；当前职责是独立副本
                  </p>
                </div>
              </div>
              <div class="flex items-center gap-1.5 shrink-0">
                <HqBadge v-if="roleMeta(role.roleId).readOnly" variant="info" size="sm">
                  <Lock class="w-3 h-3 mr-1" />
                  只读权限
                </HqBadge>
                <template v-if="isCustomScene">
                  <button type="button" class="min-w-[36px] min-h-[36px] p-2 rounded hover:bg-muted text-text-muted flex items-center justify-center cursor-pointer" title="上移阶段" aria-label="上移阶段" :disabled="index === 0" @click="moveStage(index, -1)">
                    <ArrowUp class="w-3.5 h-3.5" />
                  </button>
                  <button type="button" class="min-w-[36px] min-h-[36px] p-2 rounded hover:bg-muted text-text-muted flex items-center justify-center cursor-pointer" title="下移阶段" aria-label="下移阶段" :disabled="index === editableRoles.length - 1" @click="moveStage(index, 1)">
                    <ArrowDown class="w-3.5 h-3.5" />
                  </button>
                  <button type="button" class="min-w-[36px] min-h-[36px] p-2 rounded hover:bg-danger/10 text-danger flex items-center justify-center cursor-pointer" title="移除阶段" aria-label="移除阶段" @click="removeStage(index)">
                    <Trash2 class="w-3.5 h-3.5" />
                  </button>
                </template>
                <div v-if="isRoleOptional(role)" class="flex items-center gap-1.5 ml-1">
                  <span class="text-[11px] text-text-muted">启用</span>
                  <HqSwitch
                    :model-value="role.enabled"
                    :disabled="isRequiredByOriginalPlanner(role)"
                    @update:model-value="(value) => handleRoleEnabledChange(role, value)"
                  />
                </div>
              </div>
            </div>

            <div v-if="isCustomScene" class="text-xs">
              <label class="block font-medium text-text mb-1">阶段显示名称</label>
              <HqInput v-model="role.roleName" :placeholder="roleMeta(role.roleId).title" :maxlength="120" />
              <p class="text-[10px] text-text-muted mt-1">基础权限类型保持为 {{ roleMeta(role.roleId).shortTitle }}，显示名称不会改变权限。</p>
            </div>

            <div v-if="role.enabled" class="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
              <div>
                <label class="block font-medium text-text mb-1">执行 Agent <span class="text-danger">*</span></label>
                <HqSelect
                  :model-value="role.agentInstanceId"
                  :disabled="usesOriginalPlannerReview && role.roleId === 'reviewer'"
                  :options="scenesStore.availableAgents.map((agent) => ({
                    label: `${agent.displayName} (${agent.adapterId})`,
                    value: agent.id,
                  }))"
                  placeholder="选择本地 Agent"
                  @update:model-value="(value) => handleAgentChange(role, value as string)"
                />
              </div>
              <div>
                <label class="block font-medium text-text mb-1">模型规格</label>
                <HqSelect
                  v-if="scenesStore.agentModelsMap[role.agentInstanceId]?.verified
                    && (scenesStore.agentModelsMap[role.agentInstanceId]?.models.length || 0) > 0"
                  v-model="role.modelId"
                  :disabled="usesOriginalPlannerReview && role.roleId === 'reviewer'"
                  :options="(scenesStore.agentModelsMap[role.agentInstanceId]?.models || []).map((model) => ({
                    label: `${model.name} (${model.id})`,
                    value: model.id,
                  }))"
                  placeholder="选择模型"
                  @update:model-value="role.reasoningEffort = ''"
                />
                <HqInput
                  v-else
                  v-model="role.modelId"
                  :disabled="usesOriginalPlannerReview && role.roleId === 'reviewer'"
                  placeholder="留空继承 Agent 默认模型"
                />
              </div>
              <div>
                <label class="block font-medium text-text mb-1">思考强度</label>
                <HqSelect
                  v-if="selectedModel(role)"
                  v-model="role.reasoningEffort"
                  :disabled="usesOriginalPlannerReview && role.roleId === 'reviewer'"
                  :options="effortOptions(role)"
                  placeholder="继承默认"
                />
                <HqInput
                  v-else
                  v-model="role.reasoningEffort"
                  :disabled="usesOriginalPlannerReview && role.roleId === 'reviewer'"
                  placeholder="留空继承 Runtime 默认"
                />
              </div>
            </div>

            <div v-if="role.enabled">
              <label class="block font-medium text-text text-xs mb-1">角色职责与约束</label>
              <HqTextarea v-model="role.instructions" :rows="4" :maxlength="12000" show-count />
            </div>
          </section>

          <section
            v-if="isCustomScene"
            class="p-4 rounded-[var(--radius-lg)] border border-dashed border-border bg-panel/60 space-y-3"
          >
            <div>
              <h3 class="text-xs font-semibold text-text">添加顺序阶段</h3>
              <p class="text-[11px] text-text-muted mt-1">每种基础角色最多一次。模板只复制名称、职责和来源版本。</p>
            </div>
            <div class="flex items-center gap-2">
              <HqSelect v-model="stageSelection" :options="stageOptions" placeholder="选择基础角色或角色模板" />
              <HqButton size="sm" variant="secondary" :disabled="!stageSelection || editableRoles.length >= 4" @click="addStage">
                <Plus class="w-3.5 h-3.5 mr-1" />
                添加阶段
              </HqButton>
            </div>
          </section>
        </div>
      </main>
    </div>

    <HqDialog
      :open="isCreateSceneOpen"
      title="新建自定义场景"
      description="创建后可继续增减阶段、调整顺序和配置 Agent"
      @close="isCreateSceneOpen = false"
    >
      <div class="space-y-4 text-xs">
        <div>
          <label class="block font-medium text-text mb-1">场景名称</label>
          <HqInput v-model="newSceneName" placeholder="例如：RTK 模块开发与验收" autofocus />
        </div>
        <div>
          <label class="block font-medium text-text mb-1">场景说明</label>
          <HqTextarea v-model="newSceneDescription" :rows="3" placeholder="说明适用范围和预期产出" />
        </div>
        <HqRadioGroup v-model="newSceneSource" :options="newSceneSourceOptions" />
        <p v-if="createSceneError" role="alert" class="text-danger">{{ createSceneError }}</p>
      </div>
      <template #footer>
        <HqButton size="sm" variant="secondary" @click="isCreateSceneOpen = false">取消</HqButton>
        <HqButton size="sm" variant="primary" :loading="scenesStore.isCreating" :disabled="!newSceneName.trim() || scenesStore.isCreating" @click="createScene">
          创建场景
        </HqButton>
      </template>
    </HqDialog>

    <HqDialog
      :open="isTemplateManagerOpen"
      title="角色模板管理"
      description="模板继承基础角色权限；应用到场景后成为可独立修改的副本"
      width="760px"
      @close="isTemplateManagerOpen = false"
    >
      <div class="grid grid-cols-[220px_1fr] gap-4 min-h-[360px]">
        <aside class="border-r border-border pr-3 space-y-2">
          <HqButton size="sm" variant="secondary" class="w-full" @click="selectTemplate('new')">
            <Plus class="w-3.5 h-3.5 mr-1" />
            新建模板
          </HqButton>
          <button
            v-for="template in scenesStore.roleTemplates"
            :key="template.id"
            type="button"
            class="w-full rounded-lg border p-2.5 text-left"
            :class="selectedTemplateId === template.id ? 'border-primary bg-primary/10' : 'border-border hover:border-border-strong'"
            @click="selectTemplate(template.id)"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs font-medium text-text truncate">{{ template.name }}</span>
              <span class="text-[10px] text-text-muted">v{{ template.version }}</span>
            </div>
            <p class="text-[10px] text-text-muted mt-1">{{ roleMeta(template.baseRoleId).shortTitle }}</p>
          </button>
        </aside>
        <div class="space-y-4">
          <div>
            <label class="block font-medium text-text mb-1">模板名称</label>
            <HqInput v-model="templateName" placeholder="例如：RTK 安全审查员" autofocus />
          </div>
          <div>
            <label class="block font-medium text-text mb-1">基础角色类型</label>
            <HqSelect
              v-model="templateBaseRoleId"
              :disabled="selectedTemplateId !== 'new'"
              :options="baseRoleIds.map((roleId) => ({ label: roleMeta(roleId).title, value: roleId }))"
            />
            <p class="text-[10px] text-text-muted mt-1">基础类型决定运行权限，模板更新时不可更改。</p>
          </div>
          <div>
            <label class="block font-medium text-text mb-1">默认职责</label>
            <HqTextarea v-model="templateInstructions" :rows="7" :maxlength="12000" show-count />
          </div>
          <div v-if="scenesStore.templateConflictError" class="p-2.5 rounded bg-danger/10 text-danger text-xs flex items-center justify-between gap-2">
            <span>{{ scenesStore.templateConflictError.message }}</span>
            <HqButton size="sm" variant="secondary" @click="refreshTemplates">刷新模板</HqButton>
          </div>
          <p v-if="templateError" role="alert" class="text-danger text-xs">{{ templateError }}</p>
        </div>
      </div>
      <template #footer>
        <HqButton size="sm" variant="secondary" @click="isTemplateManagerOpen = false">关闭</HqButton>
        <HqButton size="sm" variant="primary" :loading="scenesStore.isTemplateSaving" :disabled="!templateName.trim() || scenesStore.isTemplateSaving" @click="saveTemplate">
          <Pencil v-if="selectedTemplateId !== 'new'" class="w-3.5 h-3.5 mr-1" />
          <Plus v-else class="w-3.5 h-3.5 mr-1" />
          {{ selectedTemplateId === 'new' ? '创建模板' : '保存模板' }}
        </HqButton>
      </template>
    </HqDialog>
  </div>
</template>
