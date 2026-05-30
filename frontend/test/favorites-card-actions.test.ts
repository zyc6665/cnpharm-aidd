import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('收藏页工具卡片操作应使用可聚焦按钮', () => {
  const source = readSource('src/views/user/Favorites.vue')

  assert.equal(source.includes('EyeOutlined'), true)
  assert.equal(source.includes('favorite-card-action'), true)
  assert.equal(source.includes(':aria-label="t(\'tools.viewDetail\')"'), true)
  assert.equal(source.includes(':aria-label="t(\'tools.run\')"'), true)
  assert.equal(source.includes(':aria-label="t(\'tools.unfavorite\')"'), true)
  assert.equal(source.includes('<PlayCircleOutlined @click.stop'), false)
})
