<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useScenesStore } from '@/stores/scenes.store'
import type { LocalRoleConfig } from '@hqagent/protocol'
import {
  HqButton,
  HqBadge,
  HqSelect,
  HqSwitch,
  HqTextarea,
  useToast,
} from '@/shared/ui'
import {
  Save,
  RefreshCw,
  AlertCircle,
  Lock,
  Info,
} from 'lucide-vue-next'

const scenesStore = useScenesStore()
const toast = useToast()

const selectedSceneId = ref<string>('develop')

// Local edit buffer for roles
const editableRoles = ref<LocalRoleConfig[]>([])

onMounted(async () => {
  await scenesStore.fetchScenes()
  if (scenesStore.scenes.length > 0) {
    selectedSceneId.value = scenesStore.scenes[0].id
    syncEditBuffer()
  }
})

watch(selectedSceneId, () => {
  syncEditBuffer()
})

function syncEditBuffer() {
  const scene = scenesStore.scenes.find((s) => s.id === selectedSceneId.value)
  if (scene) {
    scenesStore.selectScene(scene.id)
    editableRoles.value = JSON.parse(JSON.stringify(scene.roles))
    // Prefetch models for agents
    editableRoles.value.forEach((r) => {
      if (r.agentInstanceId) {
        scenesStore.fetchAgentModels(r.agentInstanceId)
      }
    })
  }
}

function handleAgentChange(role: LocalRoleConfig, agentId: string) {
  role.agentInstanceId = agentId
  role.modelId = ''
  role.reasoningEffort = ''
  if (agentId) {
    scenesStore.fetchAgentModels(agentId)
  }
}

async function handleSave() {
  const current = scenesStore.currentScene
  if (!current) return

  try {
    await scenesStore.saveScene(current.id, {
      roles: editableRoles.value,
      expectedVersion: current.version,
    })
    toast.success('场景配置保存成功！后续新建的 Run 将自动应用此配置。')
  } catch {
    // Conflict or other errors handled in store & template
  }
}

async function handleRefresh() {
  await scenesStore.fetchScenes()
  syncEditBuffer()
}

function getRoleMeta(roleId: string) {
  switch (roleId) {
    case 'analyst':
      return {
        title: '代码分析 (Analyst)',
        desc: '只读梳理代码与依赖链路，不得授予文件写权限',
        isReadOnly: true,
        isOptional: false,
      }
    case 'planner':
      return {
        title: '需求规划 (Planner)',
        desc: '只读分析需求并输出落地实施方案，不修改业务文件',
        isReadOnly: true,
        isOptional: selectedSceneId.value === 'develop',
      }
    case 'developer':
      return {
        title: '项目开发 (Developer)',
        desc: '在授权工作树执行代码修改与测试验证',
        isReadOnly: false,
        isOptional: false,
      }
    case 'reviewer':
      return {
        title: '代码审查 (Reviewer)',
        desc: '对 git diff 实施坏味道、越界与安全审查（可选角色）',
        isReadOnly: true,
        isOptional: true,
      }
    default:
      return {
        title: roleId,
        desc: '自定义场景角色',
        isReadOnly: false,
        isOptional: true,
      }
  }
}

function selectedModel(role: LocalRoleConfig) {
  return scenesStore.agentModelsMap[role.agentInstanceId]?.models.find(model => model.id === role.modelId)
}

function effortOptions(role: LocalRoleConfig) {
  return [{ label: '继承 Runtime 默认', value: '' },
    ...(selectedModel(role)?.efforts || []).map(effort => ({ label: effort, value: effort }))]
}
</script>

