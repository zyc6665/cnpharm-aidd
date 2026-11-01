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

test('SLOT_STATE_TONES 覆盖后端五种卡位状态 + UNKNOWN 兜底并给出状态色', async () => {
  const computeDomain = await import('../src/domain/admin/compute.ts')
  const tones = computeDomain.SLOT_STATE_TONES

  assert.deepEqual(
    Object.keys(tones).sort(),
    ['BORROWED', 'BUSY', 'FAULT', 'FREE', 'RESERVED', 'UNKNOWN']
  )
  assert.equal(tones.FREE, 'success')
  assert.equal(tones.RESERVED, 'warning')
  assert.equal(tones.BUSY, 'processing')
  assert.equal(tones.FAULT, 'error')
  assert.equal(tones.BORROWED, 'default')
  assert.equal(tones.UNKNOWN, 'default')
  assert.deepEqual(
    [...computeDomain.DECLARED_SLOT_STATES].sort(),
    ['BORROWED', 'BUSY', 'FAULT', 'FREE', 'RESERVED']
  )
})

test('countSlotsByState 对空数组返回五个 0（外加 UNKNOWN 兜底桶）', async () => {
  const computeDomain = await import('../src/domain/admin/compute.ts')
  const counts = computeDomain.countSlotsByState([])

  assert.deepEqual(counts, { FREE: 0, RESERVED: 0, BUSY: 0, FAULT: 0, BORROWED: 0, UNKNOWN: 0 })
  assert.equal(computeDomain.countSlotsByState(undefined).FREE, 0)
})

test('未知卡位状态归一化为 UNKNOWN 而非 FREE', async () => {
  const computeDomain = await import('../src/domain/admin/compute.ts')

  // 后端新增状态（DRAINING）或拼写错误都不得被乐观地当成「空闲」。
  assert.equal(computeDomain.normalizeSlotState('DRAINING'), 'UNKNOWN')
  assert.equal(computeDomain.normalizeSlotState('free'), 'UNKNOWN')
  assert.equal(computeDomain.normalizeSlotState(''), 'UNKNOWN')
  assert.equal(computeDomain.normalizeSlotState(undefined), 'UNKNOWN')
  assert.equal(computeDomain.normalizeSlotState('FREE'), 'FREE')
  assert.equal(computeDomain.normalizeSlotState('BORROWED'), 'BORROWED')

  // 统计层面：未知状态进 UNKNOWN 桶，不会算进 FREE。
  const counts = computeDomain.countSlotsByState([
    { state: 'FREE' },
    { state: 'DRAINING' },
    { state: 'BUSY' }
  ] as never)
  assert.deepEqual(counts, { FREE: 1, RESERVED: 0, BUSY: 1, FAULT: 0, BORROWED: 0, UNKNOWN: 1 })
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

test('审计页查询失败必须显式呈现错误态，不能静默成空表', () => {
  const page = readSource('src/views/admin/Audit.vue')

  assert.equal(page.includes('errorMessage'), true)
  assert.equal(page.includes('AppInlineError'), true)
  assert.equal(page.includes("t('admin.audit.loadError')"), true)
  assert.equal(page.includes('retryLoad'), true)
})

test('算力页分配表只展示后端真实返回的字段', () => {
  const page = readSource('src/views/admin/Compute.vue')

  // gpu_index 缺失时必须渲染 '-'，不得捏造成 0 号卡。
  assert.equal(page.includes('record.gpu_index === null'), true)
  // 订单/释放时间这类后端未返回的列不得出现在表头。
  assert.equal(page.includes("key: 'released_at'"), false)
  assert.equal(page.includes('record.released_at'), false)
  assert.equal(page.includes("t('admin.compute.releasedAt')"), false)
  // 未知状态需把后端原始状态原文显示出来，便于排障。
  assert.equal(page.includes('raw_state'), true)
  assert.equal(page.includes("t('admin.compute.rawState')"), true)
})
