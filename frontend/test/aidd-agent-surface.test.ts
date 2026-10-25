import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('前端不再暴露旧 /agents/aidd API 和旧智能体 store', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/api/agents.ts')), false)
  assert.equal(existsSync(resolve(rootDir, 'src/stores/agents.ts')), false)

  const apiIndexSource = readSource('src/api/index.ts')
  const storeIndexSource = readSource('src/stores/index.ts')
  const taskListSource = readSource('src/views/tasks/List.vue')

  assert.equal(apiIndexSource.includes("export * from './agents'"), false)
  assert.equal(storeIndexSource.includes('useAgentsStore'), false)
  assert.equal(taskListSource.includes('useAgentsStore'), false)
  assert.equal(taskListSource.includes('fetchRuns'), false)
  assert.equal(taskListSource.includes('AgentRunTaskCard'), false)
  assert.equal(taskListSource.includes('agent-task-grouping'), false)
})

test('项目会话与 Agent 覆盖层已从交付线移除', () => {
  for (const removed of [
    'src/api/conversations.ts',
    'src/api/agent-stream.ts',
    'src/stores/project-conversation.ts',
    'src/types/conversations.ts',
    'src/composables/useAgentEventStream.ts',
    'src/components/workflow/AiddAgentPanel.vue',
    'src/components/conversation/MessageTimeline.vue',
    'src/components/conversation/ConversationSidebar.vue',
    'src/views/projects/Research.vue'
  ]) {
    assert.equal(existsSync(resolve(rootDir, removed)), false, `should be removed: ${removed}`)
  }
})

test('路由与工作流页面不再暴露 Agent 模式入口', () => {
  const routerSource = readSource('src/router/index.ts')
  const workflowSource = readSource('src/views/workflow/index.vue')
  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')

  assert.equal(routerSource.includes('ProjectResearch'), false)
  assert.equal(routerSource.includes('/research/'), false)
  assert.equal(workflowSource.includes('AiddAgentPanel'), false)
  assert.equal(workflowSource.includes('key="agent"'), false)
  assert.equal(zhSource.includes('进入项目智能体'), false)
  assert.equal(enSource.includes('Open Project Agent'), false)
})

test('已删除的 Agent 覆盖层不再被残留引用', () => {
  const offenders: string[] = []
  const walk = (dir: string): void => {
    for (const entry of readdirSync(resolve(rootDir, dir), { withFileTypes: true })) {
      const rel = `${dir}/${entry.name}`
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === 'dist') continue
        walk(rel)
        continue
      }
      if (!/\.(ts|vue)$/.test(entry.name)) continue
      const source = readSource(rel)
      for (const needle of [
        '@/api/conversations',
        '@/api/agent-stream',
        '@/types/conversations',
        '@/stores/project-conversation',
        'useAgentEventStream'
      ]) {
        if (source.includes(needle)) offenders.push(`${rel}: ${needle}`)
      }
    }
  }
  walk('src')
  assert.deepEqual(offenders, [])
})
