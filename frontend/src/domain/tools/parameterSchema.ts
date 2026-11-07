import type { SchemaProperty, ToolSchema } from '@/types/models'

export type ParameterValue = string | number | boolean | null | undefined
export type ParameterValues = Record<string, ParameterValue>

const NUMBER_TYPES = new Set(['number', 'integer'])

export function isToolSchema(value: unknown): value is ToolSchema {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<ToolSchema>
  return candidate.type === 'object' && Boolean(candidate.properties) && typeof candidate.properties === 'object'
}

export function schemaProperties(schema?: ToolSchema | null): Array<[string, SchemaProperty]> {
  if (!schema?.properties) return []
  return Object.entries(schema.properties)
}

export function isRequired(schema: ToolSchema | null | undefined, key: string): boolean {
  return Boolean(schema?.required?.includes(key))
}

export function defaultValueForProperty(property: SchemaProperty): ParameterValue {
  if (property.default !== undefined) return property.default as ParameterValue
  const type = Array.isArray(property.type) ? property.type[0] : property.type
  if (type === 'boolean') return false
  if (NUMBER_TYPES.has(String(type))) return undefined
  if (type === 'array') return undefined
  return ''
}

export function buildDefaultValues(
  schema?: ToolSchema | null,
  options: { omit?: string[] } = {}
): ParameterValues {
  const omit = new Set(options.omit ?? [])
  const values: ParameterValues = {}
  for (const [key, property] of schemaProperties(schema)) {
    if (omit.has(key) || property.hidden) continue
    values[key] = defaultValueForProperty(property)
  }
  return values
}

function isEmptyValue(value: ParameterValue): boolean {
  return value === undefined || value === null || (typeof value === 'string' && value.trim() === '')
}

export function normalizeParameters(
  schema: ToolSchema | null | undefined,
  values: ParameterValues
): Record<string, string | number | boolean> {
  const payload: Record<string, string | number | boolean> = {}
  for (const [key, property] of schemaProperties(schema)) {
    if (property.hidden) continue
    const value = values[key]
    if (isEmptyValue(value)) continue
    const type = Array.isArray(property.type) ? property.type[0] : property.type
    if (NUMBER_TYPES.has(String(type))) {
      const numeric = Number(value)
      if (!Number.isFinite(numeric)) continue
      payload[key] = type === 'integer' ? Math.trunc(numeric) : numeric
    } else if (type === 'boolean') {
      payload[key] = Boolean(value)
    } else {
      payload[key] = typeof value === 'string' ? value.trim() : (value as string | number | boolean)
    }
  }
  return payload
}

export function validateParameters(
  schema: ToolSchema | null | undefined,
  values: ParameterValues
): string[] {
  const errors: string[] = []
  if (!schema) return errors
  for (const [key, property] of schemaProperties(schema)) {
    if (property.hidden) continue
    const value = values[key]
    if (isRequired(schema, key) && isEmptyValue(value)) {
      errors.push(`${key}:required`)
      continue
    }
    if (isEmptyValue(value)) continue
    const type = Array.isArray(property.type) ? property.type[0] : property.type
    if (NUMBER_TYPES.has(String(type))) {
      const numeric = Number(value)
      if (!Number.isFinite(numeric)) {
        errors.push(`${key}:invalid-number`)
        continue
      }
      if (property.minimum !== undefined && numeric < property.minimum) errors.push(`${key}:below-minimum`)
      if (property.maximum !== undefined && numeric > property.maximum) errors.push(`${key}:above-maximum`)
    }
    if (typeof value === 'string') {
      const trimmed = value.trim()
      if (property.minLength !== undefined && trimmed.length < property.minLength) {
        errors.push(`${key}:too-short`)
      }
      if (property.maxLength !== undefined && trimmed.length > property.maxLength) {
        errors.push(`${key}:too-long`)
      }
    }
    if (property.enum?.length && !property.enum.includes(value)) {
      errors.push(`${key}:invalid-option`)
    }
  }
  return errors
}
