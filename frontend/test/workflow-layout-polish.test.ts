import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工作台产物条目应分离内容列和操作列，避免查看详情按钮与信息重叠', () => {
  const source = readSource('src/components/workflow/WorkflowArtifactPanel.vue')

  assert.equal(source.includes('artifact-action'), true)
  assert.equal(source.includes('artifact-action-button'), true)
  assert.equal(source.includes('grid-template-columns: minmax(0, 1fr) auto'), true)
  assert.equal(source.includes('overflow-wrap: anywhere'), true)
  assert.equal(source.includes('align-self: start'), true)
})

test('工作台页面应提供更稳的三栏布局和窄屏顺序', () => {
  const pageSource = readSource('src/views/workflow/index.vue')
  const runPanelSource = readSource('src/components/workflow/WorkflowRunPanel.vue')

  assert.equal(pageSource.includes('workflow-shell'), true)
  assert.equal(pageSource.includes('class="workflow-shell"'), true)
  assert.equal(pageSource.includes('container workflow-shell'), false)
  assert.equal(pageSource.includes('max-width: none'), true)
  assert.equal(pageSource.includes('width: min(100%, calc(100vw - 32px))'), true)
  assert.equal(pageSource.includes('grid-template-columns: minmax(260px, 320px) minmax(0, 1fr) minmax(320px, 380px)'), true)
  assert.equal(pageSource.includes('align-items: start'), true)
  assert.equal(pageSource.includes('order:'), true)
  assert.equal(runPanelSource.includes('form-action-buttons'), true)
  assert.equal(runPanelSource.includes(':deep(.ant-space-item)'), true)
})

test('工作台工具选择应改为紧凑下拉区而不是卡片网格', () => {
  const runPanelSource = readSource('src/components/workflow/WorkflowRunPanel.vue')

  assert.equal(runPanelSource.includes('tool-select-panel'), true)
  assert.equal(runPanelSource.includes('tool-select-meta'), true)
  assert.equal(runPanelSource.includes('tool-select'), true)
  assert.equal(runPanelSource.includes('<a-select'), true)
  assert.equal(runPanelSource.includes('tool-option-card'), false)
  assert.equal(runPanelSource.includes('repeat(auto-fit, minmax(280px, 1fr))'), false)
})

test('工具与参数栏应移除重复当前分组并把结果查看做成可展开面板', () => {
  const runPanelSource = readSource('src/components/workflow/WorkflowRunPanel.vue')

  assert.equal(runPanelSource.includes('group-banner'), false)
  assert.equal(runPanelSource.includes('workflow.currentGroup.label'), false)
  assert.equal(runPanelSource.includes('action-summary-card'), false)
  assert.equal(runPanelSource.includes('result-collapse'), true)
  assert.equal(runPanelSource.includes('<a-collapse'), true)
  assert.equal(runPanelSource.includes('resultPanelActiveKeys'), true)
  assert.equal(runPanelSource.includes('WorkflowTaskResultPanel'), true)
})

test('工具说明区域不应重复展示推荐和任务状态标签', () => {
  const runPanelSource = readSource('src/components/workflow/WorkflowRunPanel.vue')

  assert.equal(runPanelSource.includes('tool-select-badges'), false)
  assert.equal(runPanelSource.includes('tool-select-desc'), true)
  assert.equal(runPanelSource.includes('result-collapse-header'), true)
})

test('工作台左右栏应在桌面端跟随顶部导航吸顶', () => {
  const sidebarSource = readSource('src/components/workflow/WorkflowStepSidebar.vue')
  const artifactPanelSource = readSource('src/components/workflow/WorkflowArtifactPanel.vue')
  const stickyColumnPattern = /\.workflow-column\s*\{[\s\S]*?@media \(min-width: @screen-md\)\s*\{[\s\S]*?position: sticky/
  const stickyCardPattern = /\.column-card\s*\{[\s\S]*?position: sticky/
  const artifactVisiblePattern = /\.artifact-lab-panel\s*\{[\s\S]*?overflow: visible/

  assert.equal(stickyColumnPattern.test(sidebarSource), true)
  assert.equal(stickyColumnPattern.test(artifactPanelSource), true)
  assert.equal(stickyCardPattern.test(sidebarSource), false)
  assert.equal(stickyCardPattern.test(artifactPanelSource), false)
  assert.equal(sidebarSource.includes('top: calc(@header-height + @spacing-md)'), true)
  assert.equal(artifactPanelSource.includes('top: calc(@header-height + @spacing-md)'), true)
  assert.equal(sidebarSource.includes('max-height: calc(100vh - @header-height - @spacing-xl)'), true)
  assert.equal(artifactPanelSource.includes('max-height: calc(100vh - @header-height - @spacing-xl)'), true)
  assert.equal(sidebarSource.includes('overflow-y: auto'), true)
  assert.equal(artifactPanelSource.includes('overflow-y: auto'), true)
  assert.equal(artifactVisiblePattern.test(artifactPanelSource), true)
  assert.equal(sidebarSource.includes('&:focus-visible'), true)
})

test('工作台产物应按任务归类并限制每个任务的预览数量', () => {
  const artifactPanelSource = readSource('src/components/workflow/WorkflowArtifactPanel.vue')
  const zhLocaleSource = readSource('src/locales/zh-CN/index.ts')
  const enLocaleSource = readSource('src/locales/en-US/index.ts')

  assert.equal(artifactPanelSource.includes('groupArtifactsByTask'), true)
  assert.equal(artifactPanelSource.includes('currentGroupTaskGroups'), true)
  assert.equal(artifactPanelSource.includes('recentTaskGroups'), true)
  assert.equal(artifactPanelSource.includes('ARTIFACT_TASK_PREVIEW_LIMIT'), true)
  assert.equal(artifactPanelSource.includes('visibleArtifacts'), true)
  assert.equal(artifactPanelSource.includes('artifact-task-card'), true)
  assert.equal(artifactPanelSource.includes('artifact-task-count'), true)
  assert.equal(artifactPanelSource.includes('workflow.artifacts.taskCount'), true)
  assert.equal(artifactPanelSource.includes('workflow.artifacts.moreArtifacts'), true)
  assert.equal(zhLocaleSource.includes('taskCount'), true)
  assert.equal(zhLocaleSource.includes('moreArtifacts'), true)
  assert.equal(enLocaleSource.includes('taskCount'), true)
  assert.equal(enLocaleSource.includes('moreArtifacts'), true)
})

test('工作台任务产物卡片头部应放松任务 ID、来源和时间的布局', () => {
  const artifactPanelSource = readSource('src/components/workflow/WorkflowArtifactPanel.vue')

  assert.equal(artifactPanelSource.includes('artifact-task-kicker'), true)
  assert.equal(artifactPanelSource.includes('artifact-task-id'), true)
  assert.equal(artifactPanelSource.includes('artifact-task-meta-grid'), true)
  assert.equal(artifactPanelSource.includes('artifact-task-meta-item'), true)
  assert.equal(artifactPanelSource.includes('font-family: @font-family-mono'), true)
  assert.equal(artifactPanelSource.includes('gap: @spacing-md'), true)
  assert.equal(artifactPanelSource.includes('padding: @spacing-lg'), true)
})
