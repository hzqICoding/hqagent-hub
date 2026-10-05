import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import AppLayout from '../layouts/AppLayout.vue'
import LocalChatLayout from '../layouts/LocalChatLayout.vue'
import { useLocalAuthStore } from '@/stores/local-auth.store'
import { useRemoteAuthStore } from '@/stores/remote-auth.store'
import { getRuntimeMode } from '@/shared/config/runtime-mode'
import { isDesktopShell } from '@/shared/api/desktop-endpoint'

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
    path: '/settings',
    component: LocalChatLayout,
    children: [{ path: '', name: 'settings', component: () => import('@/pages/settings/SettingsPage.vue'), meta: { title: '系统设置' } }],
  },
  {
    path: '/agents',
    component: LocalChatLayout,
    children: [{ path: '', name: 'agents', component: () => import('@/pages/settings/SettingsPage.vue'), props: { initialTab: 'agents' }, meta: { title: 'Agent 与模型' } }],
  },
  {
    path: '/scenes',
    component: LocalChatLayout,
    children: [{ path: '', name: 'scenes', component: () => import('@/pages/settings/SettingsPage.vue'), props: { initialTab: 'scenes' }, meta: { title: '场景与角色配置' } }],
  },
  {
    path: '/remote/login',
    name: 'remote-login',
    component: () => import('@/pages/remote/RemoteLoginPage.vue'),
    meta: { title: '远程登录' },
  },
  {
    path: '/remote/pair',
    name: 'remote-pair',
    component: () => import('@/pages/remote/RemotePairingPage.vue'),
    meta: { title: '设备配对' },
  },
  {
    path: '/remote',
    redirect: '/remote/devices',
  },
  {
    path: '/remote/devices',
    name: 'remote-devices',
    component: () => import('@/pages/remote/RemoteDevicesPage.vue'),
    meta: { title: '我的电脑' },
  },
  {
    path: '/remote/tokens',
    name: 'remote-tokens',
    component: () => import('@/pages/remote/RemoteTokensPage.vue'),
    meta: { title: 'API 令牌' },
  },
  {
    path: '/remote/chat',
    name: 'remote-chat',
    component: () => import('@/pages/remote/RemoteChatPage.vue'),
    meta: { title: '远程对话工作台' },
  },
  {
    path: '/remote-link',
    component: LocalChatLayout,
    children: [{ path: '', name: 'remote-link', component: () => import('@/pages/settings/SettingsPage.vue'), props: { initialTab: 'remote-link' }, meta: { title: '连接手机' } }],
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
        redirect: '/settings',
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
  if (isDesktopShell()) {
    // DesktopConnection owns readiness/recovery; no browser connection-code route.
    if (to.path === '/connect' || to.path.startsWith('/remote/') || to.path === '/remote') next('/chat')
    else next()
    return
  }
  // 1. Remote routes guard
  if (to.path === '/remote' || to.path.startsWith('/remote/')) {
    const remoteAuthStore = useRemoteAuthStore()

    // B7: Extract #code=... if arriving at /remote/pair with hash
    if (to.path === '/remote/pair') {
      const hashStr = (typeof window !== 'undefined' ? window.location.hash : to.hash) || ''
      const match = hashStr.match(/code=([A-Za-z0-9]{8})(?:&|$)/)
      if (match) {
        remoteAuthStore.pendingPairCode = match[1].toUpperCase()
        if (typeof window !== 'undefined' && window.history?.replaceState) {
          window.history.replaceState(null, '', window.location.pathname + window.location.search)
        }
      }
    }

    if (to.path === '/remote/login') {
      next()
      return
    }

    if (!remoteAuthStore.isAuthenticated) {
      const ok = await remoteAuthStore.checkSession()
      if (!ok) {
        const redirectPath = to.path
        next({ path: '/remote/login', query: { redirect: redirectPath } })
        return
      }
    }
    next()
    return
  }

  // 2. If running in remote mode and user visits root / or /chat or /remote, redirect to /remote/devices
  if (getRuntimeMode() === 'remote' && (to.path === '/' || to.path === '/chat' || to.path === '/remote')) {
    next('/remote/devices')
    return
  }

  // 3. Local desktop mode guards (unchanged)
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
