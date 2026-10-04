<script setup lang="ts">
import { Bot, TerminalSquare, Sparkles } from 'lucide-vue-next'
defineProps<{ agent?: string }>()
</script>
<template><span v-if="agent === 'pi'" role="img" aria-label="PI" class="inline-flex items-center justify-center font-semibold text-accent shrink-0" data-testid="pi-icon">π</span><TerminalSquare v-else-if="agent === 'codex'" aria-label="Codex" /><Sparkles v-else-if="agent === 'claude'" aria-label="Claude Code" /><Bot v-else aria-hidden="true" /></template>
