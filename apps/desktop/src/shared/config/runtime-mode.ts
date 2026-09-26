export type AppRuntimeMode = 'local' | 'remote'

let runtimeModeOverride: AppRuntimeMode | null = null

export function setRuntimeModeForTesting(mode: AppRuntimeMode | null): void {
  runtimeModeOverride = mode
}

export function getRuntimeMode(): AppRuntimeMode {
  if (runtimeModeOverride) {
    return runtimeModeOverride
  }

  // 1. Explicit Vite env variable
  if (import.meta.env.VITE_GATEWAY_MODE === 'remote') {
    return 'remote'
  }

  // 2. URL path starts with /remote in browser
  if (typeof window !== 'undefined' && window.location.pathname.startsWith('/remote')) {
    return 'remote'
  }

  return 'local'
}

export const isRemoteMode = getRuntimeMode() === 'remote'
