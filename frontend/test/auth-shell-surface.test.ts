import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('认证页应复用统一 AuthShell 页面外壳', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/auth/AuthShell.vue')), true)

  for (const relativePath of [
    'src/views/auth/Login.vue',
    'src/views/auth/Register.vue',
    'src/views/auth/ForgotPassword.vue'
  ]) {
    const source = readSource(relativePath)

    assert.equal(source.includes('AuthShell'), true, relativePath)
    assert.equal(source.includes('class="auth-page"'), false, relativePath)
    assert.equal(source.includes('class="auth-container"'), false, relativePath)
    assert.equal(source.includes('class="auth-card"'), false, relativePath)
    assert.equal(source.includes('class="auth-title"'), false, relativePath)
  }
})

test('AuthShell 应提供品牌视觉区和表单卡片区', () => {
  const source = readSource('src/components/auth/AuthShell.vue')

  assert.equal(source.includes('auth-shell'), true)
  assert.equal(source.includes('auth-shell__brand'), true)
  assert.equal(source.includes('auth-shell__card'), true)
  assert.equal(source.includes('<slot />'), true)
})
