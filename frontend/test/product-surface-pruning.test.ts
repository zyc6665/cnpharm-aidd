import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('前端路由中不应再暴露积分中心页面', () => {
  const routerSource = readSource('src/router/index.ts')

  assert.equal(routerSource.includes("path: '/credits'"), false)
  assert.equal(routerSource.includes("name: 'Credits'"), false)
})

test('用户中心与个人资料页不应再跳转积分中心', () => {
  const userCenterSource = readSource('src/views/user/index.vue')
  const profileSource = readSource('src/views/user/Profile.vue')

  assert.equal(userCenterSource.includes('WalletOutlined'), false)
  assert.equal(userCenterSource.includes("router.push('/credits')"), false)

  assert.equal(profileSource.includes('goToCredits'), false)
  assert.equal(profileSource.includes('goToMembership'), false)
  assert.equal(profileSource.includes("router.push('/credits')"), false)
  assert.equal(profileSource.includes("t('user.credits')"), false)
  assert.equal(profileSource.includes("t('user.memberStatus')"), false)
})

test('后台系统页不应再显示积分设置或 GPU 信息', () => {
  const systemSource = readSource('src/views/admin/System.vue')

  assert.equal(systemSource.includes('key="credits"'), false)
  assert.equal(systemSource.includes("t('admin.creditsSettings')"), false)
  assert.equal(systemSource.includes("t('admin.gpuInfo')"), false)
  assert.equal(systemSource.includes('gpuColumns'), false)
  assert.equal(systemSource.includes('gpuInfo = ref'), false)
})

test('后台仪表板不应再显示 GPU 统计', () => {
  const dashboardSource = readSource('src/views/admin/Dashboard.vue')

  assert.equal(dashboardSource.includes("t('admin.stats.gpuUsage')"), false)
  assert.equal(dashboardSource.includes('stats.gpuUsage'), false)
  assert.equal(dashboardSource.includes('systemStatus.gpuMemory'), false)
})

test('工具相关页面不应再暴露 GPU 管理 UI', () => {
  const listSource = readSource('src/views/tools/List.vue')
  const detailSource = readSource('src/views/tools/Detail.vue')
  const createSource = readSource('src/views/tools/Create.vue')
  const adminToolsSource = readSource('src/views/admin/Tools.vue')

  assert.equal(listSource.includes('tool.gpu_required'), false)

  assert.equal(detailSource.includes('class="gpu-info card"'), false)
  assert.equal(detailSource.includes("t('tools.gpuRequirements')"), false)

  assert.equal(createSource.includes("t('tools.gpuRequired')"), false)
  assert.equal(createSource.includes("t('tools.gpuMemoryMb')"), false)

  assert.equal(adminToolsSource.includes("t('admin.gpuRequired')"), false)
})

test('积分中心相关前端模块应已删除', () => {
  const storesIndexSource = readSource('src/stores/index.ts')

  assert.equal(existsSync(resolve(rootDir, 'src/views/credits/index.vue')), false)
  assert.equal(existsSync(resolve(rootDir, 'src/stores/credits.ts')), false)
  assert.equal(existsSync(resolve(rootDir, 'src/api/credits.ts')), false)
  assert.equal(storesIndexSource.includes('useCreditsStore'), false)
})

test('后台与任务页不应再显示积分字段', () => {
  const adminUsersSource = readSource('src/views/admin/Users.vue')
  const adminToolsSource = readSource('src/views/admin/Tools.vue')
  const taskDetailSource = readSource('src/views/tasks/Detail.vue')

  assert.equal(adminUsersSource.includes("column.key === 'credits'"), false)
  assert.equal(adminUsersSource.includes('userForm.credits'), false)

  assert.equal(adminToolsSource.includes("column.key === 'credits'"), false)
  assert.equal(adminToolsSource.includes('toolForm.credits_cost'), false)

  assert.equal(taskDetailSource.includes('task.tool.credits'), false)
})

test('首页与注册页不应再宣传 GPU 或积分奖励', () => {
  const homeSource = readSource('src/views/home/index.vue')
  const registerSource = readSource('src/views/auth/Register.vue')

  assert.equal(homeSource.includes('ThunderboltOutlined'), false)
  assert.equal(homeSource.includes('gpu:'), false)

  assert.equal(registerSource.includes('invitationBonus'), false)
  assert.equal(registerSource.includes("t('auth.invitationBonus')"), false)
})

test('管理员工具管理页应接入完整工具创建与编辑路由', () => {
  const routerSource = readSource('src/router/index.ts')
  const adminToolsSource = readSource('src/views/admin/Tools.vue')
  const createSource = readSource('src/views/tools/Create.vue')

  assert.equal(routerSource.includes("path: 'tools/create'"), true)
  assert.equal(routerSource.includes("name: 'AdminToolCreate'"), true)
  assert.equal(routerSource.includes("path: 'tools/:id/edit'"), true)
  assert.equal(routerSource.includes("name: 'AdminToolEdit'"), true)

  assert.equal(adminToolsSource.includes("router.push('/admin/tools/create')"), true)
  assert.equal(adminToolsSource.includes("router.push(`/admin/tools/${tool.id}/edit`)"), true)
  assert.equal(adminToolsSource.includes('showCreateModal'), false)

  assert.equal(createSource.includes("route.name === 'AdminToolEdit'"), true)
  assert.equal(createSource.includes('createToolVersion'), true)
  assert.equal(createSource.includes("value=\"ssh_job\""), true)
  assert.equal(createSource.includes('ssh_host'), true)
  assert.equal(createSource.includes('ssh_auth_type'), true)
  assert.equal(createSource.includes('ssh_auth_ref'), true)
  assert.equal(createSource.includes('ssh_password_ref'), true)
})

test('管理员工具管理页应提供 platform_tool.json 导入入口', () => {
  const adminToolsSource = readSource('src/views/admin/Tools.vue')
  const toolsApiSource = readSource('src/api/tools.ts')

  assert.equal(adminToolsSource.includes('handleImportConfig'), true)
  assert.equal(adminToolsSource.includes('importConfigText'), true)
  assert.equal(adminToolsSource.includes('importToolConfig'), true)

  assert.equal(toolsApiSource.includes('importToolConfig'), true)
  assert.equal(toolsApiSource.includes('/tools/import-config'), true)
})
