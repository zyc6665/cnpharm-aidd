import type { SystemHealth } from '@/types/models'
import { formatServerDateTime } from '@/utils/datetime'

export type SystemHealthService = SystemHealth['services'][number]
export type SystemHealthStatus = SystemHealth['status'] | SystemHealthService['status'] | 'unknown'

const serviceOrder = [
  'database',
  'database_schema',
  'cache',
  'storage',
  'celery',
  'executor_gateway',
  'tool_package_runtime'
]

const serviceLabels: Record<string, string> = {
  database: '数据库连接',
  database_schema: '数据库 Schema',
  cache: '缓存',
  storage: '存储',
  celery: '任务队列',
  executor_gateway: '执行器网关',
  tool_package_runtime: 'Tool Package Runtime'
}

export function sortSystemHealthServices(
  services: SystemHealthService[] | undefined
): SystemHealthService[] {
  return [...(services ?? [])].sort((left, right) => {
    return getServiceOrderIndex(left.name) - getServiceOrderIndex(right.name)
  })
}

export function getSystemHealthStatusColor(status?: string | null): string {
  if (status === 'healthy') return 'green'
  if (status === 'degraded' || status === 'unknown') return 'orange'
  if (status === 'unhealthy') return 'red'
  return 'default'
}

export function getSystemHealthStatusText(status?: string | null): string {
  if (status === 'healthy') return '正常'
  if (status === 'degraded') return '降级'
  if (status === 'unhealthy') return '异常'
  if (status === 'unknown') return '未知'
  return '-'
}

export function getSystemHealthServiceLabel(name: string): string {
  return serviceLabels[name] ?? name
}

export function getModelServiceTestStatusColor(status?: string | null): string {
  if (status === 'success') return 'green'
  if (status === 'failure') return 'red'
  return 'default'
}

/**
 * 后台时间展示（本地时区）。
 *
 * 服务端时间是不带时区的 UTC，直接 `new Date()` 会按本地时区解释，
 * 东八区用户看到的每个时间都晚 8 小时。统一走 `utils/datetime` 补 `Z`。
 */
export function formatAdminDateTime(value?: string | null): string {
  return formatServerDateTime(value)
}

function getServiceOrderIndex(name: string): number {
  const index = serviceOrder.indexOf(name)
  return index === -1 ? serviceOrder.length : index
}
