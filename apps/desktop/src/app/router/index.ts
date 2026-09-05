import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import AppLayout from '../layouts/AppLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/onboarding',
    name: 'onboarding',
    component: () => import('@/pages/onboarding/OnboardingPage.vue'),
    meta: { title: '首次使用引导' },
  },
  {
    path: '/',
    component: AppLayout,
    children: [
      {
        path: '',
        redirect: '/overview',
      },
      {
        path: 'overview',
        name: 'overview',
        component: () => import('@/pages/overview/OverviewPage.vue'),
        meta: { title: '总览控制台' },
      },
      {
        path: 'agents',
        name: 'agents',
        component: () => import('@/pages/agents/AgentsPage.vue'),
        meta: { title: 'Agent 管理与诊断' },
      },
      {
        path: 'workspaces',
        name: 'workspaces',
        component: () => import('@/pages/common/PlaceholderPage.vue'),
        meta: { title: '工作区管理', milestone: 'F2' },
      },
      {
        path: 'teams',
        name: 'teams',
        component: () => import('@/pages/common/PlaceholderPage.vue'),
        meta: { title: '团队配置', milestone: 'F2', featureKey: 'teamProfiles' },
      },
      {
        path: 'tasks',
        name: 'tasks',
        component: () => import('@/pages/common/PlaceholderPage.vue'),
        meta: { title: '任务中心', milestone: 'F3', featureKey: 'tasks' },
      },
      {
        path: 'sessions',
        name: 'sessions',
        component: () => import('@/pages/common/PlaceholderPage.vue'),
        meta: { title: '会话历史', milestone: 'F3', featureKey: 'sessions' },
      },
      {
        path: 'templates',
        name: 'templates',
        component: () => import('@/pages/common/PlaceholderPage.vue'),
        meta: { title: '任务模板', milestone: 'F2' },
      },
      {
        path: 'updates',
        name: 'updates',
        component: () => import('@/pages/common/PlaceholderPage.vue'),
        meta: { title: '软件更新', milestone: 'F4', featureKey: 'updates' },
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/pages/common/PlaceholderPage.vue'),
        meta: { title: '系统设置', milestone: 'F4' },
      },
    ],
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
