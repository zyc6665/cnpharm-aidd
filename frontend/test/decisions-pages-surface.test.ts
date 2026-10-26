import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

const PAGE_FILE = 'src/views/projects/Decisions.vue'

/** 递归收集 i18n 对象的叶子 key，用来断言两份语言包对称。 */
function collectLeafKeys(value: unknown, prefix = ''): string[] {
  if (value === null || typeof value !== 'object') {
    return [prefix]
  }
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    collectLeafKeys(child, prefix ? `${prefix}.${key}` : key)
  )
}

test('决策记录页视图文件存在且使用 script setup lang="ts"', () => {
  assert.ok(existsSync(resolve(rootDir, PAGE_FILE)), `missing view: ${PAGE_FILE}`)

  const source = readSource(PAGE_FILE)
  assert.ok(source.includes('<script setup lang="ts">'), `${PAGE_FILE} 缺少 script setup lang="ts"`)
  assert.ok(source.includes('data-testid'), `${PAGE_FILE} 缺少 data-testid`)
})

test('router 注册 ProjectDecisions 并挂在 /projects/:projectId/decisions', () => {
  const routerSource = readSource('src/router/index.ts')

  assert.ok(routerSource.includes("name: 'ProjectDecisions'"), 'router 缺少 ProjectDecisions 路由名')
  assert.ok(
    routerSource.includes("path: '/projects/:projectId/decisions'"),
    'router 缺少 /projects/:projectId/decisions 路径'
  )
  assert.ok(
    routerSource.includes("import('@/views/projects/Decisions.vue')"),
    'router 未懒加载 Decisions.vue'
  )

  // 位置：紧跟在 ProjectResults 之后
  const resultsIndex = routerSource.indexOf("name: 'ProjectResults'")
  const decisionsIndex = routerSource.indexOf("name: 'ProjectDecisions'")
  assert.ok(resultsIndex >= 0, 'router 缺少 ProjectResults 路由')
  assert.ok(decisionsIndex > resultsIndex, 'ProjectDecisions 必须注册在 ProjectResults 之后')
})

test('项目导航新增 decisions 项，位置在 results 之后 lineage 之前', () => {
  const navSource = readSource('src/domain/projects/navigation.ts')

  assert.ok(navSource.includes("'decisions'"), "ProjectWorkspaceNavKey 必须含 'decisions'")

  const resultsIndex = navSource.indexOf("key: 'results'")
  const decisionsIndex = navSource.indexOf("key: 'decisions'")
  const lineageIndex = navSource.indexOf("key: 'lineage'")

  assert.ok(resultsIndex >= 0, '导航缺少 results 项')
  assert.ok(decisionsIndex >= 0, '导航缺少 decisions 项')
  assert.ok(lineageIndex >= 0, '导航缺少 lineage 项')
  assert.ok(decisionsIndex > resultsIndex, 'decisions 必须排在 results 之后')
  assert.ok(decisionsIndex < lineageIndex, 'decisions 必须排在 lineage 之前')
})

test('i18n 两份语言包都含 decisions 命名空间且叶子数相等', async () => {
  const zh = (await import('../src/locales/zh-CN/index')).default as Record<string, unknown>
  const en = (await import('../src/locales/en-US/index')).default as Record<string, unknown>

  assert.ok(zh.decisions, 'zh-CN 缺少 decisions 命名空间')
  assert.ok(en.decisions, 'en-US 缺少 decisions 命名空间')

  const zhLeaves = collectLeafKeys(zh.decisions)
  const enLeaves = collectLeafKeys(en.decisions)

  assert.deepEqual(zhLeaves.slice().sort(), enLeaves.slice().sort(), 'zh-CN 与 en-US 的 decisions 叶子不对称')
  assert.ok(zhLeaves.length > 0, 'decisions 命名空间不能为空')
})

test('决策记录页不出现 any 断言', () => {
  const source = readSource(PAGE_FILE)

  assert.equal(/: any\b/.test(source), false, '页面出现 : any')
  assert.equal(/\bas any\b/.test(source), false, '页面出现 as any')
  assert.equal(/<any>/.test(source), false, '页面出现 <any>')
})

test('决策记录页不打印 console.log', () => {
  assert.equal(readSource(PAGE_FILE).includes('console.log'), false, '页面出现 console.log')
})

test('决策记录页调用 listProjectDecisions 与 createProjectDecision', () => {
  const source = readSource(PAGE_FILE)

  assert.ok(source.includes('listProjectDecisions'), '页面未调用 listProjectDecisions')
  assert.ok(source.includes('createProjectDecision'), '页面未调用 createProjectDecision')
})

test('决策记录页用 score_source / missing 判定「未记录」', () => {
  const source = readSource(PAGE_FILE)

  assert.ok(source.includes('score_source'), '页面未判断 score_source')
  assert.ok(source.includes('missing'), "页面未判断 'missing'")
})

test('决策记录页不提供编辑/删除入口（只追加）', () => {
  const source = readSource(PAGE_FILE)

  assert.equal(source.includes('deleteProjectDecision'), false, '决策记录不可删除，页面不应有删除调用')
  assert.equal(source.includes('updateProjectDecision'), false, '决策记录不可修改，页面不应有更新调用')
})
