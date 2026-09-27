import { createI18n } from 'vue-i18n'
import { REMOTE_LINK_ERROR_MESSAGES } from './remote-link-errors'

const zhCN = {
  app: {
    name: 'HQAgent-Hub',
    subtitle: 'AI 团队本地控制中心',
  },
  theme: {
    mode: '外观模式',
    palette: '主题配色',
    density: '显示密度',
    contrast: '对比度',
    fontScale: '字号大小',
    modes: {
      system: '跟随系统',
      light: '浅色模式',
      dark: '深色模式',
    },
    densities: {
      comfortable: '舒适 (默认)',
      compact: '紧凑 (高密度)',
    },
    contrasts: {
      normal: '标准对比度',
      high: '高对比度 (无障碍)',
    },
  },
  status: {
    ready: '就绪',
    busy: '执行中',
    offline: '离线',
    error: '异常',
    not_logged_in: '未登录',
    incompatible: '版本不兼容',
    discovering: '正在探测',
    disabled: '已停用',
  },
  task: {
    status: {
      draft: '草稿',
      queued: '排队中',
      running: '执行中',
      waiting_approval: '等待安全审批',
      paused: '已暂停',
      succeeded: '执行成功',
      failed: '执行失败',
      cancelled: '已取消',
    },
  },
  role: {
    orchestrator: '总控调度',
    architect: '系统架构',
    frontend_implementer: '前端开发',
    general_implementer: '全栈实现',
    reviewer: '代码审查',
    tester: '测试验证',
    deployer: '构建部署',
    integrator: '分支集成',
  },
  remoteErrors: REMOTE_LINK_ERROR_MESSAGES,
}

export const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  messages: {
    'zh-CN': zhCN,
  },
})

export { REMOTE_LINK_ERROR_MESSAGES, getRemoteLinkErrorMessage } from './remote-link-errors'
