import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工具列表卡片应支持键盘访问和可见焦点态', () => {
  const source = readSource('src/views/tools/List.vue')

  assert.equal(source.includes('role="button"'), true)
  assert.equal(source.includes('tabindex="0"'), true)
  assert.equal(source.includes(':aria-label="tool.name"'), true)
  assert.equal(source.includes('@keydown.enter="goToDetail(tool.id)"'), true)
  assert.equal(source.includes('@keydown.space.prevent="goToDetail(tool.id)"'), true)
  assert.equal(source.includes('&:focus-visible'), true)
})
