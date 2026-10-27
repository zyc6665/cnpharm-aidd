import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('应用 HTML 外壳应使用平台品牌资源而不是 Vite 默认资源', () => {
  const html = readSource('index.html')

  assert.equal(html.includes('/vite.svg'), false)
  assert.equal(html.includes('/src/assets/logo.svg'), true)
  assert.equal(html.includes('<html lang="zh">'), true)
  // 标题必须是交付方的产品名，而不是上游产品线名（docs/06 §4 的全局框架稿）
  assert.equal(html.includes('<title>中国医药 AI 药物研发平台</title>'), true)
})

test('前端源码中不应保留未使用的 Vite 模板文件', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/components/HelloWorld.vue')), false)
  assert.equal(existsSync(resolve(rootDir, 'src/assets/vue.svg')), false)
  assert.equal(existsSync(resolve(rootDir, 'src/style.css')), false)
  assert.equal(existsSync(resolve(rootDir, 'public/vite.svg')), false)
})

test('品牌名应集中在 config/brand.ts，界面各处不得再硬编码上游产品名', () => {
  const brandSource = readSource('src/config/brand.ts')

  assert.equal(brandSource.includes("export const PLATFORM_NAME = '中国医药 AI 药物研发平台'"), true)
  assert.equal(brandSource.includes('export function buildDocumentTitle'), true)

  // 这些是这个缺陷当初所在的全部位置。逐个断言它们改成引用集中常量，
  // 否则「改一处漏一处」会随下一次改版复发。
  const consumers: ReadonlyArray<readonly [string, string]> = [
    ['src/components/layout/AppShell.vue', 'PLATFORM_SHORT_NAME'],
    ['src/components/auth/AuthShell.vue', 'PLATFORM_NAME'],
    ['src/components/common/AppErrorState.vue', 'PLATFORM_SHORT_NAME'],
    ['src/views/home/index.vue', 'buildCopyright'],
    ['src/router/index.ts', 'buildDocumentTitle'],
  ]

  for (const [path, symbol] of consumers) {
    const source = readSource(path)
    assert.equal(source.includes(symbol), true, `${path} 应引用 ${symbol}`)
    assert.equal(source.includes('CPUModel'), false, `${path} 不应再出现上游产品名`)
  }
})
