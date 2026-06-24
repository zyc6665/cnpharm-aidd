import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('受保护头像组件应通过 blob URL 渲染私有文件下载地址', () => {
  const componentPath = resolve(rootDir, 'src/components/common/ProtectedAvatar.vue')
  assert.equal(existsSync(componentPath), true)

  const source = readSource('src/components/common/ProtectedAvatar.vue')
  assert.equal(source.includes('createProtectedObjectUrl'), true)
  assert.equal(source.includes('isProtectedFileDownloadUrl'), true)
  assert.equal(source.includes('displaySrc'), true)
  assert.equal(source.includes('resource.revoke()'), true)
})

test('用户头像入口不应直接把文件下载地址传给 a-avatar', () => {
  const defaultLayoutSource = readSource('src/components/layout/DefaultLayout.vue')
  const userIndexSource = readSource('src/views/user/index.vue')
  const profileSource = readSource('src/views/user/Profile.vue')

  assert.equal(defaultLayoutSource.includes('ProtectedAvatar'), true)
  assert.equal(userIndexSource.includes('ProtectedAvatar'), true)
  assert.equal(profileSource.includes('ProtectedAvatar'), true)
})
