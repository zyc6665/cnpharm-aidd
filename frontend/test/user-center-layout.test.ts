import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('用户中心外壳应在窄屏切换为横向导航', () => {
  const source = readSource('src/views/user/index.vue')

  assert.equal(source.includes(':mode="menuMode"'), true)
  assert.equal(source.includes('window.matchMedia'), true)
  assert.equal(source.includes("'horizontal'"), true)
  assert.equal(source.includes("window.addEventListener('resize', updateMenuMode)"), true)
  assert.equal(source.includes("window.removeEventListener('resize', updateMenuMode)"), true)
})

test('用户中心外壳应提供稳定的侧栏和内容容器样式', () => {
  const source = readSource('src/views/user/index.vue')

  assert.equal(source.includes('user-center-shell'), true)
  assert.equal(source.includes('user-sidebar-card'), true)
  assert.equal(source.includes('user-content-panel'), true)
  assert.equal(source.includes('overflow-x: auto'), true)
  assert.equal(source.includes('white-space: nowrap'), true)
})
