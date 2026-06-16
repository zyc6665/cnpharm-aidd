import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('后台工具编辑页应提供版本化 Markdown 介绍字段', () => {
  const source = readSource('src/views/tools/Create.vue')

  assert.equal(source.includes('documentation_markdown: string'), true)
  assert.equal(source.includes("documentation_markdown: ''"), true)
  assert.equal(source.includes('config.documentation_markdown'), true)
  assert.equal(source.includes("typeof config.documentation_markdown === 'string'"), true)
  assert.equal(source.includes("t('tools.documentationMarkdown')"), true)
  assert.equal(source.includes("t('tools.documentationMarkdownHint')"), true)
  assert.equal(source.includes('tool-documentation-editor'), true)
})
