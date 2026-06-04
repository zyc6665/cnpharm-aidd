import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

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

  const hierarchyModule = await import(pathToFileURL(modulePath).href)

  assert.equal(typeof hierarchyModule.buildWorkflowArtifactHierarchy, 'function')

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

  const currentHierarchy = hierarchyModule.buildWorkflowArtifactHierarchy({
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
  const modelSource = readSource('src/types/models.d.ts')

  assert.equal(source.includes('selectedGroupId'), true)
  assert.equal(source.includes('selectedToolSlug'), true)
  assert.equal(source.includes('selectedTaskId'), true)
  assert.equal(source.includes('activeStep'), true)
  assert.equal(source.includes('externalSelectionPath'), true)
  assert.equal(source.includes('artifact-path'), true)
  assert.equal(source.includes('artifact-step-panel'), true)
  assert.equal(source.includes('artifact-step-option'), true)
  assert.equal(source.includes('artifact-selection-summary'), true)
  assert.equal(source.includes('buildWorkflowArtifactHierarchy'), true)
  assert.equal(modelSource.includes('task_name?: string'), true)
})

test('工作台右侧产物面板应按工具分组→工具→任务→产物统一展示并提供路径回传', () => {
  const source = readSource('src/components/workflow/WorkflowArtifactPanel.vue')
  const runPanelSource = readSource('src/components/workflow/WorkflowRunPanel.vue')
  const workflowPageSource = readSource('src/views/workflow/index.vue')

  assert.equal(source.includes('buildWorkflowArtifactHierarchy'), true)
  assert.equal(source.includes('artifact-tool-section'), true)
  assert.equal(source.includes('artifact-tool-title'), true)
  assert.equal(source.includes('artifact-task-card'), true)
  assert.equal(source.includes('artifact-task-title'), true)
  assert.equal(source.includes('artifact-task-short-id'), true)
  assert.equal(source.includes('taskNode.taskName'), true)
  assert.equal(source.includes('artifact-name'), true)
  assert.equal(source.includes('expandedGroupIds'), true)
  assert.equal(source.includes('expandedToolSlugs'), true)
  assert.equal(source.includes('expandedTaskIds'), true)
  assert.equal(source.includes('select-artifact-path'), true)
  assert.equal(runPanelSource.includes('artifactSelectionPath'), true)
  assert.equal(workflowPageSource.includes('@select-artifact-path'), true)
})
