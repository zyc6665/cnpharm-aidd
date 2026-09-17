import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { buildWorkflowArtifactHierarchy } from '../src/workflow/artifact-hierarchy.ts'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

function resolveSource(relativePath: string): string {
  return resolve(rootDir, relativePath)
}

test('工作台应存在共享产物四级层级派生器，并按分组顺序确定主分组', async () => {
  const modulePath = resolveSource('src/workflow/artifact-hierarchy.ts')

  assert.equal(
    existsSync(modulePath),
    true,
    '缺少 src/workflow/artifact-hierarchy.ts，共享层级派生器尚未实现'
  )

  assert.equal(typeof buildWorkflowArtifactHierarchy, 'function')

  const groups = [
    {
      id: 'group-alpha',
      name: 'Alpha',
      slug: 'alpha',
      tools: [
        { id: 'tool-dock', slug: 'dock', name: 'Dock' },
        { id: 'tool-shared', slug: 'shared', name: 'Shared Tool' }
      ]
    },
    {
      id: 'group-beta',
      name: 'Beta',
      slug: 'beta',
      tools: [
        { id: 'tool-shared', slug: 'shared', name: 'Shared Tool' },
        { id: 'tool-prop', slug: 'prop', name: 'Prop' }
      ]
    }
  ]

  const artifacts = [
    {
      id: 'artifact-1',
      task_id: 'task-shared',
      task_name: '共享口袋筛选批次',
      tool_id: 'tool-shared',
      tool_slug: 'shared',
      tool_name: 'Shared Tool',
      filename: 'results/shared-latest.sdf',
      content_type: 'chemical/x-mdl-sdfile',
      created_at: '2026-05-31T10:30:00Z'
    },
    {
      id: 'artifact-2',
      task_id: 'task-shared',
      task_name: '共享口袋筛选批次',
      tool_id: 'tool-shared',
      tool_slug: 'shared',
      tool_name: 'Shared Tool',
      filename: 'results/shared-old.sdf',
      content_type: 'chemical/x-mdl-sdfile',
      created_at: '2026-05-31T09:30:00Z'
    },
    {
      id: 'artifact-3',
      task_id: 'task-prop',
      tool_id: 'tool-prop',
      tool_slug: 'prop',
      tool_name: 'Prop',
      filename: 'reports/property.csv',
      content_type: 'text/csv',
      created_at: '2026-05-31T11:30:00Z'
    },
    {
      id: 'artifact-4',
      task_id: 'task-ungrouped',
      tool_id: 'tool-free',
      tool_slug: 'free',
      tool_name: 'Free Tool',
      filename: 'reports/free.csv',
      content_type: 'text/csv',
      created_at: '2026-05-31T12:30:00Z'
    }
  ]

  const currentHierarchy = buildWorkflowArtifactHierarchy({
    groups,
    artifacts,
    accept: '.sdf,.csv',
    scope: 'global'
  })

  assert.equal(Array.isArray(currentHierarchy.groups), true)
  assert.equal(currentHierarchy.groups[0]?.groupId, 'group-alpha')
  assert.equal(currentHierarchy.groups[0]?.tools[0]?.toolSlug, 'shared')
  assert.equal(currentHierarchy.groups[0]?.tools[0]?.tasks[0]?.taskId, 'task-shared')
  assert.equal(currentHierarchy.groups[0]?.tools[0]?.tasks[0]?.taskName, '共享口袋筛选批次')
  assert.deepEqual(
    currentHierarchy.groups[0]?.tools[0]?.tasks[0]?.artifacts.map((item: { id: string }) => item.id),
    ['artifact-1', 'artifact-2']
  )
  assert.equal(
    currentHierarchy.groups.some((group: { groupId: string }) => group.groupId === 'ungrouped'),
    true
  )
})

test('参数里的产物复用选择器应提供分组→工具→任务→产物四级链路', () => {
  const source = readSource('src/components/tools/ArtifactFilePicker.vue')
  const pathSource = readSource('src/components/tools/ArtifactPickerPath.vue')
  const stepPanelSource = readSource('src/components/tools/ArtifactPickerStepPanel.vue')
  const optionSource = readSource('src/components/tools/ArtifactPickerStepOption.vue')
  const summarySource = readSource('src/components/tools/ArtifactPickerSelectionSummary.vue')
  const modelSource = readSource('src/types/models.d.ts')

  assert.equal(source.includes('selectedGroupId'), true)
  assert.equal(source.includes('selectedToolSlug'), true)
  assert.equal(source.includes('selectedTaskId'), true)
  assert.equal(source.includes('activeStep'), true)
  assert.equal(source.includes('externalSelectionPath'), true)
  assert.equal(source.includes('ArtifactPickerPath'), true)
  assert.equal(pathSource.includes('artifact-path'), true)
  assert.equal(stepPanelSource.includes('artifact-step-panel'), true)
  assert.equal(optionSource.includes('artifact-step-option'), true)
  assert.equal(summarySource.includes('artifact-selection-summary'), true)
  assert.equal(source.includes('buildWorkflowArtifactHierarchy'), true)
  assert.equal(modelSource.includes('task_name?: string'), true)
})

test('节点参数表单应通过共享选择器提供分组→工具→任务→产物链路', () => {
  const source = readSource('src/components/tools/ArtifactFilePicker.vue')
  const pathSource = readSource('src/components/tools/ArtifactPickerPath.vue')
  const formSource = readSource('src/components/tools/ToolParameterForm.vue')

  assert.equal(source.includes('buildWorkflowArtifactHierarchy'), true)
  assert.equal(source.includes('selectedGroupId'), true)
  assert.equal(source.includes('selectedToolSlug'), true)
  assert.equal(source.includes('selectedTaskId'), true)
  assert.equal(pathSource.includes('artifact-path'), true)
  assert.equal(formSource.includes('ArtifactFilePicker'), true)
})
