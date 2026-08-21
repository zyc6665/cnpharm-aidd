const WORKFLOW_LABEL_FALLBACK = '未命名节点'

export function formatWorkflowKey(key: unknown): string {
  const normalizedKey = typeof key === 'string' ? key.trim() : ''
  if (!normalizedKey) {
    return WORKFLOW_LABEL_FALLBACK
  }

  const lastSegment = normalizedKey.split('.').pop() ?? normalizedKey
  if (/\s/.test(lastSegment.trim())) {
    return lastSegment
      .replace(/[-_]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
  }
  return lastSegment
    .replace(/([A-Z])/g, ' $1')
    .replace(/[-_]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function resolveWorkflowLabel(
  key: unknown,
  translate: (key: string) => string,
  hasTranslation: (key: string) => boolean
): string {
  const normalizedKey = typeof key === 'string' ? key.trim() : ''
  if (!normalizedKey) {
    return WORKFLOW_LABEL_FALLBACK
  }

  return hasTranslation(normalizedKey) ? translate(normalizedKey) : formatWorkflowKey(normalizedKey)
}
