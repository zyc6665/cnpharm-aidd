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

test('5 个直达页必须在研发流程页内可达（侧边栏不再重复挂载设计分组）', () => {
  const appShell = readSource('src/components/layout/AppShell.vue')
  const pipelinePage = readSource('src/views/design/Pipeline.vue')
  const designNav = readSource('src/domain/design/navigation.ts')
  // 设计流程工具入口收敛到项目内「研发流程」（Pipeline.vue），全局侧栏不再重复列出。
  assert.equal(appShell.includes('sidebar-design-nav'), false, '全局侧边栏不应再保留设计流程分组')
  assert.equal(pipelinePage.includes('buildDesignNavGroups'), true, '研发流程页必须消费设计流程分组提供直达入口')
  for (const path of DESIGN_ROUTES) {
    assert.equal(designNav.includes(`withProject('${path}')`), true, `设计流程分组缺少入口: ${path}`)
  }
})

test('5 个直达页必须在命令面板可达', () => {
  const palette = readSource('src/components/common/CommandPalette.vue')
  for (const path of DESIGN_ROUTES) {
    assert.equal(palette.includes(`router.push('${path}')`), true, `命令面板缺少入口: ${path}`)
  }
})

test('移动端抽屉复用主侧边栏，不隐藏底部入口', () => {
  const appShell = readSource('src/components/layout/AppShell.vue')
  assert.equal(appShell.includes('.mobile-topbar {'), true)
  assert.equal(appShell.includes('.sidebar-footer {\n    display: none;'), false)
})
