<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { RemoteApiTokenView } from '@hqagent/protocol'
import { getRemoteGateway, RemoteApiError } from '@/shared/api'
import { HqButton, HqDialog, HqBadge } from '@/shared/ui'
import RemoteTokenIssueDialog from './RemoteTokenIssueDialog.vue'
import RemoteRequestNotice from './RemoteRequestNotice.vue'

const router = useRouter()
const tokens = ref<RemoteApiTokenView[]>([])
const includeRevoked = ref(false)
const nextCursor = ref<string | undefined>()
const loading = ref(false)
const error = ref('')
const issueOpen = ref(false)
const revokeId = ref<string | null>(null)
const revoking = ref(false)
let request = 0
async function fetchTokens(more = false) {
  const current = ++request
  loading.value = true
  error.value = ''
  if (!more) { tokens.value = []; nextCursor.value = undefined }
  try {
    const page = await getRemoteGateway().listApiTokens(more ? nextCursor.value : undefined, 50, includeRevoked.value)
    if (current !== request) return
    if (page.hasMore && !page.nextCursor) throw new Error('令牌分页游标无效')
    tokens.value = more ? [...tokens.value, ...page.items] : page.items
    nextCursor.value = page.hasMore ? page.nextCursor : undefined
  } catch (err: unknown) {
    if (current === request) error.value = err instanceof RemoteApiError ? err.message : '读取令牌列表失败，请重试'
  } finally { if (current === request) loading.value = false }
}
async function revoke() {
  if (!revokeId.value || revoking.value) return
  revoking.value = true
  error.value = ''
  try {
    await getRemoteGateway().revokeApiToken(revokeId.value)
    revokeId.value = null
    await fetchTokens()
  } catch (err: unknown) { error.value = err instanceof RemoteApiError ? err.message : '吊销失败，请重试' }
  finally { revoking.value = false }
}
function time(value?: string) { return value ? new Date(value).toLocaleString() : '从未使用' }
watch(includeRevoked, () => { void fetchTokens() })
onMounted(() => { void fetchTokens() })
onBeforeUnmount(() => { request++ })
</script>

<template>
  <div class="h-dvh bg-bg-app text-text flex flex-col overflow-hidden">
    <header class="h-14 shrink-0 px-4 bg-panel border-b border-border flex items-center justify-between">
      <HqButton variant="ghost" size="sm" @click="router.push('/remote/devices')">返回</HqButton>
      <h1 class="font-bold text-sm">API 令牌</h1><HqButton size="sm" @click="issueOpen = true">新建令牌</HqButton>
    </header>
    <RemoteRequestNotice />
    <main class="flex-1 min-h-0 overflow-y-auto w-full max-w-lg mx-auto p-4 space-y-4">
      <p class="text-xs text-text-muted">用于外部工具管理设备。令牌秘密仅在首次签发时展示，请按需授予权限。</p>
      <label class="text-xs flex gap-2 items-center"><input class="hq-form-choice" v-model="includeRevoked" type="checkbox" />显示已吊销</label>
      <p v-if="error" role="alert" class="text-xs text-danger">{{ error }} <button type="button" class="underline" @click="fetchTokens()">重试</button></p>
      <p v-if="loading" class="text-xs text-text-muted">正在读取令牌…</p>
      <p v-else-if="!tokens.length" class="text-sm text-text-muted py-8 text-center">暂无 API 令牌</p>
      <article v-for="token in tokens" :key="token.tokenId" class="p-4 rounded-xl border border-border bg-panel space-y-2 text-xs">
        <div class="flex items-center justify-between gap-2"><h2 class="font-semibold text-sm break-words min-w-0">{{ token.name }}</h2><HqBadge :variant="token.status === 'active' ? 'success' : 'neutral'">{{ { active: '有效', expired: '已过期', revoked: '已吊销' }[token.status] }}</HqBadge></div>
        <p class="break-all select-text text-text-muted">{{ token.tokenPrefix }}</p>
        <p class="break-words">权限：{{ token.scopes.join('、') }}</p>
        <dl class="space-y-1 text-text-muted"><div>创建时间：{{ time(token.createdAt) }}</div><div>最后使用：{{ time(token.lastUsedAt) }}</div><div>到期时间：{{ time(token.expiresAt) }}</div></dl>
        <HqButton v-if="token.status !== 'revoked'" variant="danger" size="sm" @click="error = ''; revokeId = token.tokenId">吊销</HqButton>
      </article>
      <HqButton v-if="nextCursor" variant="secondary" :loading="loading" @click="fetchTokens(true)">加载更多</HqButton>
    </main>
    <RemoteTokenIssueDialog v-if="issueOpen" @close="issueOpen = false" @created="fetchTokens()" @revoke="revokeId = $event" />
    <HqDialog :open="Boolean(revokeId)" title="确认吊销 API 令牌？" @close="revokeId = null">
      <p class="text-xs">吊销后，使用此令牌的外部工具将立即失去访问权限。此操作不能恢复。</p>
      <p v-if="error" role="alert" class="text-xs text-danger mt-3">{{ error }}</p><RemoteRequestNotice />
      <template #footer><HqButton variant="ghost" :disabled="revoking" @click="revokeId = null">取消</HqButton><HqButton variant="danger" :loading="revoking" @click="revoke">确认吊销</HqButton></template>
    </HqDialog>
  </div>
</template>
