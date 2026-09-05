<script setup lang="ts">
import { useToast } from './useToast'
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from 'lucide-vue-next'

const { toasts, dismiss } = useToast()
</script>

<template>
  <Teleport to="body">
    <div
      class="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none"
    >
      <TransitionGroup
        enter-active-class="transform ease-out duration-200 transition"
        enter-from-class="translate-y-2 opacity-0 sm:translate-y-0 sm:translate-x-2"
        enter-to-class="translate-y-0 opacity-100 sm:translate-x-0"
        leave-active-class="transition ease-in duration-150"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-for="item in toasts"
          :key="item.id"
          :class="[
            'pointer-events-auto flex items-start p-3 bg-elevated border rounded-[var(--radius-md)] shadow-popover select-none',
            item.type === 'success'
              ? 'border-status-success/40'
              : item.type === 'warning'
                ? 'border-status-warning/40'
                : item.type === 'danger'
                  ? 'border-status-danger/40'
                  : 'border-status-info/40',
          ]"
        >
          <!-- Icon -->
          <div class="mr-2.5 mt-0.5 shrink-0">
            <CheckCircle2
              v-if="item.type === 'success'"
              class="h-4 w-4 text-status-success"
            />
            <AlertTriangle
              v-else-if="item.type === 'warning'"
              class="h-4 w-4 text-status-warning"
            />
            <XCircle
              v-else-if="item.type === 'danger'"
              class="h-4 w-4 text-status-danger"
            />
            <Info v-else class="h-4 w-4 text-status-info" />
          </div>

          <!-- Text -->
          <div class="flex-1 mr-2 text-xs">
            <div
              v-if="item.title"
              class="font-semibold text-content-primary mb-0.5"
            >
              {{ item.title }}
            </div>
            <div class="text-content-secondary leading-normal">
              {{ item.message }}
            </div>
          </div>

          <!-- Close -->
          <button
            type="button"
            class="text-content-muted hover:text-content-primary rounded p-0.5 shrink-0"
            @click="dismiss(item.id)"
          >
            <X class="h-3.5 w-3.5" />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>
