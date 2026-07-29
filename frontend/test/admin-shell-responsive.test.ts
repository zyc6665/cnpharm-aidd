import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('后台容器应在窄屏下收紧间距并保持标签可横向浏览', () => {
  const source = readSource('src/views/admin/index.vue')

  assert.equal(source.includes('@media (max-width: @screen-md)'), true)
  assert.equal(source.includes('.admin-page'), true)
  assert.equal(source.includes('.admin-tabs'), true)
  assert.equal(source.includes('overflow-x: auto;'), true)
  assert.equal(source.includes('padding: @spacing-md;'), true)
})

test('后台导航标签应避免换行挤压', () => {
  const source = readSource('src/views/admin/index.vue')

  assert.equal(source.includes('class="admin-tab"'), true)
  assert.equal(source.includes('white-space: nowrap;'), true)
  assert.equal(source.includes('font-size: @font-size-xs;'), true)
})
