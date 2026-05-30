import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('用户资料和设置表单应提供移动端单列兜底样式', () => {
  const profileSource = readSource('src/views/user/Profile.vue')
  const settingsSource = readSource('src/views/user/Settings.vue')

  assert.equal(profileSource.includes('class="profile-form"'), true)
  assert.equal(settingsSource.includes('class="settings-form"'), true)
  assert.equal(profileSource.includes(':deep(.ant-form-item-label)'), true)
  assert.equal(settingsSource.includes(':deep(.ant-form-item-label)'), true)
  assert.equal(profileSource.includes('max-width: 100%'), true)
  assert.equal(settingsSource.includes('max-width: 100%'), true)
})

test('收藏页搜索框应使用响应式样式类', () => {
  const source = readSource('src/views/user/Favorites.vue')

  assert.equal(source.includes('favorites-search-input'), true)
  assert.equal(source.includes('style="width: 200px"'), false)
})
