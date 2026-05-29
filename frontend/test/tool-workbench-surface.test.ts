import test from 'node:test'
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
})

test('/workflow 页面应读取工作台分组而不是旧的工作流工具集合', () => {
  const source = readSource('src/views/workflow/index.vue')

  assert.equal(source.includes('fetchWorkbenchGroups'), true)
  assert.equal(source.includes('fetchWorkflowTools'), false)
})

test('共享产物文件选择器组件文件应存在', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/tools/ArtifactFilePicker.vue')), true)
})

test('普通工具详情页应引用共享产物文件选择器', () => {
  const source = readSource('src/views/tools/Detail.vue')

  assert.equal(source.includes('ArtifactFilePicker'), true)
})

test('工作台运行区应复用共享产物选择器并移除强流程推进文案', () => {
  const source = readSource('src/components/workflow/WorkflowRunPanel.vue')

  assert.equal(source.includes('ArtifactFilePicker'), true)
  assert.equal(source.includes('workflow.actions.continueNextStep'), false)
  assert.equal(source.includes('workflow.invalidations.notice'), false)
})

test('工作台右栏应展示我的产物而不是旧的流程工作区', () => {
  const source = readSource('src/components/workflow/WorkflowArtifactPanel.vue')

  assert.equal(source.includes('useArtifactsStore'), true)
  assert.equal(source.includes('workflow.columns.artifacts'), true)
  assert.equal(source.includes('workflow.columns.workspace'), false)
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
  assert.equal(adminSource.includes("key=\"workbench-groups\""), true)
})

test('后台工作台分组管理页面文件应存在并包含分组与映射维护区', () => {
  const pagePath = resolve(rootDir, 'src/views/admin/WorkbenchGroups.vue')

  assert.equal(existsSync(pagePath), true)

  const source = readSource('src/views/admin/WorkbenchGroups.vue')
  assert.equal(source.includes('group-form'), true)
  assert.equal(source.includes('mapping-form'), true)
  assert.equal(source.includes('adminDeleteWorkbenchGroup'), true)
  assert.equal(source.includes('message.warning'), true)
})
