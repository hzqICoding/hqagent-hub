import type { IRemoteGateway } from './remote-gateway.interface'
import { remoteGateway } from './remote-gateway'
import { mockRemoteGateway } from './mock-remote-gateway'

let currentRemoteGateway: IRemoteGateway | null = null

export function setRemoteGatewayForTesting(gateway: IRemoteGateway | null): void {
  currentRemoteGateway = gateway
}

export function getRemoteGateway(): IRemoteGateway {
  if (currentRemoteGateway) {
    return currentRemoteGateway
  }

  // If VITE_REMOTE_MOCK is set or mode is mock
  if (
    import.meta.env.VITE_REMOTE_MOCK === 'true' ||
    import.meta.env.VITE_GATEWAY_MODE === 'mock' ||
    import.meta.env.MODE === 'mock'
  ) {
    return mockRemoteGateway
  }

  return remoteGateway
}

export { remoteGateway, RemoteGateway, RemoteApiError } from './remote-gateway'
export { mockRemoteGateway, MockRemoteGateway } from './mock-remote-gateway'
export type { IRemoteGateway } from './remote-gateway.interface'
