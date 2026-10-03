<script setup lang="ts">
import { onMounted } from 'vue'
import { themeEngine } from '@/shared/theme/theme.engine'
import { HqToast } from '@/shared/ui'
import { isDesktopShell } from '@/shared/api/desktop-endpoint'
import DesktopConnection from '@/app/DesktopConnection.vue'

onMounted(() => {
  themeEngine.init()
})
</script>

<template>
  <div class="h-full w-full overflow-hidden bg-app text-content-primary flex flex-col">
    <DesktopConnection v-if="isDesktopShell()"><router-view /></DesktopConnection>
    <router-view v-else />
    <HqToast />
  </div>
</template>
