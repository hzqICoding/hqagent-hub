import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
        '@hqagent/protocol': fileURLToPath(new URL('../../packages/protocol/generated/ts', import.meta.url)),
        '@hqagent/fixtures': fileURLToPath(new URL('../../packages/protocol/fixtures/contracts', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      strictPort: false,
      proxy: {
        '/api': {
          target: process.env.VITE_WORKER_BASE_URL || 'http://127.0.0.1:49210',
          changeOrigin: true,
        },
        '/ws': {
          target:
            process.env.VITE_WORKER_WS_URL ||
            (process.env.VITE_WORKER_BASE_URL
              ? process.env.VITE_WORKER_BASE_URL.replace(/^http/, 'ws')
              : 'ws://127.0.0.1:49210'),
          ws: true,
          changeOrigin: true,
        },
      },
    },
    build: {
      target: 'esnext',
      sourcemap: mode !== 'production',
      rollupOptions: {
        output: {
          manualChunks: {
            vendor: ['vue', 'vue-router', 'pinia', 'lucide-vue-next'],
            echarts: ['echarts'],
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      include: ['src/**/*.{test,spec}.{js,ts,jsx,tsx}'],
    },
  }
})
