import type { ToolSchema } from '@/types/models'

const JSON_SCHEMA_TYPES = new Set([
  'string',
  'number',
  'integer',
  'boolean',
  'array',
  'object',
  'null',
])
const LEGACY_UI_TYPES = new Set(['file', 'select'])
const PLATFORM_PARAMETER_NAMES = new Set([
  'base_url',
  'command',
  'cpu',
  'device',
  'devices',
  'endpoint',
  'entrypoint',
  'gpu_device',
  'gpu_memory_mb',
  'gpu_required',
  'memory_mb',
  'resource_profile',
  'resources',
  'script',
  'script_content',
  'script_path',
  'timeout_sec',
  'worker_id',
  'worker_queue',
])
const CREDENTIAL_PARAMETER_NAMES = new Set([
  'access_token',
  'api_key',
  'apikey',
  'authorization',
  'credentials',
  'credential_ref',
  'headers',
  'password',
  'password_ref',
  'private_key',
  'secret',
  'secret_ref',
  'token',
])

export function createEmptyParameterSchema(): ToolSchema {
  return { type: 'object', properties: {}, required: [] }
}

export function validateParameterSchema(
  value: unknown,
  options: { allowLegacyUiTypes?: boolean } = {},
): string[] {
  if (!isRecord(value) || value.type !== 'object') {
    return ['参数 Schema 的根类型必须是 object']
  }

  if (!isRecord(value.properties)) {
    return ['参数 Schema 的 properties 必须是对象']
  }

  const properties = value.properties
  const required = value.required === undefined ? [] : value.required
  if (!Array.isArray(required) || required.some((name) => typeof name !== 'string')) {
    return ['参数 Schema 的 required 必须是字段名数组']
  }

  const errors: string[] = []
  for (const name of required) {
    if (!Object.prototype.hasOwnProperty.call(properties, name)) {
      errors.push(`必填字段「${name}」没有对应的参数定义`)
    }
  }

  for (const [name, rawProperty] of Object.entries(properties)) {
    if (!name.trim()) {
      errors.push('参数字段名不能为空')
      continue
    }
    if (!isRecord(rawProperty)) {
      errors.push(`参数「${name}」的定义必须是对象`)
      continue
    }
    if (!(options.allowLegacyUiTypes ?? true)) {
      const normalizedName = name.trim().toLowerCase().replace(/-/g, '_')
      if (PLATFORM_PARAMETER_NAMES.has(normalizedName)) {
        errors.push(`参数「${name}」属于平台资源配置，应在运行 variants 中维护`)
      } else if (CREDENTIAL_PARAMETER_NAMES.has(normalizedName)) {
        errors.push(`参数「${name}」不能作为任务参数收集凭证`)
      }
      if (['file', 'uri', 'password'].includes(String(rawProperty.format ?? ''))) {
        errors.push(`参数「${name}」应通过标准 Artifact 或平台凭证配置声明`)
      }
    }
    if (!isSupportedType(rawProperty.type, options.allowLegacyUiTypes ?? true)) {
      errors.push(`参数「${name}」缺少受支持的 type`)
    }
    if (rawProperty.title !== undefined && typeof rawProperty.title !== 'string') {
      errors.push(`参数「${name}」的 title 必须是文本`)
    }
    if (rawProperty.enum !== undefined && (!Array.isArray(rawProperty.enum) || rawProperty.enum.length === 0)) {
      errors.push(`参数「${name}」的选项至少需要一个值`)
    }
    if (
      typeof rawProperty.minimum === 'number' &&
      typeof rawProperty.maximum === 'number' &&
      rawProperty.minimum > rawProperty.maximum
    ) {
      errors.push(`参数「${name}」的最小值不能大于最大值`)
    }
  }

  return errors
}

function isSupportedType(value: unknown, allowLegacyUiTypes: boolean): boolean {
  const types = Array.isArray(value) ? value : [value]
  if (types.length === 0) return false
  return types.every((type) =>
    typeof type === 'string' &&
    (JSON_SCHEMA_TYPES.has(type) || (allowLegacyUiTypes && LEGACY_UI_TYPES.has(type)))
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
