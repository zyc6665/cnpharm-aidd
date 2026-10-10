import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工具详情页应展示当前执行器与工具说明信息', () => {
  const source = readSource('src/views/tools/Detail.vue')
  const presentationSource = readSource('src/composables/useToolDetailPresentation.ts')

  assert.equal(source.includes('useToolDetailPresentation'), true)
  assert.equal(source.includes('executorType'), true)
  assert.equal(source.includes('ToolRunInputForm'), true)
  assert.equal(source.includes('ToolRunFormActions'), true)
  for (const marker of [
    'executorType',
    'detailSubtitle',
    'documentationMarkdown',
    'outputSchema'
  ]) {
    assert.equal(presentationSource.includes(marker), true, `missing tool detail marker ${marker}`)
  }
})
