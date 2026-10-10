import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('路由标题应在写入 document.title 前经过 i18n 翻译', () => {
  const routerSource = readSource('src/router/index.ts')

  assert.equal(routerSource.includes("import i18n from '@/locales'"), true)
  assert.equal(routerSource.includes("document.title = `${to.meta.title || 'CPUModel'} - CPUModel`"), false)
  assert.equal(routerSource.includes('i18n.global.t(titleKey)'), true)
})

test('项目工作流路由标题和侧栏按钮应使用当前标题与多语言键', () => {
  const routerSource = readSource('src/router/index.ts')
  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')
  const shellSource = readSource('src/components/layout/AppShell.vue')

  assert.equal(routerSource.includes("meta: { titleLiteral: '项目工作流', requiresAuth: true }"), true)
  for (const source of [zhSource, enSource]) {
    assert.equal(source.includes('expand:'), true)
    assert.equal(source.includes('collapse:'), true)
  }
  assert.equal(shellSource.includes("t('common.collapse')"), true)
})
