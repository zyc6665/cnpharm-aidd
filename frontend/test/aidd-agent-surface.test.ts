import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('前端应存在 AIDD agent API 和 store', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/api/agents.ts')), true)
  assert.equal(existsSync(resolve(rootDir, 'src/stores/agents.ts')), true)

  const apiSource = readSource('src/api/agents.ts')
  const storeSource = readSource('src/stores/agents.ts')
  const apiIndexSource = readSource('src/api/index.ts')
  const storeIndexSource = readSource('src/stores/index.ts')

  assert.equal(apiSource.includes('createAiddAgentRun'), true)
  assert.equal(apiSource.includes('getAiddAgentRun'), true)
  assert.equal(apiSource.includes('syncAiddAgentRun'), true)
  assert.equal(storeSource.includes('useAgentsStore'), true)
  assert.equal(storeSource.includes('pollRunUntilTerminal'), true)
  assert.equal(storeSource.includes('currentRun.value = res.data.items[0] ?? null'), true)
  assert.equal(apiIndexSource.includes("export * from './agents'"), true)
  assert.equal(storeIndexSource.includes('useAgentsStore'), true)
})

test('Agent API 和 store 应支持独立的工作流草稿生成状态', () => {
  const apiSource = readSource('src/api/agents.ts')
  const storeSource = readSource('src/stores/agents.ts')
  const modelsSource = readSource('src/types/models.d.ts')

  assert.equal(modelsSource.includes('export interface AiddWorkflowDraft'), true)
  assert.equal(modelsSource.includes('definition: WorkflowDefinition'), true)
  assert.equal(apiSource.includes('createAiddWorkflowDraft'), true)
  assert.equal(apiSource.includes("'/agents/aidd/workflow-drafts'"), true)
  assert.equal(storeSource.includes('const drafting = ref(false)'), true)
  assert.equal(storeSource.includes('const createWorkflowDraft = async'), true)
  assert.equal(storeSource.includes('drafting.value = true'), true)
  assert.equal(storeSource.includes('drafting.value = false'), true)
  assert.equal(storeSource.includes('createWorkflowDraft,'), true)
})

test('工作台应挂载 AIDD agent 入口组件', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/workflow/AiddAgentPanel.vue')), true)
  const workflowSource = readSource('src/views/workflow/index.vue')
  const panelSource = readSource('src/components/workflow/AiddAgentPanel.vue')

  assert.equal(workflowSource.includes('AiddAgentPanel'), true)
  assert.equal(workflowSource.includes('a-tabs'), true)
  assert.equal(workflowSource.includes("activeMode"), true)
  assert.equal(workflowSource.includes("workflow.mode.manual"), true)
  assert.equal(workflowSource.includes("workflow.mode.agent"), true)
  assert.equal(workflowSource.indexOf('AiddAgentPanel') > workflowSource.indexOf('workflow.mode.agent'), true)
  assert.equal(panelSource.includes('createAiddWorkflowDraft'), true)
  assert.equal(panelSource.includes('generateWorkflowDraft'), true)
  assert.equal(panelSource.includes('draft-only-description'), true)
  assert.equal(panelSource.includes('input_type'), false)
  assert.equal(panelSource.includes('workflow.agent.inputType'), false)
  assert.equal(panelSource.includes('a-radio-group'), false)
  assert.equal(panelSource.includes('generationCount'), false)
  assert.equal(panelSource.includes('a-input-number'), false)
  assert.equal(panelSource.includes('syncRun'), false)
  assert.equal(panelSource.includes('/tasks/'), false)
  assert.equal(panelSource.includes('agent-control-panel'), true)
  assert.equal(panelSource.includes('agent-runtime-panel'), true)
  assert.equal(panelSource.includes('capabilityOptions'), true)
  assert.equal(panelSource.includes('capability-strip'), true)
  assert.equal(panelSource.includes('LVPocket'), false)
  assert.equal(panelSource.includes('GCDM'), false)
  assert.equal(panelSource.includes('fetchRuns'), false)
  assert.equal(panelSource.includes('run-meta'), false)
  assert.equal(panelSource.includes('智能体设计工作区'), false)
})

test('Agent store keeps history APIs while panel remains draft-only', () => {
  const apiSource = readSource('src/api/agents.ts')
  const storeSource = readSource('src/stores/agents.ts')
  const panelSource = readSource('src/components/workflow/AiddAgentPanel.vue')

  assert.equal(apiSource.includes('deleteAiddAgentRun'), true)
  assert.equal(storeSource.includes('deleteRun'), true)
  assert.equal(panelSource.includes('agent-history-panel'), false)
  assert.equal(panelSource.includes('historyRuns'), false)
  assert.equal(panelSource.includes('workflow.agent.history'), false)
  assert.equal(panelSource.includes('agent-runtime-panel'), true)
  assert.equal(panelSource.includes('draftOnlyDescription'), true)
  assert.equal(panelSource.includes('reasoning_content'), false)
})

test('Agent 面板应支持普通多文件上传并提交 input_file_ids', () => {
  const panelSource = readSource('src/components/workflow/AiddAgentPanel.vue')
  const modelsSource = readSource('src/types/models.d.ts')
  const zhSource = readSource('src/locales/zh-CN/index.ts')

  assert.equal(modelsSource.includes('input_file_ids?: string[]'), true)
  assert.equal(modelsSource.includes('input_files?: Record<string, string>'), true)
  assert.equal(modelsSource.includes('input_files: Record<string, string>'), true)
  assert.equal(panelSource.includes('agentFileUploads'), true)
  assert.equal(panelSource.includes(':multiple="true"'), true)
  assert.equal(panelSource.includes('input_file_ids: uploadedFileIds'), true)
  assert.equal(panelSource.includes('semanticFileUploads'), false)
  assert.equal(panelSource.includes('semanticFileOptions'), false)
  assert.equal(panelSource.includes('input_files: uploadedSemanticFiles'), false)
  assert.equal(zhSource.includes('自动识别文件类型'), true)
  assert.equal(zhSource.includes('配体 PDB'), false)
  assert.equal(zhSource.includes('SMILES CSV'), false)
})

test('Agent 面板应生成草稿并把结果交给工作流页面', () => {
  const panelSource = readSource('src/components/workflow/AiddAgentPanel.vue')
  const workflowSource = readSource('src/views/workflow/index.vue')
  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')

  assert.equal(panelSource.includes('defineEmits'), true)
  assert.equal(panelSource.includes('prepareAgentRequest'), true)
  assert.equal(panelSource.includes('generateWorkflowDraft'), true)
  assert.equal(panelSource.includes('createAiddWorkflowDraft(request)'), true)
  assert.equal(panelSource.includes("emit('draftGenerated', response.data, selectedProjectId.value)"), true)
  assert.equal(panelSource.includes('workflow.agent.generateDraft'), true)
  assert.equal(workflowSource.includes('@draft-generated="handleAgentWorkflowDraft"'), true)
  assert.equal(workflowSource.includes('applyWorkflowDraft(draft)'), true)
  assert.equal(workflowSource.includes("activeMode.value = 'manual'"), true)
  assert.equal(zhSource.includes('生成工作流草稿'), true)
  assert.equal(enSource.includes('Generate Workflow Draft'), true)
})
