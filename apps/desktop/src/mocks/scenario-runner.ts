import { ref } from 'vue'
import { mockGateway, type MockScenario } from '../shared/api/mock-gateway'

export interface ScenarioMeta {
  id: MockScenario
  name: string
  description: string
}

export const AVAILABLE_SCENARIOS: ScenarioMeta[] = [
  {
    id: 'happy-path',
    name: '正常全流程 (Happy Path)',
    description: 'Agent 正常在线，多角色协作运行中，有待处理审批',
  },
  {
    id: 'first-run-no-agent',
    name: '首次运行无 Agent',
    description: '模拟未检测到任何本地 Agent 时的引导与空状态',
  },
  {
    id: 'task-running',
    name: '多 Agent 协作进行中',
    description: 'Architect 完成，Frontend 实现中，Reviewer 排队中',
  },
  {
    id: 'task-waiting-approval',
    name: '任务等待审批 (Waiting Approval)',
    description: '触发 git_push 高风险命令，等待用户二次确认',
  },
  {
    id: 'task-failed',
    name: '任务失败与越界拦截',
    description: '前端尝试越界写后端目录，被 PermissionEngine 拦截',
  },
  {
    id: 'update-downloading',
    name: 'OTA 下载中',
    description: '显示 68.5% 下载进度与断点续传能力',
  },
  {
    id: 'update-draining',
    name: 'OTA Task Drain 排空保护',
    description: '升级安装前进入维护模式，等待正在运行的任务安全保存',
  },
  {
    id: 'hub-disconnected',
    name: 'Local Hub 断开连接',
    description: '模拟 127.0.0.1 端口失联，展示全局离线与重连引导',
  },
]

export function useScenarioRunner() {
  const currentScenario = ref<MockScenario>(mockGateway.getScenario())
  const isStreaming = ref(false)
  let streamTimer: ReturnType<typeof setInterval> | null = null

  function switchScenario(scenario: MockScenario) {
    currentScenario.value = scenario
    mockGateway.setScenario(scenario)
  }

  function startEventStream() {
    if (isStreaming.value) return
    isStreaming.value = true

    let step = 0
    streamTimer = setInterval(() => {
      step++
      const roles = ['architect', 'frontend_implementer', 'reviewer', 'tester']
      const currentRole = roles[step % roles.length]

      mockGateway.emitMockEvent({
        type: 'agent.progress',
        payload: {
          step,
          role: currentRole,
          log: `[${new Date().toLocaleTimeString()}] ${currentRole} 执行进度更新: 步骤 #${step} 校验完成`,
        },
      })
    }, 1200)
  }

  function stopEventStream() {
    if (streamTimer) {
      clearInterval(streamTimer)
      streamTimer = null
    }
    isStreaming.value = false
  }

  return {
    currentScenario,
    availableScenarios: AVAILABLE_SCENARIOS,
    isStreaming,
    switchScenario,
    startEventStream,
    stopEventStream,
  }
}
