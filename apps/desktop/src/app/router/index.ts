import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import AppLayout from '../layouts/AppLayout.vue'
import LocalChatLayout from '../layouts/LocalChatLayout.vue'
import { useLocalAuthStore } from '@/stores/local-auth.store'

const routes: RouteRecordRaw[] = [
  {
    path: '/connect',
    name: 'connect',
    component: () => import('@/pages/auth/ConnectPage.vue'),
    meta: { title: '本地会话连接' },
  },
  {
    path: '/onboarding',
    name: 'onboarding',
    component: () => import('@/pages/onboarding/OnboardingPage.vue'),
    meta: { title: '首次使用引导' },
  },
  {
    path: '/chat',
    component: LocalChatLayout,
    children: [{ path: '', name: 'chat', component: () => import('@/pages/chat/ChatPage.vue'), meta: { title: '本地角色对话工作台' } }],
  },
  {
    path: '/scenes',
    component: LocalChatLayout,
    children: [{ path: '', name: 'scenes', component: () => import('@/pages/scenes/ScenesPage.vue'), meta: { title: '场景与角色配置' } }],
  },
  {
    path: '/',
    component: AppLayout,
    children: [
      {
        path: '',
        redirect: '/chat',
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
        component: () => import('@/pages/workspaces/WorkspacesPage.vue'),
        meta: { title: '工作区管理' },
      },
      {
        path: 'teams',
        name: 'teams',
        component: () => import('@/pages/teams/TeamsPage.vue'),
        meta: { title: '团队配置', featureKey: 'teamProfiles' },
      },
      {
        path: 'tasks',
        name: 'tasks',
        component: () => import('@/pages/tasks/TasksPage.vue'),
        meta: { title: '任务中心', featureKey: 'tasks' },
      },
      {
        path: 'tasks/:taskId',
        name: 'task-detail',
        component: () => import('@/pages/tasks/TaskDetailPage.vue'),
        meta: { title: '任务详情', featureKey: 'tasks' },
      },
      {
        path: 'sessions',
        name: 'sessions',
        component: () => import('@/pages/sessions/SessionsPage.vue'),
        meta: { title: '会话历史', featureKey: 'sessions' },
      },
      {
        path: 'approvals',
        name: 'approvals',
        component: () => import('@/pages/approvals/ApprovalsPage.vue'),
        meta: { title: '安全审批中心', featureKey: 'approvals' },
      },
      {
        path: 'templates',
        name: 'templates',
        component: () => import('@/pages/templates/TemplatesPage.vue'),
        meta: { title: '任务模板' },
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

// Navigation Guard: In real mode, enforce local session check
router.beforeEach(async (to, _from, next) => {
  if (
    to.path === '/connect' ||
    to.path.startsWith('/onboarding') ||
    to.path.startsWith('/dev')
  ) {
    next()
    return
  }

  const authStore = useLocalAuthStore()
  if (authStore.isMockMode) {
    next()
    return
  }

  if (!authStore.authenticated) {
    const isAuthed = await authStore.checkAuthStatus()
    if (!isAuthed) {
      next({ path: '/connect', query: { redirect: to.fullPath } })
      return
    }
  }
  next()
})
