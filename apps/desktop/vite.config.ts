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
