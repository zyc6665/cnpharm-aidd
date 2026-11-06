import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('管理后台应提供模型接入指南入口与独立页面', () => {
  const adminSource = readSource('src/views/admin/index.vue')
  const routerSource = readSource('src/router/index.ts')
  const guidePath = resolve(rootDir, 'src/views/admin/ModelGuide.vue')

  assert.equal(adminSource.includes("key: 'model-guide'"), true)
  assert.equal(adminSource.includes('modelGuide'), true)
  assert.equal(routerSource.includes("path: 'model-guide'"), true)
  assert.equal(routerSource.includes('AdminModelGuide'), true)
  assert.equal(existsSync(guidePath), true)

  const guideSource = readSource('src/views/admin/ModelGuide.vue')
  for (const marker of ['模型接入教程', 'DRP_TASK_FILE', 'DRP_RESULT_FILE', 'Tool Package v2', 'protein_structure@1', 'molecule_table@1']) {
    assert.equal(guideSource.includes(marker), true, `missing guide marker ${marker}`)
  }
})

test('模型管理页应突出交付包主路径并避免横向滚动', () => {
  const toolsSource = readSource('src/views/admin/Tools.vue')

  for (const marker of ['modelAdminHint', 'admin.modelGuide', 'modelRuntime', 'shortDigest', 'handleMenuClick']) {
    assert.equal(toolsSource.includes(marker), true, `missing model management marker ${marker}`)
  }
  assert.equal(toolsSource.includes(":scroll=\"{ x: 'max-content' }\""), false)
})

test('管理页内容区应加宽且不产生内部横向滚动', () => {
  const adminSource = readSource('src/views/admin/index.vue')

  assert.equal(adminSource.includes('max-width: none'), true)
  assert.equal(adminSource.includes('padding-inline: @spacing-sm'), true)
  assert.equal(adminSource.includes('overflow-x: hidden'), true)
})

test('算力队列应使用等宽厂商分布卡片', () => {
  const computeSource = readSource('src/views/admin/Compute.vue')

  for (const marker of ['compute-vendor-grid', 'compute-vendor-item', 'vendorEntries']) {
    assert.equal(computeSource.includes(marker), true, `missing vendor card marker ${marker}`)
  }
})

test('模型登记弹窗应使用逐项向导并保留 JSON 快捷模式', () => {
  const source = readSource('src/views/admin/ToolPackages.vue')

  for (const marker of [
    'registrationSteps',
    'guidedStep',
    'registration-step-body',
    'registration-summary-grid',
    'nextGuidedStep',
    'previousGuidedStep',
    'registration-footer-progress'
  ]) {
    assert.equal(source.includes(marker), true, `missing registration wizard marker ${marker}`)
  }
  assert.equal(source.includes('逐项向导'), true)
  assert.equal(source.includes('粘贴 JSON'), true)
  assert.equal(source.includes('width="880px"'), true)
})
