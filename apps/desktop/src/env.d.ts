/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

interface ImportMetaEnv {
  readonly VITE_GATEWAY_MODE?: 'mock' | 'local' | 'remote'
  readonly VITE_REMOTE_MOCK?: string
  readonly VITE_DEFAULT_REMOTE_SERVER?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
