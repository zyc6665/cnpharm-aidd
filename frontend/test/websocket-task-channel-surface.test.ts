import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('任务实时通道应使用 SSE，而不是自研 WebSocket 客户端', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/composables/useWebSocket.ts')), false)
  assert.equal(existsSync(resolve(rootDir, 'src/domain/tasks/websocket.ts')), false)

  const eventsSource = readSource('src/api/task-events.ts')
  assert.equal(eventsSource.includes('EventSource'), true)
  assert.equal(eventsSource.includes('/api/v1/tasks/'), true)
  assert.equal(eventsSource.includes('/events'), true)
  // 认证改由 httpOnly Cookie 承载，不再把 token 拼进查询参数。
  assert.equal(eventsSource.includes('token='), false)
  assert.equal(eventsSource.includes('withCredentials: true'), true)
})

test('任务详情页应订阅任务事件流并保留终态刷新', () => {
  const source = readSource('src/views/tasks/Detail.vue')
  const liveUpdatesSource = readSource('src/composables/useTaskDetailLiveUpdates.ts')

  assert.equal(source.includes('useTaskDetailLiveUpdates'), true)
  assert.equal(source.includes("from '@/domain/tasks'"), true)
  assert.equal(liveUpdatesSource.includes('openTaskEventStream'), true)
  assert.equal(liveUpdatesSource.includes('onSnapshot'), true)
  assert.equal(liveUpdatesSource.includes('onDone'), true)
  assert.equal(liveUpdatesSource.includes('resolveTaskWebSocketProgressUpdate'), false)
  assert.equal(liveUpdatesSource.includes('useWebSocket'), false)
})

test('SSE 不可用时才回退轮询，且间隔不小于 2 秒', () => {
  const liveUpdatesSource = readSource('src/composables/useTaskDetailLiveUpdates.ts')

  // docs/10 API-08：禁止前端轮询间隔 < 2s。
  assert.equal(liveUpdatesSource.includes('intervalMs ?? 5000'), true)
  assert.equal(liveUpdatesSource.includes('streamConnected'), true)
  assert.equal(liveUpdatesSource.includes("taskStatus.value === 'running'"), true)
})

test('任务列表页不应建立自研 WebSocket 连接', () => {
  const source = readSource('src/views/tasks/List.vue')

  assert.equal(source.includes('useWebSocket'), false)
  assert.equal(source.includes('onMessage(handleWSMessage)'), false)
})

test('Vite 的 /api 代理不再需要 WebSocket upgrade', () => {
  const source = readSource('vite.config.ts')

  assert.equal(source.includes('ws: true'), false)
  assert.equal(source.includes("'/ws'"), false)
  assert.match(source, /'\/api':\s*\{\s*target:\s*'http:\/\/localhost:8000'/)
})

test('中英文 locale 应补齐 tools.runs 文案', () => {
  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')

  assert.match(zhSource, /runs:\s*'[^']+'/)
  assert.match(enSource, /runs:\s*'[^']+'/)
})