<template>
  <div class="h-full flex flex-col bg-bg-app overflow-hidden">
    <!-- Notice Banner -->
    <div class="px-4 py-2 bg-panel-header border-b border-border flex items-center justify-between text-xs text-text">
      <div class="flex items-center gap-2">
        <Info class="w-4 h-4 text-primary shrink-0" />
        <span class="font-medium text-text">场景与角色配置 (N0 Local Scenes)</span>
        <span class="text-text-muted hidden md:inline">
          — 修改配置仅对后续新建的 Run 生效；已运行的消息始终保留其自身的场景快照 (sceneSnapshot)。
        </span>
      </div>

      <HqButton size="sm" variant="secondary" @click="handleRefresh">
        <RefreshCw class="w-3.5 h-3.5 mr-1" />
        刷新配置
      </HqButton>
    </div>

    <!-- 2-Column Layout -->
    <div class="flex-1 flex overflow-hidden">
      <!-- Left: Scene Selection Tabs -->
      <aside class="w-64 border-r border-border bg-panel p-3 space-y-2 shrink-0 select-none overflow-y-auto">
        <h3 class="text-xs font-semibold text-text px-1 mb-2">预置场景清单</h3>

        <div
          v-for="scene in scenesStore.scenes"
          :key="scene.id"
          class="p-3 rounded-[var(--radius-md)] border cursor-pointer transition-all space-y-1.5"
          :class="
            selectedSceneId === scene.id
              ? 'border-primary bg-primary/10 shadow-xs'
              : 'border-border bg-bg-app hover:border-border-hover'
          "
          @click="selectedSceneId = scene.id"
        >
          <div class="flex items-center justify-between">
            <span class="font-medium text-xs text-text">{{ scene.name }}</span>
            <HqBadge size="sm" :variant="scene.readOnly ? 'info' : 'success'">
              {{ scene.readOnly ? '只读场景' : '读写场景' }}
            </HqBadge>
          </div>

          <p class="text-[11px] text-text-muted leading-relaxed line-clamp-2">
            {{ scene.description }}
          </p>

          <div class="flex items-center justify-between text-[10px] text-text-muted pt-1 border-t border-border/50">
            <span class="font-mono">版本 v{{ scene.version }}</span>
            <span>{{ scene.roles.length }} 个角色</span>
          </div>
        </div>
      </aside>

      <!-- Center/Right: Role Configuration Studio -->
      <main class="flex-1 flex flex-col overflow-hidden bg-bg-app">
        <!-- Editor Header -->
        <header class="p-4 border-b border-border bg-panel flex items-center justify-between gap-4 shrink-0">
          <div v-if="scenesStore.currentScene">
            <div class="flex items-center gap-2 mb-1">
              <h2 class="text-sm font-semibold text-text">
                {{ scenesStore.currentScene.name }}
              </h2>
              <span class="font-mono text-xs text-text-muted">
                v{{ scenesStore.currentScene.version }}
              </span>
              <HqBadge size="sm" variant="neutral">
                {{ scenesStore.currentScene.id }}
              </HqBadge>
            </div>
            <p class="text-xs text-text-muted leading-relaxed">
              {{ scenesStore.currentScene.description }}
            </p>
          </div>

          <div class="flex items-center gap-2">
            <HqButton
              variant="primary"
              size="sm"
              :disabled="scenesStore.isSaving"
              :loading="scenesStore.isSaving"
              @click="handleSave"
            >
              <Save class="w-3.5 h-3.5 mr-1.5" />
              保存场景配置
            </HqButton>
          </div>
        </header>

        <!-- Version Conflict 409 Alert -->
        <div
          v-if="scenesStore.conflictError"
          class="m-4 p-3.5 rounded-[var(--radius-md)] bg-danger/10 border border-danger/30 text-xs text-danger flex items-start justify-between gap-3 shadow-sm"
        >
          <div class="flex items-start gap-2.5">
            <AlertCircle class="w-4 h-4 shrink-0 mt-0.5" />
            <div class="space-y-1">
              <p class="font-semibold text-danger">配置版本冲突 (HTTP 409)</p>
              <p class="text-text leading-relaxed">
                {{ scenesStore.conflictError.message }}
              </p>
            </div>
          </div>
          <HqButton size="sm" variant="secondary" @click="handleRefresh">
            <RefreshCw class="w-3.5 h-3.5 mr-1" />
            拉取最新版本覆盖
          </HqButton>
        </div>

        <!-- Role Cards Stream -->
        <div class="flex-1 overflow-y-auto p-4 space-y-4">
          <div
            v-for="(role, idx) in editableRoles"
            :key="role.roleId"
            class="p-4 rounded-[var(--radius-lg)] border border-border bg-panel shadow-xs space-y-3"
          >
            <!-- Role Header -->
            <div class="flex items-center justify-between gap-2 pb-2 border-b border-border">
              <div class="flex items-center gap-2">
                <span class="w-5 h-5 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-xs">
                  {{ idx + 1 }}
                </span>
                <div>
                  <h4 class="text-xs font-semibold text-text">
                    {{ getRoleMeta(role.roleId).title }}
                  </h4>
                  <p class="text-[11px] text-text-muted">
                    {{ getRoleMeta(role.roleId).desc }}
                  </p>
                </div>
              </div>

              <div class="flex items-center gap-2">
                <HqBadge
                  v-if="getRoleMeta(role.roleId).isReadOnly"
                  variant="info"
                  size="sm"
                  class="text-[10px]"
                >
                  <Lock class="w-3 h-3 mr-1" />
                  只读约束 (禁止提权)
                </HqBadge>

                <!-- Optional Role Switch -->
                <div v-if="getRoleMeta(role.roleId).isOptional" class="flex items-center gap-1.5 text-xs">
                  <span class="text-[11px] text-text-muted">启用角色</span>
                  <HqSwitch v-model="role.enabled" />
                </div>
              </div>
            </div>

            <!-- Role Body Fields -->
            <div v-if="role.enabled" class="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
              <!-- Agent Select -->
              <div>
                <label class="block font-medium text-text mb-1">
                  执行 Agent <span class="text-danger">*</span>
                </label>
                <HqSelect
                  :model-value="role.agentInstanceId"
                  :options="
                    scenesStore.availableAgents.map((a) => ({
                      label: `${a.displayName} (${a.adapterId})`,
                      value: a.id,
                    }))
                  "
                  placeholder="选择已发现的本地 Agent"
                  @update:model-value="(val) => handleAgentChange(role, val as string)"
                />
              </div>

              <!-- Model Select or Manual Input -->
              <div>
                <label class="block font-medium text-text mb-1">
                  模型规格 (Model ID)
                </label>
                <!-- If verified models available -->
                <div v-if="scenesStore.agentModelsMap[role.agentInstanceId]?.verified && (scenesStore.agentModelsMap[role.agentInstanceId]?.models?.length ?? 0) > 0">
                  <HqSelect
                  v-model="role.modelId"
                  @update:model-value="role.reasoningEffort = ''"
                    :options="
                      (scenesStore.agentModelsMap[role.agentInstanceId]?.models || []).map((m) => ({
                        label: `${m.name} (${m.id})`,
                        value: m.id,
                      }))
                    "
                    placeholder="选择供应商模型规格"
                  />
                </div>

                <!-- If unverified or empty models: Provide clearly marked manual input -->
                <div v-else class="space-y-1">
                  <input
                    v-model="role.modelId"
                    type="text"
                    placeholder="手动指定模型规格 (由后端在执行时验证)..."
                    class="w-full px-2.5 py-1.5 text-xs bg-bg-app border border-border rounded text-text placeholder-text-muted/60 focus:outline-none focus:border-primary"
                  />
                  <p class="text-[10px] text-warning flex items-center gap-1">
                    <AlertCircle class="w-3 h-3 shrink-0" />
                    <span>未提供预定义模型列表，支持手动指定由后端校验</span>
                  </p>
                </div>
              </div>

              <!-- Reasoning Effort -->
              <div>
                <label class="block font-medium text-text mb-1">
                  思考强度 (Reasoning Effort)
                </label>
                <HqSelect
                  v-if="selectedModel(role)"
                  v-model="role.reasoningEffort"
                  :options="effortOptions(role)"
                  placeholder="请选择思考等级"
                />
                <input v-else v-model="role.reasoningEffort" class="w-full px-2.5 py-1.5 bg-bg-app border border-border rounded" placeholder="留空继承默认；手填值由后端验证" />
              </div>
            </div>

            <!-- Role Instructions / Prompt -->
            <div v-if="role.enabled">
              <div class="flex items-center justify-between mb-1">
                <label class="block font-medium text-text text-xs">
                  角色职责与约束提示词 (Instructions)
                </label>
                <span
                  class="text-[10px]"
                  :class="role.instructions.length > 12000 ? 'text-danger font-medium' : 'text-text-muted'"
                >
                  {{ role.instructions.length }} / 12000 字符
                </span>
              </div>
              <HqTextarea
                v-model="role.instructions"
                :rows="3"
                placeholder="请输入该角色在当前场景中的专业职责与边界约束..."
              />
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>
