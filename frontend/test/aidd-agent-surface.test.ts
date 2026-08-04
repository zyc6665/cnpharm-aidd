import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
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

test('项目会话 API 承接 agent-run 查询、详情和取消', () => {
  const conversationsSource = readSource('src/api/conversations.ts')

  assert.equal(conversationsSource.includes('getProjectAgentRuns'), true)
  assert.equal(conversationsSource.includes('getProjectAgentRun'), true)
  assert.equal(conversationsSource.includes('cancelProjectAgentRun'), true)
  assert.equal(conversationsSource.includes('`/projects/${projectId}/agent-runs`'), true)
  assert.equal(conversationsSource.includes('`/projects/${projectId}/agent-runs/${runId}`'), true)
  assert.equal(conversationsSource.includes('/agents/aidd'), false)
})

test('Workflow Agent 模式进入项目研究会话，不再生成旧工作流草稿', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/workflow/AiddAgentPanel.vue')), true)
  const workflowSource = readSource('src/views/workflow/index.vue')
  const panelSource = readSource('src/components/workflow/AiddAgentPanel.vue')
  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')

  assert.equal(workflowSource.includes('<AiddAgentPanel />'), true)
  assert.equal(workflowSource.includes('@draft-generated="handleAgentWorkflowDraft"'), false)
  assert.equal(panelSource.includes("from '@/api/conversations'"), true)
  assert.equal(panelSource.includes('createProjectConversation'), true)
  assert.equal(panelSource.includes('startProjectAgentRun'), true)
  assert.equal(panelSource.includes("name: 'ProjectResearch'"), true)
  assert.equal(panelSource.includes('createAiddWorkflowDraft'), false)
  assert.equal(panelSource.includes('uploadFile'), false)
  assert.equal(panelSource.includes('input_file_ids'), false)
  assert.equal(zhSource.includes('进入项目智能体'), true)
  assert.equal(enSource.includes('Open Project Agent'), true)
})
