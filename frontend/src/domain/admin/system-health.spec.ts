import { test } from 'vitest'
import assert from 'node:assert/strict'
import type { SystemHealth } from '@/types/models'
import {
  formatAdminDateTime,
  getModelServiceTestStatusColor,
  getSystemHealthServiceLabel,
  getSystemHealthStatusColor,
  getSystemHealthStatusText,
  sortSystemHealthServices
} from './system-health'

type HealthService = SystemHealth['services'][number]

const services: HealthService[] = [
  { name: 'custom', status: 'unknown', message: 'custom' },
  { name: 'tool_package_runtime', status: 'healthy', message: 'ready' },
  { name: 'cache', status: 'unhealthy', message: 'down' },
  { name: 'database', status: 'healthy', message: 'ok' },
  { name: 'database_schema', status: 'healthy', message: 'migrated' },
  { name: 'storage', status: 'unknown', message: 'checking' },
  { name: 'celery', status: 'healthy', message: 'ready' },
  { name: 'executor_gateway', status: 'healthy', message: 'ready' }
]

test('系统健康服务按固定运行依赖顺序展示，未知服务排在最后', () => {
  assert.deepEqual(
    sortSystemHealthServices(services).map(service => service.name),
    ['database', 'database_schema', 'cache', 'storage', 'celery', 'executor_gateway', 'tool_package_runtime', 'custom']
  )
})

test('系统健康状态颜色和文案保持后台约定', () => {
  assert.equal(getSystemHealthStatusColor('healthy'), 'green')
  assert.equal(getSystemHealthStatusColor('degraded'), 'orange')
  assert.equal(getSystemHealthStatusColor('unknown'), 'orange')
  assert.equal(getSystemHealthStatusColor('unhealthy'), 'red')
  assert.equal(getSystemHealthStatusColor(undefined), 'default')

  assert.equal(getSystemHealthStatusText('healthy'), '正常')
  assert.equal(getSystemHealthStatusText('degraded'), '降级')
  assert.equal(getSystemHealthStatusText('unhealthy'), '异常')
  assert.equal(getSystemHealthStatusText('unknown'), '未知')
  assert.equal(getSystemHealthStatusText(undefined), '-')
})

test('系统健康服务名称展示为中文业务标签', () => {
  assert.equal(getSystemHealthServiceLabel('database'), '数据库连接')
  assert.equal(getSystemHealthServiceLabel('database_schema'), '数据库 Schema')
  assert.equal(getSystemHealthServiceLabel('cache'), '缓存')
  assert.equal(getSystemHealthServiceLabel('storage'), '存储')
  assert.equal(getSystemHealthServiceLabel('celery'), '任务队列')
  assert.equal(getSystemHealthServiceLabel('executor_gateway'), '执行器网关')
  assert.equal(getSystemHealthServiceLabel('tool_package_runtime'), 'Tool Package Runtime')
  assert.equal(getSystemHealthServiceLabel('custom'), 'custom')
})

test('模型服务测试状态和日期格式保持系统页约定', () => {
  assert.equal(getModelServiceTestStatusColor('success'), 'green')
  assert.equal(getModelServiceTestStatusColor('failure'), 'red')
  assert.equal(getModelServiceTestStatusColor(undefined), 'default')
  assert.equal(formatAdminDateTime(undefined), '-')
  assert.equal(formatAdminDateTime('not-a-date'), 'not-a-date')
  assert.notEqual(formatAdminDateTime('2026-08-05T00:00:00Z'), '-')
})
