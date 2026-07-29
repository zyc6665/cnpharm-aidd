import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工具详情页应提供 Markdown 工具介绍弹窗', () => {
  const source = readSource('src/views/tools/Detail.vue')

  assert.equal(source.includes('documentationOpen'), true)
  assert.equal(source.includes('renderMarkdownToHtml'), true)
  assert.equal(source.includes('buildFallbackToolDocumentation'), true)
  assert.equal(source.includes("t('tools.viewIntroduction')"), true)
  assert.equal(source.includes('tool-documentation-modal'), true)
  assert.equal(source.includes('v-html="documentationHtml"'), true)
  assert.equal(source.includes('documentation_markdown'), true)
  assert.equal(source.includes('output_schema'), true)
  assert.equal(source.includes('output_globs'), true)
})
