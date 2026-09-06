<script setup lang="ts">
import { onMounted } from 'vue'
import { useAppStore } from '@/stores/app.store'
import { useWorkspaceStore } from '@/stores/workspace.store'
import AppSidebar from './components/AppSidebar.vue'
import AppHeader from './components/AppHeader.vue'
import AppStatusBar from './components/AppStatusBar.vue'
import LogDrawer from './components/LogDrawer.vue'
import ContextInspector from './components/ContextInspector.vue'

const appStore = useAppStore()
const workspaceStore = useWorkspaceStore()

onMounted(async () => {
  await appStore.fetchBootstrap()
  await workspaceStore.fetchWorkspaces()
})
</script>

<template>
  <div class="h-full w-full overflow-hidden flex flex-col bg-app text-content-primary">
    <!-- Top Body Area: Sidebar + Main Area + Inspector -->
    <div class="flex-1 flex overflow-hidden">
      <!-- Left: Sidebar -->
      <AppSidebar />

      <!-- Center: Main Page Content -->
      <div class="flex-1 flex flex-col min-w-0 overflow-hidden">
        <AppHeader />
        <main class="flex-1 overflow-y-auto relative bg-panel/30">
          <router-view />
        </main>
      </div>

      <!-- Right: Context Inspector -->
      <ContextInspector />
    </div>

    <!-- Collapsible Log Drawer -->
    <LogDrawer />

    <!-- Bottom Status Bar -->
    <AppStatusBar />
  </div>
</template>
