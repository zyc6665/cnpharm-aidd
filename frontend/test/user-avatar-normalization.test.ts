import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { normalizeUserInfo } from '../src/utils/user-normalization.ts'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('用户信息归一化应将 avatar_url 映射为可显示的 avatar 字段', () => {
  const normalized = normalizeUserInfo({
    id: 'u-1',
    email: 'avatar@example.com',
    display_name: 'Avatar User',
    avatar_url: '/api/v1/files/file-1/download',
    role: 'user',
    status: 'active',
    created_at: '2026-05-27T00:00:00Z',
    updated_at: '2026-05-27T00:00:00Z'
  })

  assert.equal(normalized.avatar, '/api/v1/files/file-1/download')
  assert.equal(normalized.avatar_url, '/api/v1/files/file-1/download')
  assert.equal(normalized.username, 'Avatar User')
})

test('用户 store 应通过归一化后的 user 视图读取头像', () => {
  const storeSource = readSource('src/stores/user.ts')

  assert.equal(storeSource.includes("import { normalizeUserInfo } from '@/utils/user-normalization'"), true)
  assert.equal(storeSource.includes('const user = computed(() => normalizeUserInfo(userInfo.value))'), true)
  assert.equal(storeSource.includes("const avatar = computed(() => user.value?.avatar || '')"), true)
})
