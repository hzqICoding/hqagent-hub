import { invoke } from '@tauri-apps/api/core'

export function isDesktopShell(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
}

export interface DesktopEndpoint { baseUrl: string; token: string }

export class ShellConnectionError extends Error {}

// Only coalesce concurrent IPC calls. Never persist credentials or reuse an endpoint
// across requests: the supervisor rotates both port and token on every Hub restart.
let pending: Promise<DesktopEndpoint> | null = null
export function getDesktopEndpoint(): Promise<DesktopEndpoint> {
  if (!pending) {
    pending = invoke<DesktopEndpoint>('get_hub_endpoint').then((endpoint) => {
      const url = new URL(endpoint.baseUrl)
      if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port
        || url.username || url.password || url.pathname !== '/' || url.search || url.hash || !endpoint.token) {
        throw new Error('桌面服务地址无效')
      }
      return endpoint
    }).catch((error: unknown) => {
      // Tauri rejects with serialized CommandError rather than a JS Error.
      if (error && typeof error === 'object' && 'code' in error && 'message' in error
        && typeof error.message === 'string') throw new ShellConnectionError(error.message)
      throw error
    }).finally(() => { pending = null })
  }
  return pending
}
