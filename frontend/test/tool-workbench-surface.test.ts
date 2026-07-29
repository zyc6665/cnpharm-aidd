import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('/workflow 页面文案应切换为工具工作台', () => {
  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')

  assert.equal(zhSource.includes("title: '工具工作台'"), true)
  assert.equal(enSource.includes("title: 'Tool Workbench'"), true)
})

test('工作台页面仍使用 /workflow 路由并保留独立视图文件', () => {
  const routerSource = readSource('src/router/index.ts')

  assert.equal(routerSource.includes("path: '/workflow'"), true)
  assert.equal(existsSync(resolve(rootDir, 'src/views/workflow/index.vue')), true)
})

test('工作台左栏应转为分组栏语义而不是步骤栏语义', () => {
  const source = readSource('src/components/workflow/WorkflowStepSidebar.vue')

  assert.equal(source.includes('workflow.columns.groups'), true)
  assert.equal(source.includes('workflow.columns.steps'), false)
  assert.equal(source.includes('group-rail-card'), true)
})

test('/workflow 页面应同时加载工作台分组与可用于画布的工具集合', () => {
  const source = readSource('src/views/workflow/index.vue')

  assert.equal(source.includes('fetchWorkbenchGroups'), true)
  assert.equal(source.includes('fetchWorkflowTools'), true)
})

test('工作台页头标题与副标题应居中展示', () => {
  const source = readSource('src/views/workflow/index.vue')

  assert.equal(source.includes('<AppPageHeader'), true)
  assert.equal(source.includes('align="center"'), true)
  assert.equal(source.includes('workflow-deck'), true)
})

test('共享产物文件选择器组件文件应存在', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/tools/ArtifactFilePicker.vue')), true)
})

test('共享产物文件选择器应使用路径式四级选择并过滤兼容文件', () => {
  const source = readSource('src/components/tools/ArtifactFilePicker.vue')

  assert.equal(source.includes('buildWorkflowArtifactHierarchy'), true)
  assert.equal(source.includes('currentToolId'), true)
  assert.equal(source.includes('currentToolSlug'), true)
  assert.equal(source.includes('artifact-path'), true)
  assert.equal(source.includes('artifact-step-panel'), true)
  assert.equal(source.includes('selectedTaskId'), true)
  assert.equal(source.includes('selectedGroupId'), true)
  assert.equal(source.includes('selectedToolSlug'), true)
  assert.equal(source.includes('activeStep'), true)
  assert.equal(source.includes('a-select-opt-group'), false)
  assert.equal(source.includes('tools.noCompatibleArtifacts'), true)
  assert.equal(source.includes('tools.selectArtifactTask'), true)
})

test('普通工具详情页应引用共享产物文件选择器', () => {
  const source = readSource('src/views/tools/Detail.vue')

  assert.equal(source.includes('ArtifactFilePicker'), true)
  assert.equal(source.includes(':current-tool-id="tool?.id"'), true)
  assert.equal(source.includes(':current-tool-slug="tool?.slug"'), true)
})

test('节点运行区应经由参数表单复用共享产物选择器', () => {
  const runPanelSource = readSource('src/components/workflow/WorkflowNodeRunPanel.vue')
  const formSource = readSource('src/components/workflow/ToolParameterForm.vue')

  assert.equal(runPanelSource.includes('ToolParameterForm'), true)
  assert.equal(runPanelSource.includes(':tool-id="selectedTool?.id"'), true)
  assert.equal(runPanelSource.includes(':tool-slug="selectedTool?.slug"'), true)
  assert.equal(formSource.includes('ArtifactFilePicker'), true)
})

test('工作台右栏应展示我的产物而不是旧的流程工作区', () => {
  const source = readSource('src/components/workflow/WorkflowArtifactPanel.vue')

  assert.equal(source.includes('useArtifactsStore'), true)
  assert.equal(source.includes('workflow.columns.artifacts'), true)
  assert.equal(source.includes('workflow.columns.workspace'), false)
  assert.equal(source.includes('artifact-lab-panel'), true)
  assert.equal(source.includes('artifact-task-short-id'), true)
})

test('工具 API 应暴露工作台分组相关方法', () => {
  const source = readSource('src/api/tools.ts')

  assert.equal(source.includes('getWorkbenchGroups'), true)
  assert.equal(source.includes('adminGetWorkbenchGroups'), true)
  assert.equal(source.includes('adminGetWorkbenchGroupMappings'), true)
})

test('文件 API 应暴露我的产物读取方法', () => {
  const source = readSource('src/api/files.ts')

  assert.equal(source.includes('getArtifactFiles'), true)
})

test('应存在独立的产物 store 并从 store 入口导出', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/stores/artifacts.ts')), true)

  const source = readSource('src/stores/index.ts')
  assert.equal(source.includes("export { useArtifactsStore } from './artifacts'"), true)
})

test('管理后台应存在工作台分组管理路由与导航入口', () => {
  const routerSource = readSource('src/router/index.ts')
  const adminSource = readSource('src/views/admin/index.vue')

  assert.equal(routerSource.includes("path: 'workbench-groups'"), true)
  assert.equal(routerSource.includes('AdminWorkbenchGroups'), true)
  assert.equal(adminSource.includes("key: 'workbench-groups'"), true)
})

test('后台工作台分组管理页面文件应存在并包含分组与映射维护区', () => {
  const pagePath = resolve(rootDir, 'src/views/admin/WorkbenchGroups.vue')

  assert.equal(existsSync(pagePath), true)

  const source = readSource('src/views/admin/WorkbenchGroups.vue')
  assert.equal(source.includes('group-form'), true)
  assert.equal(source.includes('mapping-form'), true)
  assert.equal(source.includes('adminDeleteWorkbenchGroup'), true)
  assert.equal(source.includes('message.warning'), true)
  assert.equal(source.includes('useRemoteToolOptions'), true)
  assert.equal(source.includes(':filter-option="false"'), true)
  assert.equal(source.includes('@search="searchToolOptions"'), true)
  assert.equal(source.includes('getToolList({ page: 1, page_size: 100 })'), false)
  assert.equal(source.includes('item.tool_name'), true)
  assert.equal(source.includes('item.group_name'), true)
  assert.equal(source.includes('resolveToolName'), false)
  assert.equal(source.includes('resolveGroupName'), false)
  assert.equal(source.includes('mappingFilters.search'), true)
  assert.equal(source.includes('mappingFilters.group_id'), true)
  assert.equal(source.includes('mappingPaginationConfig'), true)
  assert.equal(source.includes('fetchMappings'), true)

  const apiSource = readSource('src/api/tools.ts')
  assert.equal(apiSource.includes('AdminWorkbenchGroupMappingListParams'), true)
  assert.equal(apiSource.includes('PaginatedResponse<WorkbenchGroupMapping>'), true)
})
