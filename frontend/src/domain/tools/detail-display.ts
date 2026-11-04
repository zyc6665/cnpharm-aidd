import type { TypedArtifact } from '@/types/artifacts'
import { parseServerDate } from '@/utils/datetime'

export function formatToolMetricCount(num?: number | null): string {
  if (num == null) {
    return '0'
  }
  if (num >= 10000) {
    return `${(num / 10000).toFixed(1)}w`
  }
  if (num >= 1000) {
    return `${(num / 1000).toFixed(1)}k`
  }
  return num.toString()
}

export function formatToolDate(dateStr: string): string {
  return parseServerDate(dateStr)?.toLocaleDateString() ?? '-'
}

export function getToolStatusColor(status: string): string {
  const colors: Record<string, string> = {
    draft: 'default',
    published: 'success',
    disabled: 'warning',
    deprecated: 'error',
  }
  return colors[status] || 'default'
}

export function formatStandardArtifactLabel(artifact: TypedArtifact): string {
  const filename = artifact.latest_version.filename || artifact.name
  return `${artifact.name || filename} · v${artifact.latest_version.version}`
}
