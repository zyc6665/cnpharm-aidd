import type { TaskRunPreparationPreview } from '@/types/models'

export function taskRunPreparationBlockedMessage(
  preview?: TaskRunPreparationPreview | null,
): string {
  if (!preview || preview.ready) {
    return ''
  }

  const decisionReason = Object.values(preview.binding_decisions ?? {})
    .map(decision => normalizeMessage(decision.reason))
    .find(Boolean)

  return (
    normalizeMessage(preview.blocked_reason) ||
    decisionReason ||
    '标准产物输入尚未满足工具要求'
  )
}

function normalizeMessage(value?: string | null): string {
  return typeof value === 'string' ? value.trim() : ''
}
