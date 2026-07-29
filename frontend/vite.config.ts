import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      'h264-mp4-encoder': resolve(
        __dirname,
        'node_modules/h264-mp4-encoder/embuild/dist/h264-mp4-encoder.web.js'
      )
    }
  },
  css: {
    preprocessorOptions: {
      less: {
        javascriptEnabled: true,
        additionalData: `@import "@/assets/styles/variables.less";`
      }
    }
  },
  server: {
    port: 3000,
    host: '0.0.0.0',
    watch: {
      usePolling: true,
      interval: 1000
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true
      }
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/molstar/')) return 'molstar'
          if (id.includes('/node_modules/echarts/')) return 'echarts'
          if (
            id.includes('/node_modules/ant-design-vue/') ||
            id.includes('/node_modules/@ant-design/icons-vue/')
          ) {
            return 'ant-design-vue'
          }
          if (
            id.includes('/node_modules/vue/') ||
            id.includes('/node_modules/vue-router/') ||
            id.includes('/node_modules/pinia/')
          ) {
            return 'vue-vendor'
          }
        }
      }
    }
  }
})
