import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('WebSocket 组合式函数应使用统一 ws 地址配置并对齐后端 action 协议', () => {
  const source = readSource('src/composables/useWebSocket.ts')

  assert.equal(source.includes('VITE_WS_URL'), true)
  assert.equal(source.includes('VITE_WS_HOST'), false)
  assert.equal(source.includes('console.log'), false)
  assert.equal(source.includes('import.meta.env.DEV'), true)
  assert.equal(source.includes("action: 'ping'"), true)
  assert.equal(source.includes("action: 'subscribe_task'"), true)
  assert.equal(source.includes("action: 'unsubscribe_task'"), true)
})

test('任务详情页应连接任务专用 WebSocket 端点并兼容后端任务消息类型', () => {
  const source = readSource('src/views/tasks/Detail.vue')
  const liveUpdatesSource = readSource('src/composables/useTaskDetailLiveUpdates.ts')
  const websocketDomainSource = readSource('src/domain/tasks/websocket.ts')

  assert.equal(source.includes('useTaskDetailLiveUpdates'), true)
  assert.equal(liveUpdatesSource.includes('/api/v1/ws/tasks/'), true)
  assert.equal(source.includes("from '@/domain/tasks'"), true)
  assert.equal(liveUpdatesSource.includes('resolveTaskWebSocketProgressUpdate'), true)
  assert.equal(liveUpdatesSource.includes('resolveTaskWebSocketLog'), true)
  assert.equal(websocketDomainSource.includes("message.type === 'task_progress'"), true)
  assert.equal(websocketDomainSource.includes("message.type === 'task_log'"), true)
  assert.equal(websocketDomainSource.includes("message.type === 'task_complete'"), true)
  assert.equal(websocketDomainSource.includes("message.type === 'task_error'"), true)
  assert.equal(websocketDomainSource.includes("message.type === 'task_status'"), true)
  assert.equal(websocketDomainSource.includes('progress_percent'), true)
})

test('任务列表页不应再建立无订阅的通用 WebSocket 连接', () => {
  const source = readSource('src/views/tasks/List.vue')

  assert.equal(source.includes("import { useWebSocket } from '@/composables/useWebSocket'"), false)
  assert.equal(source.includes('const { connect, disconnect, onMessage } = useWebSocket()'), false)
  assert.equal(source.includes('connect()'), false)
  assert.equal(source.includes('onMessage(handleWSMessage)'), false)
})

test('Vite 的 /api 代理应允许 WebSocket upgrade', () => {
  const source = readSource('vite.config.ts')
  const apiProxyBlock = source.match(/['"]\/api['"]:\s*\{([\s\S]*?)\n\s*\},\n\s*['"]\/ws['"]:/)

  assert.ok(apiProxyBlock)
  assert.match(apiProxyBlock[1], /target:\s*['"]http:\/\/localhost:8000['"]/)
  assert.match(apiProxyBlock[1], /changeOrigin:\s*true/)
  assert.match(apiProxyBlock[1], /ws:\s*true/)
})

test('中英文 locale 应补齐 tools.runs 文案', () => {
  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')

  assert.match(zhSource, /runs:\s*'[^']+'/)
  assert.match(enSource, /runs:\s*'[^']+'/)
})
