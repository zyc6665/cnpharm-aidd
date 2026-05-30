import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('后台容器应提供窄屏下的头部和内容区适配', () => {
  const source = readSource('src/views/admin/index.vue')

  assert.equal(source.includes('@media (max-width: @screen-md)'), true)
  assert.equal(source.includes('.admin-header'), true)
  assert.equal(source.includes('.admin-content'), true)
  assert.equal(source.includes(':deep(.ant-breadcrumb)'), true)
  assert.equal(source.includes('.user-name'), true)
})

test('后台用户下拉昵称应使用独立类名避免窄屏挤压', () => {
  const source = readSource('src/views/admin/index.vue')

  assert.equal(source.includes('class="user-name"'), true)
  assert.equal(source.includes('max-width:'), true)
  assert.equal(source.includes('text-overflow: ellipsis'), true)
})
