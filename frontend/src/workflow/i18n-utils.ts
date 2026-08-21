export function formatWorkflowKey(key: string): string {
  const lastSegment = key.split('.').pop() ?? key
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
  key: string,
  translate: (key: string) => string,
  hasTranslation: (key: string) => boolean
): string {
  return hasTranslation(key) ? translate(key) : formatWorkflowKey(key)
}
