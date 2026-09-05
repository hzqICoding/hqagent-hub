import type { UiGateway } from '@hqagent/protocol'
import { mockGateway } from './mock-gateway'
import { localHubGateway } from './local-hub-gateway'

export * from '@hqagent/protocol'
export { mockGateway, MockGateway } from './mock-gateway'
export { localHubGateway, LocalHubGateway } from './local-hub-gateway'

export function getUiGateway(): UiGateway {
  const mode = import.meta.env.VITE_GATEWAY_MODE || 'mock'
  if (mode === 'local') {
    return localHubGateway
  }
  return mockGateway
}
