import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

test('后台仪表盘应复用统一页头并提供刷新操作', () => {
  const source = readSource('src/views/admin/Dashboard.vue')

  assert.equal(source.includes('<AppPageHeader'), true)
  assert.equal(source.includes("t('admin.dashboardSubtitle')"), true)
  assert.equal(source.includes("t('common.refresh')"), true)
  assert.equal(source.includes('ReloadOutlined'), true)
})

test('后台仪表盘应提供更易扫描的统计和列表布局', () => {
  const source = readSource('src/views/admin/Dashboard.vue')

  assert.equal(source.includes('dashboard-summary'), true)
  assert.equal(source.includes('stat-card--users'), true)
  assert.equal(source.includes('stat-card__accent'), true)
  assert.equal(source.includes('dashboard-panel'), true)
  assert.equal(source.includes(':scroll="{ x: 560 }"'), true)
})

test('后台仪表盘标题文案应完成中英文配置', () => {
  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')

  assert.equal(zhSource.includes('dashboardSubtitle'), true)
  assert.equal(enSource.includes('dashboardSubtitle'), true)
})
