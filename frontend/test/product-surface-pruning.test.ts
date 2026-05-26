import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
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
