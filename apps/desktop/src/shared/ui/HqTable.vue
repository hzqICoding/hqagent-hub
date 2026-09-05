<script setup lang="ts">
export interface TableColumn {
  key: string
  label: string
  width?: string
  align?: 'left' | 'center' | 'right'
}

interface Props {
  columns: TableColumn[]
  data: any[]
  loading?: boolean
  emptyText?: string
}

withDefaults(defineProps<Props>(), {
  loading: false,
  emptyText: '暂无数据',
})
</script>

<template>
  <div class="w-full border border-border rounded-[var(--radius-sm)] overflow-hidden bg-panel">
    <div class="overflow-x-auto">
      <table class="w-full text-left border-collapse text-xs">
        <thead class="bg-muted/70 border-b border-border text-content-secondary font-medium select-none">
          <tr>
            <th
              v-for="col in columns"
              :key="col.key"
              :class="[
                'px-3 py-2 font-medium',
                col.align === 'center' ? 'text-center' : col.align === 'right' ? 'text-right' : 'text-left',
              ]"
              :style="{ width: col.width }"
            >
              <slot :name="`header-${col.key}`" :column="col">
                {{ col.label }}
              </slot>
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border-subtle text-content-primary">
          <tr v-if="loading" class="bg-panel">
            <td :colspan="columns.length" class="text-center py-8 text-content-muted">
              <div class="flex items-center justify-center gap-2">
                <span class="inline-block h-3.5 w-3.5 rounded-full border-2 border-action-primary border-t-transparent animate-spin" />
                <span>加载中...</span>
              </div>
            </td>
          </tr>

          <tr v-else-if="data.length === 0" class="bg-panel">
            <td :colspan="columns.length" class="text-center py-8 text-content-muted">
              {{ emptyText }}
            </td>
          </tr>

          <tr
            v-for="(row, idx) in data"
            v-else
            :key="row.id || idx"
            class="hover:bg-muted/40 transition-colors group"
          >
            <td
              v-for="col in columns"
              :key="col.key"
              :class="[
                'px-3 py-2 leading-normal',
                col.align === 'center' ? 'text-center' : col.align === 'right' ? 'text-right' : 'text-left',
              ]"
            >
              <slot :name="`cell-${col.key}`" :row="row" :index="idx">
                {{ row[col.key] }}
              </slot>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
