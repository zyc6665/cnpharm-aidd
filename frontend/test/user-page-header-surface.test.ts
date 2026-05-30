import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('用户中心子页面应复用统一页面标题组件', () => {
  const userPages = [
    'src/views/user/Profile.vue',
    'src/views/user/Settings.vue',
    'src/views/user/Favorites.vue'
  ]

  for (const relativePath of userPages) {
    const source = readSource(relativePath)

    assert.equal(source.includes('AppPageHeader'), true, relativePath)
    assert.equal(source.includes(':title="t(\'user.'), true, relativePath)
  }
})

test('收藏页搜索应放在页面标题操作区而不是卡片标题 extra 中', () => {
  const source = readSource('src/views/user/Favorites.vue')

  assert.equal(source.includes('<template #actions>'), true)
  assert.equal(source.includes('<template #extra>'), false)
})
