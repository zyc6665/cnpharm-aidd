import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { test } from 'vitest'
import assert from 'node:assert/strict'

const rootDir = resolve(__dirname, '..')

function readSource(path: string) {
  return readFileSync(resolve(rootDir, path), 'utf-8')
}

test('长任务同步接口应显式使用长超时并允许传入取消信号', () => {
  const requestSource = readSource('src/api/request.ts')
  const workflowApiSource = readSource('src/api/workflows.ts')
  const agentApiSource = readSource('src/api/agents.ts')

  assert.equal(requestSource.includes('export const LONG_RUNNING_TIMEOUT_MS = 0'), true)
  assert.equal(workflowApiSource.includes('type RequestOptions'), true)
  assert.equal(agentApiSource.includes('type RequestOptions'), true)
  assert.equal(workflowApiSource.includes('timeout: options?.timeout ?? LONG_RUNNING_TIMEOUT_MS'), true)
  assert.equal(agentApiSource.includes('timeout: options?.timeout ?? LONG_RUNNING_TIMEOUT_MS'), true)
  const workflowSyncSignature =
    /syncWorkflowRun\s*=\s*\(\s*runId:\s*string,\s*options\?:\s*RequestOptions\s*\)/
  const agentSyncSignature =
    /syncAiddAgentRun\s*=\s*\(\s*runId:\s*string,\s*options\?:\s*RequestOptions\s*\)/
  assert.equal(workflowSyncSignature.test(workflowApiSource), true)
  assert.equal(agentSyncSignature.test(agentApiSource), true)
})

test('任务轮询接口应支持 AbortController 取消和一次网络重试', () => {
  const requestSource = readSource('src/api/request.ts')
  const tasksApiSource = readSource('src/api/tasks.ts')
  const workflowExecutionSource = readSource('src/composables/useWorkflowExecution.ts')

  assert.equal(requestSource.includes('isCanceledRequest'), true)
  assert.equal(requestSource.includes('!isCanceledRequest && retryCount < retryLimit'), true)
  assert.equal(tasksApiSource.includes('getTaskDetail = (id: string, options?: RequestOptions)'), true)
  assert.equal(workflowExecutionSource.includes('AbortController'), true)
  assert.equal(workflowExecutionSource.includes('onScopeDispose'), true)
  assert.equal(workflowExecutionSource.includes('signal: pollController.signal'), true)
  assert.equal(workflowExecutionSource.includes('retry: 1'), true)
  assert.equal(workflowExecutionSource.includes('cancelActivePolling'), true)
})
