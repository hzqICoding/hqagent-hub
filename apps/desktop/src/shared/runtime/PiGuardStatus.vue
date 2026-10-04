<script setup lang="ts">
import type { RuntimeGuardView } from '@hqagent/protocol'
import { piGuardReady, piGuardLabel, piReasonLabels, PI_GUARD_BLOCKED } from './pi'
defineProps<{ guard?: RuntimeGuardView }>()
</script>
<template><div class="text-xs space-y-1" data-testid="pi-guard"><p :class="piGuardReady(guard) ? 'text-status-success' : 'text-status-warning'">{{ piGuardLabel(guard) }}</p><p v-if="!piGuardReady(guard)" class="text-status-warning">{{ PI_GUARD_BLOCKED }}</p><p v-for="reason in (guard?.reasons || []).filter(reason => piReasonLabels[reason] !== piGuardLabel(guard))" :key="reason" class="text-content-secondary">{{ piReasonLabels[reason] || '保护状态需在本机核对' }}</p><p v-if="guard?.checkedAt" class="text-content-secondary">检查时间：{{ guard.checkedAt }}</p></div></template>
