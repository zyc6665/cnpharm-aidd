import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('管理员系统页应提供模型服务配置界面', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/views/admin/System.vue')), true)

  const systemApi = readSource('src/api/system.ts')
  const types = readSource('src/types/models.d.ts')
  const page = readSource('src/views/admin/System.vue')

  assert.equal(systemApi.includes('getModelServices'), true)
  assert.equal(systemApi.includes('createModelService'), true)
  assert.equal(systemApi.includes('updateModelService'), true)
  assert.equal(systemApi.includes('deleteModelService'), true)
  assert.equal(systemApi.includes('testModelService'), true)
  assert.equal(systemApi.includes('setDefaultModelService'), true)
  assert.equal(types.includes('interface ModelService'), true)
  assert.equal(types.includes('ModelServiceCreateParams'), true)
  assert.equal(page.includes('model-services'), true)
  assert.equal(page.includes('modelServiceForm'), true)
  assert.equal(page.includes('has_api_key'), true)
  assert.equal(page.includes('testModelService'), true)
  assert.equal(page.includes('setDefaultModelService'), true)
  assert.equal(page.includes('api_key_encrypted'), false)
})
