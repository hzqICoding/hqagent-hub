<script setup lang="ts">
import { onMounted } from 'vue'
import { themeEngine } from '@/shared/theme/theme.engine'
import { HqToast } from '@/shared/ui'

onMounted(() => {
  themeEngine.init()
})
</script>

<template>
  <div class="h-screen w-screen overflow-hidden bg-app text-content-primary">
    <router-view />
    <HqToast />
  </div>
</template>
