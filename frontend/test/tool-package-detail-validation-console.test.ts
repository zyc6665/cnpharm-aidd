import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('Tool Package 管理页应提供详情与校验台', () => {
  const source = readSource('src/views/admin/ToolPackages.vue')

  assert.equal(source.includes('getToolPackage'), true)
  assert.equal(source.includes("from '@/domain/tool-packages'"), true)
  assert.equal(source.includes('detailDrawerOpen'), true)
  assert.equal(source.includes('openDetail'), true)
  assert.equal(source.includes('formattedSelectedManifest'), true)
  assert.equal(source.includes('publishReadinessMessage'), true)
  assert.equal(source.includes('validation_errors'), true)
  assert.equal(source.includes('manifest-viewer'), true)
  assert.equal(source.includes('版本详情'), true)
  assert.equal(source.includes('签名与发布状态'), true)
  assert.equal(source.includes('旧工具迁移入口'), true)
})
