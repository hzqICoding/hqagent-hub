<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import type { LocalAuthorizedRootInput, LocalAuthorizedRootsView } from '@hqagent/protocol'
import { Folder, RefreshCw } from 'lucide-vue-next'
import { getLocalChatGateway } from '@/shared/api'
import { HqButton, HqBadge } from '@/shared/ui'
import { nativeFailure, defaultRootDisplayName } from './native-utils'

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
    view.value = latest
    roots.value = latest.roots.map(({ rootId, displayName, path }) => ({ rootId, displayName, path }))
  } catch (err) {
    if (alive) error.value = nativeFailure(err)
  } finally {
    if (alive) loading.value = false
  }
}

async function add() {
  if (roots.value.length >= 32 || loading.value) return
  loading.value = true
  error.value = null
  try {
    const picked = await getLocalChatGateway().pickLocalDirectory({})
    if (alive && !picked.cancelled && picked.selectedPath) {
      roots.value.push({
        path: picked.selectedPath,
        displayName: defaultRootDisplayName(picked.selectedPath),
      })
    }
  } catch (err) {
    if (alive) error.value = nativeFailure(err)
  } finally {
    if (alive) loading.value = false
  }
}

async function save() {
  if (!view.value || loading.value || roots.value.some((r) => !r.displayName.trim())) return
  loading.value = true
  error.value = null
  try {
    await getLocalChatGateway().setAuthorizedRoots({
      expectedVersion: view.value.version,
      roots: roots.value.map((r) => ({ ...r, displayName: r.displayName.trim() })),
    })
    if (alive) await load()
  } catch (err) {
    if (!alive) return
    error.value = nativeFailure(err)
    if (error.value.code === 'CONFLICT') {
      await load()
      error.value = {
        ...nativeFailure(err),
        message: '授权根目录已变化，已重新读取，请确认后重试',
      }
    }
  } finally {
    if (alive) loading.value = false
  }
}

function copyId() {
  if (error.value?.requestId) {
    void navigator.clipboard.writeText(error.value.requestId).catch(() => {})
  }
}

onMounted(load)
onBeforeUnmount(() => {
  alive = false
  roots.value = []
  view.value = null
})
</script>

<template>
  <section class="p-5 bg-panel border border-border-subtle rounded-xl space-y-4" data-testid="authorized-roots">
    <div class="flex items-center justify-between">
      <div class="space-y-0.5">
        <h2 class="font-semibold text-sm text-text flex items-center gap-2">
          <Folder class="w-4 h-4 text-primary" />
          授权根目录
        </h2>
        <p class="text-xs text-text-muted">
          手机端可浏览与添加项目的本地目录（最多 32 个）
        </p>
      </div>
      <div class="flex items-center gap-2">
        <HqBadge v-if="roots.length" variant="neutral" size="sm">
          {{ roots.length }} / 32
        </HqBadge>
        <button
          type="button"
          :disabled="loading"
          class="p-1.5 rounded-lg text-text-muted hover:text-text hover:bg-muted/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          title="刷新列表"
          aria-label="刷新"
          @click="load"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" />
        </button>
      </div>
    </div>

    <div
      v-if="error"
      role="alert"
      class="p-2.5 bg-danger/10 border border-danger/20 rounded-lg text-xs text-danger flex items-center justify-between gap-2"
    >
      <span>{{ error.message }}</span>
      <button
        v-if="error.requestId"
        class="font-mono text-[11px] underline select-text shrink-0"
        @click="copyId"
      >
        requestId: {{ error.requestId }}
      </button>
    </div>

    <div
      v-if="!roots.length"
      class="p-6 rounded-lg bg-bg-app text-center text-xs text-text-muted"
    >
      未授权任何根目录
    </div>

    <div v-else class="space-y-2">
      <div
        v-for="(root, index) in roots"
        :key="root.rootId || index"
        class="p-2.5 bg-muted/20 hover:bg-muted/40 rounded-xl flex flex-col sm:flex-row sm:items-center gap-2.5 text-xs transition-colors"
      >
        <div class="flex items-center gap-2 shrink-0">
          <Folder class="w-4 h-4 text-primary/80 shrink-0" />
          <input
            v-model="root.displayName"
            :disabled="loading"
            aria-label="根目录显示名称"
            maxlength="120"
            placeholder="显示名称"
            class="hq-form-control h-8 px-2.5 text-xs bg-panel border border-border-subtle rounded-lg w-36 font-medium text-text focus:outline-none focus:border-primary"
          />
        </div>
        <span
          class="text-xs text-text-muted font-mono truncate flex-1 min-w-0"
          :title="root.path"
        >
          {{ root.path }}
        </span>
        <HqButton
          size="sm"
          variant="ghost"
          class="text-danger hover:text-danger-hover hover:bg-danger/10 shrink-0 self-end sm:self-auto"
          :disabled="loading"
          @click="roots.splice(index, 1)"
        >
          移除
        </HqButton>
      </div>
    </div>

    <div class="flex items-center justify-between gap-3 pt-2 border-t border-border-subtle">
      <HqButton
        variant="secondary"
        size="sm"
        :disabled="loading || roots.length >= 32 || !view"
        @click="add"
      >
        选择目录
      </HqButton>

      <HqButton
        size="sm"
        :loading="loading"
        :disabled="!view || roots.some((r) => !r.displayName.trim())"
        @click="save"
      >
        保存设置
      </HqButton>
    </div>
  </section>
</template>
