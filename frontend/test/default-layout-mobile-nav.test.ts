import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('默认布局应提供移动端抽屉导航并复用同一份导航配置', () => {
  const source = readSource('src/components/layout/DefaultLayout.vue')

  assert.equal(source.includes('const navItems'), true)
  assert.equal(source.includes('visibleNavItems'), true)
  assert.equal(source.includes('mobile-menu-btn'), true)
  assert.equal(source.includes('<a-drawer'), true)
  assert.equal(source.includes('mobile-drawer-menu'), true)
  assert.equal(source.includes('MenuOutlined'), true)
})

test('移动端抽屉导航应在路由跳转和用户菜单跳转后自动收起', () => {
  const source = readSource('src/components/layout/DefaultLayout.vue')

  assert.equal(source.includes('mobileDrawerOpen.value = false'), true)
  assert.equal(source.includes('@close="mobileDrawerOpen = false"'), true)
  assert.equal(source.includes('@click="handleMobileNavClick"'), true)
})
