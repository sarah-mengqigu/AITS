import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const BACKEND = 'http://127.0.0.1:8000'
const BACKEND_WS = 'ws://127.0.0.1:8000'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        // Dart Sass 1.80+ 对 Vite 5 legacy API 的提示（仅噪声，不影响构建）
        silenceDeprecations: ['legacy-js-api'],
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: false,
    proxy: {
      // 使用带边界的正则，避免 /api-testing 这类前端路由被 /api 代理截获
      '^/api/': {
        target: BACKEND,
        changeOrigin: true,
      },
      '^/media/': {
        target: BACKEND,
        changeOrigin: true,
      },
      '^/ws/': {
        target: BACKEND_WS,
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ['vue', 'vue-router', 'pinia'],
          element: ['element-plus', '@element-plus/icons-vue'],
          charts: ['echarts', 'vue-echarts'],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.js'],
    include: ['tests/**/*.spec.js'],
    css: false,
  },
})
