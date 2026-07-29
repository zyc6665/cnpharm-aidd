import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('应用 HTML 外壳应使用 CPUModel 品牌资源而不是 Vite 默认资源', () => {
  const html = readSource('index.html')

  assert.equal(html.includes('/vite.svg'), false)
  assert.equal(html.includes('/src/assets/logo.svg'), true)
  assert.equal(html.includes('<html lang="zh">'), true)
  assert.equal(html.includes('<title>CPUModel</title>'), true)
})

test('前端源码中不应保留未使用的 Vite 模板文件', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/HelloWorld.vue')), false)
  assert.equal(existsSync(resolve(rootDir, 'src/assets/vue.svg')), false)
  assert.equal(existsSync(resolve(rootDir, 'src/style.css')), false)
  assert.equal(existsSync(resolve(rootDir, 'public/vite.svg')), false)
})
