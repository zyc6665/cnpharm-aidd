import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('前端口令校验应与后端一致为最少 12 位', () => {
  const rulesHosts = [
    'src/views/admin/Users.vue',
    'src/views/user/Settings.vue'
  ]

  for (const relativePath of rulesHosts) {
    const source = readSource(relativePath)

    assert.equal(source.includes('min: 12'), true, relativePath)
    assert.equal(source.includes('min: 6'), false, relativePath)
  }

  const zh = readSource('src/locales/zh-CN/index.ts')
  const en = readSource('src/locales/en-US/index.ts')

  assert.equal(zh.includes('密码长度至少为 12 个字符'), true)
  assert.equal(en.includes('Password must be at least 12 characters'), true)
})
