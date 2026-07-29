import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工具创建编辑页应复用统一标题并保留返回操作', () => {
  const source = readSource('src/views/tools/Create.vue')

  assert.equal(source.includes('AppPageHeader'), true)
  assert.equal(source.includes('<template #actions>'), true)
  assert.equal(source.includes('@click="goBack"'), true)
  assert.equal(source.includes('class="page-header"'), false)
  assert.equal(source.includes('.page-header'), false)
})

test('工具创建编辑页表单应提供移动端栅格兜底', () => {
  const source = readSource('src/views/tools/Create.vue')

  assert.equal(source.includes('class="tool-form"'), true)
  assert.equal(source.includes(':deep(.tool-form .ant-col-12)'), true)
  assert.equal(source.includes(':deep(.tool-form .ant-col-8)'), true)
  assert.equal(source.includes(':deep(.tool-form .ant-col-16)'), true)
})
