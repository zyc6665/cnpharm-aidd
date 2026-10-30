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
  for (const path of DESIGN_ROUTES) {
    assert.equal(appShell.includes(`to: '${path}'`), true, `侧边栏缺少入口: ${path}`)
  }
})

test('5 个直达页必须在命令面板可达', () => {
  const palette = readSource('src/components/common/CommandPalette.vue')
  for (const path of DESIGN_ROUTES) {
    assert.equal(palette.includes(`router.push('${path}')`), true, `命令面板缺少入口: ${path}`)
  }
})

test('直达页导航在移动端底部 Tab 中隐藏，避免底部项过多', () => {
  const appShell = readSource('src/components/layout/AppShell.vue')
  assert.equal(appShell.includes('sidebar-design-nav'), true)
  assert.equal(appShell.includes('.sidebar-design-nav'), true)
})
