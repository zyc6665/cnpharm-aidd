import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('请求层清理 token 时应广播认证状态失效事件', () => {
  const source = readSource('src/api/request.ts')

  assert.equal(source.includes("export const AUTH_CLEARED_EVENT = 'cpumodel-auth-cleared'"), true)
  assert.equal(source.includes("window.dispatchEvent(new CustomEvent(AUTH_CLEARED_EVENT))"), true)
})

test('用户 store 应监听认证失效事件并同步清理登录态', () => {
  const source = readSource('src/stores/user.ts')

  assert.equal(source.includes("AUTH_CLEARED_EVENT"), true)
  assert.equal(source.includes("window.addEventListener(AUTH_CLEARED_EVENT"), true)
  assert.equal(source.includes("window.removeEventListener(AUTH_CLEARED_EVENT"), true)
  assert.equal(source.includes("const refreshToken = ref<string | null>(getRefreshToken())"), true)
  assert.equal(source.includes('const authReady = ref(!getToken())'), true)
  assert.equal(source.includes('bootstrapAuthState'), true)
})

test('应用启动时应先完成认证恢复，再由页面决定是否加载私有数据', () => {
  const source = readSource('src/App.vue')

  assert.equal(source.includes('await userStore.bootstrapAuthState()'), true)
})
