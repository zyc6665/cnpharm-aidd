export type JsonResultEntryKind = 'scalar' | 'object' | 'array' | 'empty'

export interface JsonResultEntry {
  key: string
  label: string
  kind: JsonResultEntryKind
  value?: string
  rawValue: unknown
  children?: JsonResultEntry[]
}

export function isJsonRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function formatJsonResultLabel(key: string): string {
  const normalized = key
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()

  if (!normalized) {
    return 'Value'
  }

  return normalized
    .split(' ')
    .map(word => word ? `${word[0]?.toUpperCase()}${word.slice(1)}` : '')
    .join(' ')
}

export function formatJsonResultValue(value: unknown): string {
  if (value === null || value === undefined) {
    return 'None'
  }

  if (typeof value === 'boolean') {
    return value ? 'True' : 'False'
  }

  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      return String(value)
    }

    if (Number.isInteger(value)) {
      return String(value)
    }

    return value.toFixed(4).replace(/\.?0+$/, '')
  }

  if (typeof value === 'string') {
    return value
  }

  return String(value)
}

function buildJsonResultEntry(key: string, value: unknown): JsonResultEntry {
  const label = formatJsonResultLabel(key)

  if (Array.isArray(value)) {
    return {
      key,
      label,
      kind: value.length ? 'array' : 'empty',
      rawValue: value,
      children: value.map((item, index) => buildJsonResultEntry(`${key}-${index}`, item)).map((entry, index) => ({
        ...entry,
        label: `Item ${index + 1}`
      }))
    }
  }

  if (isJsonRecord(value)) {
    const children = buildJsonResultEntries(value)

    return {
      key,
      label,
      kind: children.length ? 'object' : 'empty',
      rawValue: value,
      children
    }
  }

  return {
    key,
    label,
    kind: value === null || value === undefined ? 'empty' : 'scalar',
    value: formatJsonResultValue(value),
    rawValue: value
  }
}

export function buildJsonResultEntries(value: unknown): JsonResultEntry[] {
  if (Array.isArray(value)) {
    return value.map((item, index) => buildJsonResultEntry(String(index), item))
  }

  if (isJsonRecord(value)) {
    return Object.entries(value).map(([key, childValue]) => buildJsonResultEntry(key, childValue))
  }

  return [buildJsonResultEntry('value', value)]
}
