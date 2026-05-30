import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('错误页面应复用统一错误状态组件', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/common/AppErrorState.vue')), true)

  for (const relativePath of ['src/views/error/403.vue', 'src/views/error/404.vue']) {
    const source = readSource(relativePath)

    assert.equal(source.includes('AppErrorState'), true, relativePath)
    assert.equal(source.includes('class="error-page"'), false, relativePath)
    assert.equal(source.includes('.error-page'), false, relativePath)
  }
})

test('统一错误状态组件应提供错误码、说明和返回首页操作', () => {
  const source = readSource('src/components/common/AppErrorState.vue')

  assert.equal(source.includes('app-error-state'), true)
  assert.equal(source.includes('code'), true)
  assert.equal(source.includes('description'), true)
  assert.equal(source.includes('router-link to="/"'), true)
})
