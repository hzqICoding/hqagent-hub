<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app.store'
import type { FeatureAvailability } from '@hqagent/protocol'
import { Construction, ArrowLeft, Lock, Calendar } from 'lucide-vue-next'
import { HqButton, HqBadge } from '@/shared/ui'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const pageTitle = computed(() => (route.meta.title as string) || '功能模块')
const milestone = computed(() => (route.meta.milestone as string) || '后续里程碑')
const featureKey = computed(() => route.meta.featureKey as keyof FeatureAvailability | undefined)

const isFeatureDisabled = computed(() => {
  if (!featureKey.value) return false
  return !appStore.isFeatureAvailable(featureKey.value)
})

const disabledReason = computed(() => {
  if (!featureKey.value) return undefined
  return appStore.getFeatureReason(featureKey.value)
})
</script>

<template>
  <div class="h-full flex flex-col items-center justify-center p-8 text-center select-none">
    <div class="max-w-md space-y-4">
      <div class="w-16 h-16 rounded-2xl bg-primary-50 dark:bg-primary-950 text-primary-600 flex items-center justify-center mx-auto shadow-sm">
        <Lock v-if="isFeatureDisabled" class="w-8 h-8 text-amber-500" />
        <Construction v-else class="w-8 h-8 text-primary-600" />
      </div>

      <div class="space-y-1.5">
        <div class="flex items-center justify-center gap-2">
          <h2 class="text-base font-bold text-content-primary">{{ pageTitle }}</h2>
          <HqBadge variant="neutral" size="sm">{{ milestone }}</HqBadge>
        </div>

        <p v-if="isFeatureDisabled" class="text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/40 p-2.5 rounded-lg border border-amber-200 dark:border-amber-800">
          功能门禁已锁定: {{ disabledReason || '该模块在此交付阶段暂未开放' }}
        </p>
        <p v-else class="text-xs text-content-muted leading-relaxed">
          该模块计划在 {{ milestone }} 中完整交付。当前已预留架构接入点与 UI 路由。
        </p>
      </div>

      <div class="pt-2">
        <HqButton size="sm" variant="secondary" @click="router.push('/overview')">
          <template #icon>
            <ArrowLeft class="w-3.5 h-3.5" />
          </template>
          返回总览
        </HqButton>
      </div>
    </div>
  </div>
</template>
