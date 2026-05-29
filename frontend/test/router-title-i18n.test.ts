import test from 'node:test'
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
