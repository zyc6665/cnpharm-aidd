import { test } from 'vitest'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import zhCN from '../src/locales/zh-CN/index.ts'
import enUS from '../src/locales/en-US/index.ts'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

function readGroupTitle(messages: object, namespace: string): unknown {
  const admin = (messages as { admin?: Record<string, unknown> }).admin
  const group = admin?.[namespace]
  if (typeof group !== 'object' || group === null) {
    return undefined
  }
  return (group as Record<string, unknown>).title
}

test('算力与队列页、审计日志页均已落地', () => {
  assert.equal(existsSync(resolve(rootDir, 'src/views/admin/Compute.vue')), true)
  assert.equal(existsSync(resolve(rootDir, 'src/views/admin/Audit.vue')), true)
})

test('后台路由注册了 AdminCompute 与 AdminAudit，且排在 AdminSystem 之后', () => {
  const routerSource = readSource('src/router/index.ts')

  assert.equal(routerSource.includes("path: 'compute'"), true)
  assert.equal(routerSource.includes("name: 'AdminCompute'"), true)
  assert.equal(routerSource.includes("import('@/views/admin/Compute.vue')"), true)
  assert.equal(routerSource.includes("path: 'audit'"), true)
  assert.equal(routerSource.includes("name: 'AdminAudit'"), true)
  assert.equal(routerSource.includes("import('@/views/admin/Audit.vue')"), true)

  const systemIndex = routerSource.indexOf("name: 'AdminSystem'")
  assert.equal(systemIndex > 0, true)
  assert.equal(routerSource.indexOf("name: 'AdminCompute'") > systemIndex, true)
  assert.equal(routerSource.indexOf("name: 'AdminAudit'") > systemIndex, true)
})

test('后台 tabs 含 compute / audit 两项且位于 system 之前', () => {
  const indexSource = readSource('src/views/admin/index.vue')

  assert.equal(indexSource.includes('DatabaseOutlined'), true)
  assert.equal(indexSource.includes('FileSearchOutlined'), true)

  const computeIndex = indexSource.indexOf("key: 'compute'")
  const auditIndex = indexSource.indexOf("key: 'audit'")
  const systemIndex = indexSource.indexOf("key: 'system'")

  assert.equal(computeIndex > 0, true)
  assert.equal(auditIndex > 0, true)
  assert.equal(systemIndex > 0, true)
  assert.equal(computeIndex < systemIndex, true)
  assert.equal(auditIndex < systemIndex, true)
  assert.equal(indexSource.includes('adminTabs'), true)
  assert.equal(indexSource.includes('labelKey: \'admin.compute.title\''), true)
  assert.equal(indexSource.includes('labelKey: \'admin.audit.title\''), true)
})

test('中英文 i18n 均提供 admin.compute.title 与 admin.audit.title', () => {
  for (const messages of [zhCN, enUS]) {
    assert.equal(typeof readGroupTitle(messages, 'compute'), 'string')
    assert.equal(typeof readGroupTitle(messages, 'audit'), 'string')
  }

  const zhSource = readSource('src/locales/zh-CN/index.ts')
  const enSource = readSource('src/locales/en-US/index.ts')
  assert.equal(zhSource.includes('DRP_NODE_SLOTS_YAML'), true)
  assert.equal(enSource.includes('DRP_NODE_SLOTS_YAML'), true)
})

test('SLOT_STATE_TONES 覆盖五种卡位状态并给出状态色', async () => {
  const computeDomain = await import('../src/domain/admin/compute.ts')
  const tones = computeDomain.SLOT_STATE_TONES

  assert.deepEqual(Object.keys(tones).sort(), ['BORROWED', 'BUSY', 'FAULT', 'FREE', 'RESERVED'])
  assert.equal(tones.FREE, 'success')
  assert.equal(tones.RESERVED, 'warning')
  assert.equal(tones.BUSY, 'processing')
  assert.equal(tones.FAULT, 'error')
  assert.equal(tones.BORROWED, 'default')
})

test('countSlotsByState 对空数组返回五个 0', async () => {
  const computeDomain = await import('../src/domain/admin/compute.ts')
  const counts = computeDomain.countSlotsByState([])

  assert.deepEqual(counts, { FREE: 0, RESERVED: 0, BUSY: 0, FAULT: 0, BORROWED: 0 })
  assert.equal(computeDomain.countSlotsByState(undefined).FREE, 0)
})

test('审计 domain 不硬编码动作列表，动作选项来自 facet', () => {
  const domainSource = readSource('src/domain/admin/audit.ts')

  assert.equal(domainSource.includes('buildAuditActionOptions'), true)
  assert.equal(domainSource.includes('facets?.actions'), true)
  // 不得出现硬编码的动作枚举（动作清单只能来自后端 facets）。
  assert.equal(/(LOGIN|LOGOUT|CREATE|UPDATE|DELETE|READ|EXPORT|DOWNLOAD)/.test(domainSource), false)
})

test('算力页只读，不提供卡位状态上报入口', () => {
  const page = readSource('src/views/admin/Compute.vue')

  assert.equal(page.includes('reportSlotState'), false)
  assert.equal(page.includes('/gpu/slots/report'), false)
  assert.equal(page.includes('getGpuSlotOverview'), true)
  assert.equal(page.includes('listGpuAllocations'), true)
  assert.equal(page.includes('DRP_NODE_SLOTS_YAML'), false)
  assert.equal(page.includes("t('admin.compute.emptyState')"), true)
})

test('审计页分页 page_size 有 100 上限且经 domain 统一收敛', async () => {
  const auditDomain = await import('../src/domain/admin/audit.ts')

  assert.equal(auditDomain.MAX_AUDIT_PAGE_SIZE, 100)
  assert.equal(auditDomain.buildAuditQueryParams({ page_size: 500 }).page_size, 100)
  assert.equal(auditDomain.buildAuditQueryParams({ page_size: 0 }).page_size, 50)
  assert.deepEqual(
    auditDomain.buildAuditQueryParams({ actor: '  ', action: 'login' }),
    { action: 'login', page: 1, page_size: 50 }
  )

  const page = readSource('src/views/admin/Audit.vue')
  assert.equal(page.includes('buildAuditQueryParams'), true)
  assert.equal(/(page_size:\s*(?:[2-9]\d{2}|\d{4,}))/.test(page), false)
})
