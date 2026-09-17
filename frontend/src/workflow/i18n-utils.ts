const WORKFLOW_LABEL_FALLBACK = 'Untitled Node'

export function formatWorkflowKey(key: unknown, fallback = WORKFLOW_LABEL_FALLBACK): string {
  const normalizedKey = typeof key === 'string' ? key.trim() : ''
  if (!normalizedKey) {
    return fallback
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
  hasTranslation: (key: string) => boolean,
  fallback = WORKFLOW_LABEL_FALLBACK,
): string {
  const normalizedKey = typeof key === 'string' ? key.trim() : ''
  if (!normalizedKey) {
    return fallback
  }

  return hasTranslation(normalizedKey) ? translate(normalizedKey) : formatWorkflowKey(normalizedKey, fallback)
}
