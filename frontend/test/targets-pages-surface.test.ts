import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

/** 从 locale 源码里切出某个顶层命名空间，收集其直接子键（4 空格缩进的 `key:`）。 */
function collectTopLevelKeys(source: string, namespace: string): string[] {
  const lines = source.split(/\r?\n/)
  const startIndex = lines.findIndex((line) => line === `  ${namespace}: {`)
  if (startIndex === -1) {
    return []
  }

  const keys: string[] = []
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const line = lines[index] ?? ''
    if (line === '  },') {
      break
    }
    const match = /^ {4}([A-Za-z0-9_]+):/.exec(line)
    if (match?.[1]) {
      keys.push(match[1])
    }
  }
  return keys
}

test('六个靶点页面视图文件全部存在', () => {
  const views = [
    'src/views/targets/List.vue',
    'src/views/targets/Detail.vue',
    'src/views/targets/Predict.vue',
    'src/views/targets/StructureDetail.vue',
    'src/views/targets/Pockets.vue',
    'src/views/targets/PocketResidues.vue',
  ]

  for (const view of views) {
    assert.equal(existsSync(resolve(rootDir, view)), true, `${view} 必须存在`)
  }
})

test('路由包含 6 条靶点路由且全部懒加载', () => {
  const source = readSource('src/router/index.ts')
  const routeNames = [
    'ProjectTargets',
    'TargetDetail',
    'StructurePredict',
    'StructureDetail',
    'StructurePockets',
    'PocketResidues',
  ]

  for (const name of routeNames) {
    assert.equal(
      source.includes(`name: '${name}'`),
      true,
      `router 必须声明 name: '${name}'`,
    )
  }

  for (const chunk of [
    '@/views/targets/List.vue',
    '@/views/targets/Detail.vue',
    '@/views/targets/Predict.vue',
    '@/views/targets/StructureDetail.vue',
    '@/views/targets/Pockets.vue',
    '@/views/targets/PocketResidues.vue',
  ]) {
    assert.equal(source.includes(`import('${chunk}')`), true, `${chunk} 必须懒加载`)
  }
})

test('项目导航含 targets 项且位于 overview 之后', () => {
  const source = readSource('src/domain/projects/navigation.ts')

  assert.equal(source.includes("'targets'"), true, 'ProjectWorkspaceNavKey 必须含 targets')

  const overviewIndex = source.indexOf("key: 'overview'")
  const targetsIndex = source.indexOf("key: 'targets'")
  assert.notEqual(overviewIndex, -1, 'overview 项必须存在')
  assert.notEqual(targetsIndex, -1, 'targets 项必须存在')
  assert.equal(overviewIndex < targetsIndex, true, 'targets 必须排在 overview 之后')

  const workflowIndex = source.indexOf("key: 'workflow'")
  assert.equal(targetsIndex < workflowIndex, true, 'targets 必须紧跟在 overview 之后（第 2 项）')
})

test('i18n 中英两份都补齐 targets 命名空间', () => {
  for (const locale of ['zh-CN', 'en-US']) {
    const source = readSource(`src/locales/${locale}/index.ts`)
    assert.equal(/^ {2}targets: \{$/m.test(source), true, `${locale} 必须有顶层 targets 命名空间`)
  }

  const zhKeys = collectTopLevelKeys(readSource('src/locales/zh-CN/index.ts'), 'targets')
  const enKeys = collectTopLevelKeys(readSource('src/locales/en-US/index.ts'), 'targets')
  assert.deepEqual(enKeys, zhKeys, 'targets 命名空间的键在 zh-CN 与 en-US 必须一一对应')
  assert.equal(zhKeys.length > 0, true, 'targets 命名空间不能为空')
})

test('List.vue 含空态键与新建靶点入口', () => {
  const source = readSource('src/views/targets/List.vue')

  assert.equal(source.includes('targets.list.empty'), true, '空态文案必须走 i18n 键')
  assert.equal(source.includes('createTarget'), true, '必须调用 createTarget')
  assert.equal(source.includes('SkeletonList'), true, '列表加载骨架必须复用 SkeletonList')
  assert.equal(source.includes('AppErrorState'), true, '错态必须复用 AppErrorState')
  assert.equal(source.includes('data-testid'), true, '关键元素必须带 data-testid')
})

test('Pockets.vue 行内选定调用 selectPocket 且按 score 排序', () => {
  const source = readSource('src/views/targets/Pockets.vue')
  // 口径：Pockets 页与「上游接力条」共用 useStructurePockets，选定与排序在该 composable 内。
  const composable = readSource('src/composables/useStructurePockets.ts')

  assert.equal(source.includes('useStructurePockets'), true, 'Pockets.vue 必须复用 useStructurePockets')
  assert.equal(composable.includes('selectPocket'), true, 'useStructurePockets 必须调用 selectPocket')
  assert.equal(composable.includes('sortPocketsByScore'), true, '排序必须来自 @/domain/targets')
  assert.equal(source.includes('PocketResidues'), true, '点击行必须跳转 PocketResidues')
})

test('PocketResidues.vue 用 tag 高亮 is_key 残基', () => {
  const source = readSource('src/views/targets/PocketResidues.vue')

  assert.equal(source.includes('is_key'), true, '残基表必须展示 is_key')
  assert.equal(source.includes('<a-tag'), true, 'is_key 必须用 tag 高亮')
})

test('StructureDetail.vue 复用 StructureArtifactPreview 且不直接引入 molstar', () => {
  const source = readSource('src/views/targets/StructureDetail.vue')

  assert.equal(source.includes('StructureArtifactPreview'), true, '必须复用 StructureArtifactPreview')
  assert.equal(/import[^\n]*molstar/.test(source), false, '不得直接 import molstar')
  assert.equal(source.includes('predictPockets'), true, '必须有预测口袋入口')
})
