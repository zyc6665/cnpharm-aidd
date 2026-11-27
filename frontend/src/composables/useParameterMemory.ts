import { computed, type Ref } from 'vue'
import { useUserStore } from '@/stores/user'
import {
  buildDefaultValues,
  type ParameterValues,
} from '@/domain/tools/parameterSchema'
import type { ToolSchema } from '@/types/models'

export interface UseParameterMemoryOptions {
  scope: string
  slug: Ref<string>
  schema: Ref<ToolSchema | null>
  omitKeys?: string[] | Ref<string[]>
}

export interface ParameterMemoryResult {
  defaults: ParameterValues
  restored: ParameterValues
  values: ParameterValues
  diffKeys: string[]
  restoredFromMemory: boolean
}

function resolveOmit(omit?: string[] | Ref<string[]>): string[] {
  if (!omit) return []
  return Array.isArray(omit) ? omit : omit.value
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Safely reads current user id even in unit tests without an active Pinia store. */
function resolveUserId(): string {
  try {
    const userStore = useUserStore() as { user?: { id?: string } | null; userInfo?: { id?: string } | null }
    const id = userStore.user?.id ?? userStore.userInfo?.id
    return id ? String(id) : 'anon'
  } catch {
    return 'anon'
  }
}

const MEMORY_FORMAT_VERSION = 1

function isSameParameterValue(a: unknown, b: unknown): boolean {
  if (Object.is(a, b)) return true
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, idx) => isSameParameterValue(item, b[idx]))
  }
  if (isPlainObject(a) && isPlainObject(b)) {
    const keysA = Object.keys(a)
    const keysB = Object.keys(b)
    return keysA.length === keysB.length && keysA.every(key => isSameParameterValue(a[key], b[key]))
  }
  return false
}

function matchesSchemaProperty(value: unknown, prop: Record<string, unknown> | undefined): boolean {
  if (!prop) return true
  if (Array.isArray(prop.enum) && !prop.enum.some(choice => isSameParameterValue(choice, value))) {
    return false
  }
  const type = Array.isArray(prop.type) ? prop.type[0] : prop.type
  if (type === 'integer') return typeof value === 'number' && Number.isInteger(value)
  if (type === 'number') return typeof value === 'number' && Number.isFinite(value)
  if (type === 'boolean') return typeof value === 'boolean'
  if (type === 'string') return typeof value === 'string'
  if (type === 'array') return Array.isArray(value)
  return true
}

function schemaFingerprint(schema: ToolSchema | null): string {
  const properties = schema?.properties
  if (!properties) return 'none'
  return Object.keys(properties)
    .sort()
    .map(key => {
      const prop = properties[key] as Record<string, unknown> | undefined
      const type = Array.isArray(prop?.type) ? prop?.type.join('|') : String(prop?.type ?? '')
      return `${key}:${type}`
    })
    .join(',')
}

/**
 * User-scoped, schema-validated parameter memory persisted in `localStorage`.
 * Prevents cross-user leakage and drops stale keys absent from the active schema.
 */
export function useParameterMemory(options: UseParameterMemoryOptions) {
  const storageKey = computed(() => {
    const uid = resolveUserId()
    const slug = options.slug.value || 'default'
    return `design:u:${uid}:params:${options.scope}:${slug}`
  })

  function schemaOnly(raw: ParameterValues, schema: ToolSchema | null): ParameterValues {
    const omit = new Set(resolveOmit(options.omitKeys))
    const properties = schema?.properties ?? {}
    const allowed = new Set(Object.keys(properties))
    const next: ParameterValues = {}
    for (const [key, value] of Object.entries(raw)) {
      if (omit.has(key)) continue
      if (allowed.size > 0 && !allowed.has(key)) continue
      if (value === undefined) continue
      if (allowed.size > 0 && !matchesSchemaProperty(value, properties[key] as Record<string, unknown> | undefined)) {
        continue
      }
      next[key] = value
    }
    return next
  }

  function readStored(schema: ToolSchema | null): ParameterValues {
    if (typeof localStorage === 'undefined') return {}
    try {
      const raw = localStorage.getItem(storageKey.value)
      if (!raw) return {}
      const parsed = JSON.parse(raw) as unknown
      if (!isPlainObject(parsed)) return {}
      if (typeof parsed.v === 'number' && parsed.v !== MEMORY_FORMAT_VERSION) return {}
      if (typeof parsed.schema === 'string' && schema && parsed.schema !== schemaFingerprint(schema)) return {}
      const candidate = isPlainObject(parsed.params) ? (parsed.params as ParameterValues) : (parsed as ParameterValues)
      return schemaOnly(candidate, schema)
    } catch {
      return {}
    }
  }

  function restore(schema: ToolSchema | null = options.schema.value): ParameterMemoryResult {
    const defaults = buildDefaultValues(schema, { omit: resolveOmit(options.omitKeys) })
    const restored = readStored(schema)
    const diffKeys = Object.keys(restored).filter(key => !isSameParameterValue(restored[key], defaults[key]))
    return {
      defaults,
      restored,
      values: { ...defaults, ...restored },
      diffKeys,
      restoredFromMemory: diffKeys.length > 0,
    }
  }

  function persist(values: ParameterValues): boolean {
    if (typeof localStorage === 'undefined') return false
    const schema = options.schema.value
    const filtered = schemaOnly(values, schema)
    try {
      localStorage.setItem(
        storageKey.value,
        JSON.stringify({ v: MEMORY_FORMAT_VERSION, schema: schemaFingerprint(schema), params: filtered })
      )
      return true
    } catch {
      return false
    }
  }

  function clear(): void {
    if (typeof localStorage === 'undefined') return
    try {
      localStorage.removeItem(storageKey.value)
    } catch {
      // ignore storage errors in restricted environments
    }
  }

  return {
    storageKey,
    restore,
    persist,
    clear,
  }
}
