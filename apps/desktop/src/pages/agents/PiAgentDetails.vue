<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import type { AgentView, LocalAgentModelsView } from '@hqagent/protocol'
import { getLocalChatGateway } from '@/shared/api'
import PiGuardStatus from '@/shared/runtime/PiGuardStatus.vue'
import { piModelLabel } from '@/shared/runtime/pi'
const props=defineProps<{agent:AgentView}>()
const models=ref<LocalAgentModelsView|null>(null)
async function load(){const id=props.agent.id;models.value=null;try{const result=await getLocalChatGateway().getAgentModels(id);if(props.agent.id===id)models.value=result}catch{/* Unverified models are never invented. */}}
onMounted(load);watch(()=>props.agent.id,load)
</script>
<template><div class="space-y-3" data-testid="pi-agent-details"><PiGuardStatus :guard="agent.guard" /><div class="text-xs text-content-secondary"><p class="font-medium mb-1">本机可用模型</p><p v-if="!models?.verified">模型清单尚未核实</p><ul v-else class="space-y-1"><li v-for="model in models.models" :key="model.id" class="break-words">{{ piModelLabel(model.id) }}{{ model.isDefault ? '（本机默认）' : '' }}</li></ul></div></div></template>
