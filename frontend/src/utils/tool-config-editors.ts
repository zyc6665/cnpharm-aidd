export interface KeyValueEntry {
  key: string
  value: string
}

export function recordToKeyValueEntries(value: unknown): KeyValueEntry[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return []
  }

  return Object.entries(value as Record<string, unknown>).map(([key, entryValue]) => ({
    key,
    value: entryValue == null ? '' : String(entryValue)
  }))
}

export function keyValueEntriesToRecord(entries: KeyValueEntry[]): Record<string, string> {
  const result: Record<string, string> = {}
  for (const entry of entries) {
    const key = entry.key.trim()
    if (!key && !entry.value) {
      continue
    }
    if (!key) {
      throw new Error('配置键不能为空')
    }
    if (Object.prototype.hasOwnProperty.call(result, key)) {
      throw new Error(`配置键不能重复: ${key}`)
    }
    result[key] = entry.value
  }
  return result
}

export function normalizeStringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return stringListForConfig(value.map(item => String(item)))
  }
  if (typeof value === 'string') {
    return value.trim() ? value.trim().split(/\s+/) : []
  }
  return []
}

export function stringListForConfig(items: string[]): string[] {
  return items.map(item => item.trim()).filter(Boolean)
}
