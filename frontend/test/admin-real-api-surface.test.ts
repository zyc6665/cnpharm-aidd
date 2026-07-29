import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('管理员仪表板应移除趋势图和系统状态，并接入真实概览接口', () => {
  const source = readSource('src/views/admin/Dashboard.vue')

  assert.equal(source.includes("t('admin.taskTrend')"), false)
  assert.equal(source.includes("t('admin.systemStatus')"), false)
  assert.equal(source.includes('const systemStatus = reactive'), false)
  assert.equal(source.includes('echarts'), false)

  assert.equal(source.includes('adminGetUserStats'), true)
  assert.equal(source.includes('adminGetUsers'), true)
  assert.equal(source.includes('getTaskList'), true)
  assert.equal(source.includes('getSystemStats'), true)
})

test('管理员用户页应只保留真实后端支持的管理能力', () => {
  const source = readSource('src/views/admin/Users.vue')
  const apiSource = readSource('src/api/users.ts')
  const modelSource = readSource('src/types/models.d.ts')

  assert.equal(source.includes("t('admin.createUser')"), true)
  assert.equal(source.includes("t('admin.resetPassword')"), true)
  assert.equal(source.includes("t('admin.hardDeleteUser')"), true)
  assert.equal(source.includes('handleCreateUser'), true)
  assert.equal(source.includes('handleResetPassword'), true)
  assert.equal(source.includes('handleHardDelete'), true)
  assert.equal(source.includes('const users = ref(['), false)

  assert.equal(source.includes('adminGetUsers'), true)
  assert.equal(source.includes('adminCreateUser'), true)
  assert.equal(source.includes('adminResetUserPassword'), true)
  assert.equal(source.includes('adminGetUserStats'), true)
  assert.equal(source.includes('adminUpdateUser'), true)
  assert.equal(source.includes('adminDeleteUser'), true)
  assert.equal(source.includes('Promise.allSettled'), true)
  assert.equal(source.includes('value="disabled"'), true)
  assert.equal(source.includes('value="pending"'), true)
  assert.equal(source.includes('value="inactive"'), false)
  assert.equal(source.includes('value="banned"'), false)
  assert.equal(apiSource.includes('adminCreateUser'), true)
  assert.equal(apiSource.includes('adminResetUserPassword'), true)
  assert.equal(apiSource.includes('hard?: boolean'), true)
  assert.equal(modelSource.includes("status: 'active' | 'disabled' | 'pending'"), true)
  assert.equal(modelSource.includes("status: 'active' | 'inactive' | 'banned'"), false)
})

test('管理员任务页应移除批量假操作并接入真实任务接口', () => {
  const source = readSource('src/views/admin/Tasks.vue')

  assert.equal(source.includes('handleBatchCancel'), false)
  assert.equal(source.includes('handleBatchDelete'), false)
  assert.equal(source.includes('<a-select-option :value="1">LVPocket</a-select-option>'), false)
  assert.equal(source.includes('const tasks = ref(['), false)

  assert.equal(source.includes('getTaskList'), true)
  assert.equal(source.includes('getTaskDetail'), true)
  assert.equal(source.includes('cancelTask'), true)
  assert.equal(source.includes('retryTask'), true)
  assert.equal(source.includes('deleteTask'), true)
  assert.equal(source.includes('useRemoteToolOptions'), true)
  assert.equal(source.includes(':filter-option="false"'), true)
  assert.equal(source.includes('@search="searchToolOptions"'), true)
  assert.equal(source.includes('getToolList({ page: 1, page_size: 100 })'), false)
})

test('管理员系统页应改为只读真实信息页', () => {
  const source = readSource('src/views/admin/System.vue')

  assert.equal(source.includes('handleSaveGeneral'), false)
  assert.equal(source.includes('handleSaveTasks'), false)
  assert.equal(source.includes('handleSaveStorage'), false)
  assert.equal(source.includes('handleTestStorage'), false)
  assert.equal(source.includes('handleSaveEmail'), false)
  assert.equal(source.includes('handleTestEmail'), false)

  assert.equal(source.includes('getSystemInfo'), true)
  assert.equal(source.includes('getSystemStats'), true)
  assert.equal(source.includes('getSystemConfig'), true)
})

test('管理员 API 封装应覆盖用户管理与系统信息场景', () => {
  const usersApiSource = readSource('src/api/users.ts')
  const systemApiSource = readSource('src/api/system.ts')
  const modelSource = readSource('src/types/models.d.ts')

  assert.equal(usersApiSource.includes('adminGetUsers'), true)
  assert.equal(usersApiSource.includes('adminGetUserStats'), true)
  assert.equal(usersApiSource.includes('adminUpdateUser'), true)
  assert.equal(usersApiSource.includes('adminDeleteUser'), true)

  assert.equal(modelSource.includes('export interface SystemInfo'), true)
  assert.equal(modelSource.includes('export interface SystemConfig'), true)
  assert.equal(systemApiSource.includes('Promise<ApiResponse<SystemInfo>>'), true)
  assert.equal(systemApiSource.includes('Promise<ApiResponse<SystemConfig>>'), true)
})

test('管理员工具页应将筛选条件传给真实工具接口', () => {
  const source = readSource('src/views/admin/Tools.vue')

  assert.equal(source.includes('getToolList({ status: filters.status })'), false)
  assert.equal(source.includes('search: filters.keyword'), true)
  assert.equal(source.includes('status: filters.status'), true)
})
