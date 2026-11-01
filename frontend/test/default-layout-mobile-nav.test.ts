import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('应用壳层应在移动端将侧栏切换为抽屉（顶部汉堡触发）', () => {
  const source = readSource('src/components/layout/AppShell.vue')

  assert.equal(source.includes('const mainNav'), true)
  assert.equal(source.includes('v-for="item in mainNav"'), true)
  assert.equal(source.includes('@media (max-width: @screen-md)'), true)
  assert.equal(source.includes('.mobile-topbar {'), true)
  assert.equal(source.includes('.mobile-nav-open .shell-sidebar'), true)
  assert.equal(source.includes('transform: translateX(-100%);'), true)
})

test('移动端抽屉应保留当前路由高亮与内容区避让', () => {
  const source = readSource('src/components/layout/AppShell.vue')

  assert.equal(source.includes(':class="{ active: isActive(item.active) }"'), true)
  assert.equal(source.includes('.shell-content {'), true)
  assert.equal(source.includes('margin-left: 0 !important;'), true)
})
