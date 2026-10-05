<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import type { RemoteApiTokenCreateInput, RemoteApiTokenScope } from '@hqagent/protocol'
import { getRemoteGateway, RemoteApiError } from '@/shared/api'
import { HqButton, HqDialog } from '@/shared/ui'
import RemoteRequestNotice from './RemoteRequestNotice.vue'

const emit = defineEmits<{ close: []; created: []; revoke: [tokenId: string] }>()
const name = ref('')
const scopes = ref<RemoteApiTokenScope[]>([])
const days = ref(90)
const permissions: RemoteApiTokenScope[] = ['devices:read', 'devices:manage', 'devices:delete']
const scopeLabels: Record<RemoteApiTokenScope, string> = {
  'devices:read': '读取设备信息',
  'devices:manage': '远程操作管理',
  'devices:delete': '删除电脑设备',
}
const scopeDescriptions: Record<RemoteApiTokenScope, string> = {
  'devices:read': '允许查询电脑在线状态、硬件架构与项目工作区列表',
  'devices:manage': '允许修改电脑显示名称、暂停或恢复远程接入',
  'devices:delete': '允许从云端解除设备连接（高危破坏性操作）',
}
const secret = shallowRef('')
const issuedTokenId = ref<string | null>(null)
const replayed = ref(false)
const loading = ref(false)
const error = ref('')
const copyState = ref('')
let alive = true
let intent: { input: RemoteApiTokenCreateInput; key: string } | null = null
const valid = computed(() => name.value.trim().length > 0 && name.value.trim().length <= 120 && scopes.value.length > 0 && Number.isInteger(days.value) && days.value >= 1 && days.value <= 365)
watch([name, () => [...scopes.value], days], () => { intent = null })
function close() {
  alive = false
  secret.value = ''
  issuedTokenId.value = null
  intent = null
  emit('close')
}
onBeforeUnmount(() => { alive = false; secret.value = ''; intent = null })
async function issue() {
  if (!valid.value || loading.value) return
  loading.value = true
  error.value = ''
  if (!intent) intent = {
    key: crypto.randomUUID(),
    input: { name: name.value.trim(), scopes: [...scopes.value],
      ...(days.value === 90 ? {} : { expiresAt: new Date(Date.now() + days.value * 86400000).toISOString() }) },
  }
  try {
    const result = await getRemoteGateway().issueApiToken(intent.input, intent.key)
    if (!alive) return
    issuedTokenId.value = result.token.tokenId
    if (result.secretAvailable) secret.value = result.secret
    else replayed.value = true
    // The parent only refreshes metadata; neither response nor secret is emitted.
    emit('created')
  } catch (err: unknown) {
    if (alive) error.value = err instanceof RemoteApiError ? err.message : '签发失败，请重试；若首次响应丢失，重试只会返回元数据'
  } finally { if (alive) loading.value = false }
}
async function copySecret() {
  try { await navigator.clipboard.writeText(secret.value); if (alive) copyState.value = '已复制，请妥善保存' }
  catch { if (alive) copyState.value = '复制失败，请长按选择令牌手动复制' }
}
function revokeIssued() {
  if (issuedTokenId.value) emit('revoke', issuedTokenId.value)
  close()
}
</script>

<template>
  <HqDialog :open="true" :title="issuedTokenId ? 'API 令牌已创建' : '新建 API 令牌'" @close="close">
    <div class="space-y-4 text-xs">
      <template v-if="!issuedTokenId">
        <label class="block font-medium">名称
          <input v-model="name" :disabled="loading" maxlength="120" aria-label="令牌名称" class="hq-form-control block w-full p-2.5 mt-1 bg-bg-app border border-border rounded-lg text-sm" placeholder="例如：CI 构建自动化" />
        </label>
        <fieldset :disabled="loading" class="space-y-2">
          <legend class="mb-2 font-medium">权限（各自独立）</legend>
          <label v-for="scope in permissions" :key="scope" class="flex items-start gap-3 p-3 rounded-xl border border-border bg-bg-app hover:bg-muted/40 cursor-pointer min-h-[44px] transition-colors">
            <input class="hq-form-choice mt-0.5 shrink-0" v-model="scopes" type="checkbox" :value="scope" />
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-1.5 font-medium text-xs">
                <span>{{ scopeLabels[scope] }}</span>
                <span class="text-text-muted font-mono text-[10px]">({{ scope }})</span>
              </div>
              <p class="text-[11px] text-text-muted mt-0.5 leading-normal">{{ scopeDescriptions[scope] }}</p>
            </div>
          </label>
        </fieldset>
        <p v-if="scopes.includes('devices:delete')" class="text-warning font-medium flex items-center gap-1">
          <span>⚠️</span>
          <span>删除是破坏性操作</span>
        </p>
        <label class="block font-medium">有效期（天，默认 90，最多 365）
          <input v-model.number="days" :disabled="loading" type="number" min="1" max="365" step="1" aria-label="有效期天数" class="hq-form-control block w-full p-2.5 mt-1 bg-bg-app border border-border rounded-lg text-sm" />
        </label>
        <p class="text-text-muted leading-relaxed">权限只用于设备管理，不授予对话、模型或令牌管理能力。</p>
      </template>
      <template v-else-if="secret">
        <p class="font-medium text-warning">关闭后无法再次查看</p>
        <p class="text-text-muted leading-relaxed">请复制到安全位置。不要将令牌发给他人或粘贴到排查记录中。</p>
        <pre data-testid="issued-secret" class="whitespace-pre-wrap break-all select-text bg-bg-app border border-border p-3 rounded-lg text-xs font-mono">{{ secret }}</pre>
        <div class="flex items-center gap-3">
          <HqButton size="md" class="min-h-[38px]" @click="copySecret">复制令牌</HqButton>
          <span role="status" class="text-xs text-text-muted">{{ copyState }}</span>
        </div>
      </template>
      <template v-else-if="replayed">
        <p role="status">令牌已创建但无法再次显示，如未保存请吊销后重建</p>
        <HqButton variant="danger" class="min-h-[38px]" @click="revokeIssued">吊销此令牌</HqButton>
      </template>
      <p v-if="error" role="alert" class="text-danger">{{ error }}</p>
      <RemoteRequestNotice />
    </div>
    <template #footer>
      <div class="flex items-center justify-end gap-2 w-full">
        <HqButton variant="ghost" size="md" class="min-h-[38px]" @click="close">{{ issuedTokenId ? '关闭' : '取消' }}</HqButton>
        <HqButton v-if="!issuedTokenId" size="md" class="min-h-[38px]" :disabled="!valid" :loading="loading" @click="issue">签发令牌</HqButton>
      </div>
    </template>
  </HqDialog>
</template>
