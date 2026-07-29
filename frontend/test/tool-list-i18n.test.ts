import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工具列表分页总数应复用通用国际化文案', () => {
  const source = readSource('src/views/tools/List.vue')

  assert.equal(source.includes(":show-total=\"(total: number) => t('common.totalItems', { total })\""), true)
  assert.equal(source.includes('共 ${'), false)
})
