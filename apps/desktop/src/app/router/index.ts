import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/dev/ui-kit',
  },
]

// Dev-only UI Kit route
if (import.meta.env.DEV) {
  routes.push({
    path: '/dev/ui-kit',
    name: 'dev-ui-kit',
    component: () => import('@/pages/dev/UiKitPage.vue'),
    meta: { title: 'UI Kit 组件库与主题矩阵' },
  })
}

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
