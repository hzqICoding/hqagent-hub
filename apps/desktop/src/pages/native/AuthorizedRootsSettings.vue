<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import type { LocalAuthorizedRootInput, LocalAuthorizedRootsView } from '@hqagent/protocol'
import { getLocalChatGateway } from '@/shared/api'
import { HqButton } from '@/shared/ui'
import { nativeFailure } from './native-utils'
const view = ref<LocalAuthorizedRootsView | null>(null)
const roots = ref<LocalAuthorizedRootInput[]>([])
const loading = ref(false)
const error = ref<ReturnType<typeof nativeFailure> | null>(null)
let alive = true
async function load() {
  loading.value = true
  try {
    const latest = await getLocalChatGateway().getAuthorizedRoots()
    if (!alive) return
    view.value = latest; roots.value = latest.roots.map(({ rootId, displayName, path }) => ({ rootId, displayName, path }))
  } catch (err) { if (alive) error.value = nativeFailure(err) }
  finally { if (alive) loading.value = false }
}
async function add() {
  if (roots.value.length >= 32 || loading.value) return
  loading.value = true; error.value = null
  try {
    const picked = await getLocalChatGateway().pickLocalDirectory({})
    if (alive && !picked.cancelled && picked.selectedPath) roots.value.push({ path: picked.selectedPath, displayName: '授权目录' })
  } catch (err) { if (alive) error.value = nativeFailure(err) }
  finally { if (alive) loading.value = false }
}
async function save() {
  if (!view.value || loading.value || roots.value.some((r) => !r.displayName.trim())) return
  loading.value = true; error.value = null
  try {
    await getLocalChatGateway().setAuthorizedRoots({ expectedVersion: view.value.version, roots: roots.value.map((r) => ({ ...r, displayName: r.displayName.trim() })) })
    if (alive) await load()
  } catch (err) {
    if (!alive) return
    error.value = nativeFailure(err)
    if (error.value.code === 'CONFLICT') { await load(); error.value = { ...nativeFailure(err), message: '授权根目录已变化，已重新读取，请确认后重试' } }
  } finally { if (alive) loading.value = false }
}
function copyId() { if (error.value?.requestId) void navigator.clipboard.writeText(error.value.requestId).catch(() => {}) }
onMounted(load)
onBeforeUnmount(() => { alive = false; roots.value = []; view.value = null })
</script>

<template>
  <section class="p-5 bg-panel border border-border rounded-xl space-y-4" data-testid="authorized-roots">
    <h2 class="font-semibold text-sm">授权根目录</h2><p class="text-xs text-text-muted">手机只能在这些目录内浏览和添加项目，默认不开放</p>
    <p class="text-xs text-text-muted">最多 32 个。移除授权后，已有项目保留，新的浏览和登记立即失效。</p>
    <p v-if="error" role="alert" class="text-xs text-danger">{{ error.message }} <button v-if="error.requestId" class="select-text" @click="copyId">requestId: {{ error.requestId }}</button></p>
    <p v-if="!roots.length" class="text-xs">未授权任何根目录</p>
    <div v-for="(root, index) in roots" :key="root.rootId || index" class="flex flex-wrap items-center gap-2">
      <input v-model="root.displayName" :disabled="loading" aria-label="根目录显示名称" maxlength="120" class="p-2 text-xs bg-bg-app border border-border rounded" />
      <span class="text-xs text-text-muted break-all flex-1">{{ root.path }}</span>
      <HqButton size="sm" variant="danger" :disabled="loading" @click="roots.splice(index, 1)">移除</HqButton>
    </div>
    <div class="flex gap-2"><HqButton variant="secondary" size="sm" :disabled="loading || roots.length >= 32 || !view" @click="add">选择目录添加</HqButton><HqButton size="sm" :loading="loading" :disabled="!view || roots.some((r) => !r.displayName.trim())" @click="save">保存授权根目录</HqButton><HqButton size="sm" variant="ghost" :disabled="loading" @click="load">刷新</HqButton></div>
  </section>
</template>
