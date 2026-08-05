export function formatToolConfigJsonText(value: unknown, fallback: string): string {
  if (value == null) {
    return fallback
  }

  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return fallback
  }
}

export function serializeToolConfigForComparison(value: unknown): string {
  try {
    return JSON.stringify(normalizeToolConfigForComparison(value))
  } catch {
    return ''
  }
}

export function isToolConfigRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function normalizeToolConfigForComparison(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(item => normalizeToolConfigForComparison(item))
  }

  if (isToolConfigRecord(value)) {
    return Object.keys(value)
      .sort()
      .reduce<Record<string, unknown>>((acc, key) => {
        acc[key] = normalizeToolConfigForComparison(value[key])
        return acc
      }, {})
  }

  return value
}
