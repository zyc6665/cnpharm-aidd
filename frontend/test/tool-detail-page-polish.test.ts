import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('工具详情页应使用统一页头承载工具标题和收藏操作', () => {
  const source = readSource('src/views/tools/Detail.vue')

  assert.equal(source.includes('AppPageHeader'), true)
  assert.equal(source.includes(':title="tool.name"'), true)
  assert.equal(source.includes(':subtitle="detailSubtitle"'), true)
  assert.equal(source.includes('tool-detail-actions'), true)
})

test('工具详情页应优化信息卡、表单操作区和侧栏布局', () => {
  const source = readSource('src/views/tools/Detail.vue')

  assert.equal(source.includes('tool-overview'), true)
  assert.equal(source.includes('overview-title'), true)
  assert.equal(source.includes('tool-form-actions'), true)
  assert.equal(source.includes('position: sticky'), true)
  assert.equal(source.includes('@media (max-width: @screen-md)'), true)
})

test('工具详情页应使用独立示例组件提供查看示例入口', () => {
  const detailSource = readSource('src/views/tools/Detail.vue')
  const componentPath = resolve(rootDir, 'src/components/tools/ToolExamplePanel.vue')

  assert.equal(existsSync(componentPath), true)
  assert.equal(detailSource.includes('ToolExamplePanel'), true)
  assert.equal(detailSource.includes('@preview-file="handlePreviewExampleFile"'), true)
  assert.equal(detailSource.includes('@use-example="handleUseExample"'), true)

  const componentSource = readSource('src/components/tools/ToolExamplePanel.vue')
  assert.equal(componentSource.includes('tools.viewExample'), true)
  assert.equal(componentSource.includes('tools.useExample'), true)
  assert.equal(componentSource.includes('example-panel'), true)
})
