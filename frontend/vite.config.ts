import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

function splitMolstarChunk(id: string): string | undefined {
  if (!id.includes('/node_modules/molstar/')) return undefined

  if (
    id.includes('/lib/apps/viewer/') ||
    id.includes('/lib/mol-plugin-ui/') ||
    id.includes('/lib/mol-plugin/') ||
    id.includes('/lib/mol-plugin-state/')
  ) {
    return 'molstar-viewer'
  }

  if (
    id.includes('/lib/mol-gl/') ||
    id.includes('/lib/mol-canvas3d/') ||
    id.includes('/lib/mol-geo/') ||
    id.includes('/lib/mol-repr/') ||
    id.includes('/lib/mol-theme/')
  ) {
    return 'molstar-rendering'
  }

  if (
    id.includes('/lib/mol-model/') ||
    id.includes('/lib/mol-model-formats/') ||
    id.includes('/lib/mol-model-props/') ||
    id.includes('/lib/mol-io/') ||
    id.includes('/lib/mol-script/')
  ) {
    return 'molstar-model'
  }

  if (
    id.includes('/lib/mol-data/') ||
    id.includes('/lib/mol-math/') ||
    id.includes('/lib/mol-state/') ||
    id.includes('/lib/mol-task/') ||
    id.includes('/lib/mol-util/')
  ) {
    return 'molstar-core'
  }

  return 'molstar-extensions'
}

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
    // 仅监听回环地址，避免开发服务器默认暴露到局域网（如需真机联调显式改此值）。
    host: '127.0.0.1',
    watch: {
      usePolling: true,
      interval: 1000
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          const molstarChunk = splitMolstarChunk(id)
          if (molstarChunk) return molstarChunk
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
