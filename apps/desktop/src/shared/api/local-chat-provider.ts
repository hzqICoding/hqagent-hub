import type { LocalChatGateway } from './local-chat-gateway.interface'
import { realLocalChatGateway } from './local-chat-gateway'
import { mockLocalChatGateway } from './mock-local-chat-gateway'
import { isDesktopShell } from './desktop-endpoint'

export type LocalChatGatewayMode = 'real' | 'mock'

const STORAGE_KEY = 'hqagent_local_chat_mode'

// Default mode is 'mock' in dev if explicitly chosen or defaulted, otherwise 'real'
let currentMode: LocalChatGatewayMode = (() => {
  if (typeof window !== 'undefined') {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'real' || saved === 'mock') {
      return saved
    }
  }
  // If VITE_GATEWAY_MODE is explicitly set to mock
  if (import.meta.env.VITE_GATEWAY_MODE === 'mock') {
    return 'mock'
  }
  return 'real'
})()

export function getLocalChatGatewayMode(): LocalChatGatewayMode {
  return isDesktopShell() ? 'real' : currentMode
}

export function setLocalChatGatewayMode(mode: LocalChatGatewayMode): void {
  if (isDesktopShell()) { currentMode = 'real'; return }
  currentMode = mode
  if (typeof window !== 'undefined') {
    localStorage.setItem(STORAGE_KEY, mode)
  }
}

let currentGatewayOverride: LocalChatGateway | null = null

export function setLocalChatGatewayForTesting(gateway: LocalChatGateway | null): void {
  currentGatewayOverride = gateway
}

export function getLocalChatGateway(): LocalChatGateway {
  if (currentGatewayOverride) {
    return currentGatewayOverride
  }
  if (getLocalChatGatewayMode() === 'mock') {
    return mockLocalChatGateway
  }
  return realLocalChatGateway
}
