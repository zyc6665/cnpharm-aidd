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

test('请求层应通过认证存储模块暴露兼容的 token 辅助函数', () => {
  const source = readSource('src/api/request.ts')

  assert.equal(source.includes("clearAuthStorage"), true)
  assert.equal(source.includes('setGuestSession'), false)
  assert.equal(source.includes('getGuestSession'), false)
})

test('请求层刷新失败时应拒绝并清空等待队列', () => {
  const source = readSource('src/api/request.ts')

  assert.equal(source.includes('rejectRefreshSubscribers(error)'), true)
  assert.equal(source.includes('refreshSubscribers = []'), true)
  assert.equal(source.includes('isRefreshing = false'), true)
})

test('用户 store 应监听认证失效事件并同步清理登录态', () => {
  const source = readSource('src/stores/user.ts')

  assert.equal(source.includes("AUTH_CLEARED_EVENT"), true)
  assert.equal(source.includes("window.addEventListener(AUTH_CLEARED_EVENT"), true)
  assert.equal(source.includes("window.removeEventListener(AUTH_CLEARED_EVENT"), true)
  assert.equal(source.includes("const refreshToken = ref<string | null>(getRefreshToken())"), true)
  assert.equal(source.includes('guestSession'), false)
  assert.equal(source.includes('const authReady = ref(!getToken())'), true)
  assert.equal(source.includes('const isAuthenticated = isLoggedIn'), true)
  assert.equal(source.includes('bootstrapAuthState'), true)
})

test('应用启动时应先完成认证恢复，再由页面决定是否加载私有数据', () => {
  const source = readSource('src/App.vue')

  assert.equal(source.includes('await userStore.bootstrapAuthState()'), true)
})
