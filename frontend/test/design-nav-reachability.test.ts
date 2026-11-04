import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

// 这 5 个页面在 docs/18 收口前是「有路由、零入口」的直达孤儿页：
// 用户只能手敲 URL 才能进入。下面的断言把「路由存在」与「至少一处全局入口引用它」
// 绑在一起，防止以后新增页面时再次只注册路由、不接入导航。
const DESIGN_ROUTES: ReadonlyArray<string> = [
  '/design/molecules',
  '/design/peptides',
  '/predict',
  '/screen',
  '/md',
]

test('5 个直达页必须在路由表注册', () => {
  const router = readSource('src/router/index.ts')
  for (const path of DESIGN_ROUTES) {
    assert.equal(router.includes(`path: '${path}'`), true, `路由缺失: ${path}`)
  }
})

test('5 个直达页必须在侧边栏导航可达', () => {
  const appShell = readSource('src/components/layout/AppShell.vue')
  const designNav = readSource('src/domain/design/navigation.ts')
  // 设计流程导航数据集中在 domain/design/navigation.ts，侧栏消费它渲染。
  assert.equal(appShell.includes('buildDesignNavGroups'), true, '侧边栏必须消费设计流程导航分组')
  for (const path of DESIGN_ROUTES) {
    assert.equal(designNav.includes(`to: '${path}'`), true, `侧边栏缺少入口: ${path}`)
  }
})

test('5 个直达页必须在命令面板可达', () => {
  const palette = readSource('src/components/common/CommandPalette.vue')
  for (const path of DESIGN_ROUTES) {
    assert.equal(palette.includes(`router.push('${path}')`), true, `命令面板缺少入口: ${path}`)
  }
})

test('直达页导航在移动端抽屉中仍可达，入口不再被隐藏', () => {
  const appShell = readSource('src/components/layout/AppShell.vue')
  // 移动端由「底部 Tab 隐藏设计导航」改为「抽屉复用同一套导航」，入口零丢失
  assert.equal(appShell.includes('sidebar-nav sidebar-design-nav'), true)
  assert.equal(appShell.includes('.mobile-topbar {'), true)
  assert.equal(appShell.includes('.sidebar-footer {\n    display: none;'), false)
})
