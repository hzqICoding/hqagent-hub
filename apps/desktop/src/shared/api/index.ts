import type { UiGateway } from './ui-gateway'
import { mockGateway } from './mock-gateway'
import { localHubGateway } from './local-hub-gateway'

export * from '@hqagent/protocol'
export type { UiGateway, EventSubscription } from './ui-gateway'
export { mockGateway, MockGateway } from './mock-gateway'
export { localHubGateway, LocalHubGateway, HubApiError } from './local-hub-gateway'

export function getUiGateway(): UiGateway {
  const mode = import.meta.env.VITE_GATEWAY_MODE || 'mock'
  if (mode === 'local') {
    return localHubGateway
  }
  return mockGateway
}

// N0 Local Chat Gateways & Provider
export type { LocalChatGateway } from './local-chat-gateway.interface'
export { RealLocalChatGateway, realLocalChatGateway } from './local-chat-gateway'
export { MockLocalChatGateway, mockLocalChatGateway } from './mock-local-chat-gateway'
export {
  getLocalChatGateway,
  getLocalChatGatewayMode,
  setLocalChatGatewayMode,
  setLocalChatGatewayForTesting,
  type LocalChatGatewayMode,
} from './local-chat-provider'

