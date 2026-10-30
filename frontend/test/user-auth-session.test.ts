import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('认证存储清理时应广播认证状态失效事件', () => {
  const source = readSource('src/utils/auth-storage.ts')

  assert.equal(source.includes("export const AUTH_CLEARED_EVENT = 'cpumodel-auth-cleared'"), true)
  assert.equal(source.includes("window.dispatchEvent(new CustomEvent(AUTH_CLEARED_EVENT))"), true)
  assert.equal(source.includes('GUEST_SESSION_KEY'), false)
})

test('认证存储不再暴露 token 读写接口', () => {
  const source = readSource('src/utils/auth-storage.ts')

  assert.equal(source.includes('export const getToken'), false)
  assert.equal(source.includes('export const setToken'), false)
  assert.equal(source.includes('export const getRefreshToken'), false)
  assert.equal(source.includes('export const setRefreshToken'), false)
})

test('请求层应使用 withCredentials 且不再注入 Authorization', () => {
  const source = readSource('src/api/request.ts')

  assert.equal(source.includes('withCredentials: true'), true)
  assert.equal(source.includes('Authorization'), false)
  assert.equal(source.includes('getToken'), false)
  assert.equal(source.includes('buildCsrfHeader'), true)
  assert.equal(source.includes('X-CSRF-Token'), false) // 头名集中在 cookies.ts
})

test('请求层刷新失败时应拒绝并清空等待队列', () => {
  const source = readSource('src/api/request.ts')

  assert.equal(source.includes('rejectRefreshSubscribers(refreshError)'), true)
  assert.equal(source.includes('refreshSubscribers = []'), true)
  assert.equal(source.includes('isRefreshing = false'), true)
  // 刷新接口使用 withCredentials，不再传 refresh_token
  assert.equal(source.includes('/auth/refresh'), true)
  assert.equal(source.includes('refresh_token'), false)
})

test('用户 store 应监听认证失效事件并同步清理登录态', () => {
  const source = readSource('src/stores/user.ts')

  assert.equal(source.includes('AUTH_CLEARED_EVENT'), true)
  assert.equal(source.includes('window.addEventListener(AUTH_CLEARED_EVENT'), true)
  assert.equal(source.includes('window.removeEventListener(AUTH_CLEARED_EVENT'), true)
  assert.equal(source.includes('getRefreshToken'), false)
  assert.equal(source.includes('getToken'), false)
  assert.equal(source.includes('guestSession'), false)
  assert.equal(source.includes('const isAuthenticated = isLoggedIn'), true)
  assert.equal(source.includes('bootstrapAuthState'), true)
  assert.equal(source.includes("persist: {\n    pick: ['userInfo']"), true)
})

test('应用启动时应先完成认证恢复，再由页面决定是否加载私有数据', () => {
  const source = readSource('src/App.vue')

  assert.equal(source.includes('await userStore.bootstrapAuthState()'), true)
})
