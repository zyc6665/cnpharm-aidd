import type { SchemaProperty, SchemaValueType, ToolSchema } from '../../types/models'

type UiFieldType = Extract<
  SchemaValueType,
  'string' | 'number' | 'boolean' | 'file' | 'select' | 'array' | 'object'
>

export interface UploadedToolFile {
  fileId: string
  filename: string
  downloadUrl: string
}

export interface BuildTaskSubmissionPayloadOptions {
  flattenedSchema: ToolSchema
  formState: Record<string, unknown>
  uploadedFiles: Record<string, UploadedToolFile | undefined>
  executorType?: string
}

export interface BuildTaskSubmissionPayloadResult {
  params: Record<string, unknown>
  fileIds: string[]
}

export interface BuildToolFormInitialStateOptions {
  flattenedSchema?: ToolSchema
  draft?: Record<string, unknown>
}

export interface BuildToolFormInitialStateResult {
  formState: Record<string, unknown>
  fileFieldKeys: string[]
}

export function isFileSchemaProperty(prop: SchemaProperty): boolean {
  return prop.type === 'file' || prop.format === 'file' || prop.format === 'uri'
}

function toLabel(fieldName: string): string {
  return fieldName
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, char => char.toUpperCase())
}

function normalizeSchemaType(type?: SchemaProperty['type']): UiFieldType {
  const resolvedType = Array.isArray(type)
    ? type.find(candidate => candidate !== 'null') || 'string'
    : type || 'string'

  if (resolvedType === 'integer') {
    return 'number'
  }

  if (
    resolvedType === 'string' ||
    resolvedType === 'number' ||
    resolvedType === 'boolean' ||
    resolvedType === 'file' ||
    resolvedType === 'select' ||
    resolvedType === 'array' ||
    resolvedType === 'object'
  ) {
    return resolvedType
  }

  return 'string'
}

function includesObjectType(type?: SchemaProperty['type']): boolean {
  return Array.isArray(type) ? type.includes('object') : type === 'object'
}

function shouldRenderStringArrayAsText(rawProperty: SchemaProperty): boolean {
  const type = rawProperty.type
  const itemType = rawProperty.items?.type
  const itemAllowsString = Array.isArray(itemType) ? itemType.includes('string') : itemType === 'string'

  return (
    Array.isArray(type) &&
    type.includes('array') &&
    type.includes('string') &&
    itemAllowsString &&
    !rawProperty.items?.enum
  )
}

function hasValue(value: unknown): boolean {
  if (value === undefined || value === null || value === '') {
    return false
  }

  if (Array.isArray(value) && value.length === 0) {
    return false
  }

  return true
}

function assignFieldValue(
  params: Record<string, unknown>,
  key: string,
  prop: SchemaProperty,
  value: unknown
) {
  if (prop._parentKey && prop._originalKey) {
    const parentValue = params[prop._parentKey]
    const nextParent =
      parentValue && typeof parentValue === 'object' && !Array.isArray(parentValue)
        ? (parentValue as Record<string, unknown>)
        : {}

    nextParent[prop._originalKey] = value
    params[prop._parentKey] = nextParent
    return
  }

  params[key] = value
}

function assignWrappedRootValue(
  params: Record<string, unknown>,
  wrapperKey: 'params' | 'input_files',
  key: string,
  value: unknown
) {
  const wrapperValue = params[wrapperKey]
  const nextWrapper =
    wrapperValue && typeof wrapperValue === 'object' && !Array.isArray(wrapperValue)
      ? (wrapperValue as Record<string, unknown>)
      : {}

  nextWrapper[key] = value
  params[wrapperKey] = nextWrapper
}

function normalizeFlattenedProperty(
  fieldKey: string,
  rawProperty: SchemaProperty,
  parentKey?: string
): SchemaProperty | null {
  const originalKey = parentKey ? fieldKey : undefined
  const normalizedKey = parentKey ? `${parentKey}.${fieldKey}` : fieldKey
  const platformManaged = !parentKey && fieldKey === 'task_id'

  if (platformManaged || rawProperty.hidden === true) {
    return null
  }

  const renderStringArrayAsText = shouldRenderStringArrayAsText(rawProperty)
  const normalizedType =
    parentKey === 'input_files' || rawProperty.format === 'file' || rawProperty.format === 'uri'
      ? 'file'
      : renderStringArrayAsText
        ? 'string'
        : normalizeSchemaType(rawProperty.type)

  return {
    ...rawProperty,
    type: normalizedType,
    title: rawProperty.title || toLabel(fieldKey),
    format: parentKey === 'input_files' ? 'file' : renderStringArrayAsText ? 'textarea' : rawProperty.format,
    _parentKey: parentKey,
    _originalKey: originalKey,
    _platformManaged: platformManaged
  }
}

export function flattenToolInputSchema(schema?: ToolSchema): ToolSchema | undefined {
  if (!schema?.properties) {
    return undefined
  }

  const flattened: Record<string, SchemaProperty> = {}
  const required: string[] = []

  for (const [key, rawProperty] of Object.entries(schema.properties)) {
    if (includesObjectType(rawProperty.type) && rawProperty.properties) {
      for (const [subKey, subProperty] of Object.entries(rawProperty.properties)) {
        const normalized = normalizeFlattenedProperty(subKey, subProperty, key)
        if (!normalized) {
          continue
        }

        const flatKey = `${key}.${subKey}`
        flattened[flatKey] = normalized

        if (rawProperty.required?.includes(subKey)) {
          required.push(flatKey)
        }
      }
      continue
    }

    const normalized = normalizeFlattenedProperty(key, rawProperty)
    if (!normalized) {
      continue
    }

    flattened[key] = normalized
    if (schema.required?.includes(key)) {
      required.push(key)
    }
  }

  return {
    type: 'object',
    properties: flattened,
    required
  }
}

export function buildToolFormInitialState(
  options: BuildToolFormInitialStateOptions
): BuildToolFormInitialStateResult {
  const formState: Record<string, unknown> = {}
  const fileFieldKeys: string[] = []

  if (!options.flattenedSchema?.properties) {
    return {
      formState,
      fileFieldKeys
    }
  }

  for (const [key, prop] of Object.entries(options.flattenedSchema.properties)) {
    if (options.draft && Object.prototype.hasOwnProperty.call(options.draft, key)) {
      formState[key] = options.draft[key]
    } else if (prop.default !== undefined) {
      formState[key] = prop.default
    }

    if (isFileSchemaProperty(prop)) {
      fileFieldKeys.push(key)
    }
  }

  return {
    formState,
    fileFieldKeys
  }
}

export function flattenExampleParams(
  flattenedSchema: ToolSchema,
  exampleParams: Record<string, unknown>
): Record<string, unknown> {
  const values: Record<string, unknown> = {}

  for (const [key, prop] of Object.entries(flattenedSchema.properties)) {
    if (prop._parentKey && prop._originalKey) {
      const parentValue = exampleParams[prop._parentKey]
      if (parentValue && typeof parentValue === 'object' && !Array.isArray(parentValue)) {
        const nestedValues = parentValue as Record<string, unknown>
        if (Object.prototype.hasOwnProperty.call(nestedValues, prop._originalKey)) {
          values[key] = nestedValues[prop._originalKey]
        }
      }
      continue
    }

    if (Object.prototype.hasOwnProperty.call(exampleParams, key)) {
      values[key] = exampleParams[key]
    }
  }

  return values
}

export function buildTaskSubmissionPayload(
  options: BuildTaskSubmissionPayloadOptions
): BuildTaskSubmissionPayloadResult {
  const { flattenedSchema, formState, uploadedFiles, executorType } = options
  const params: Record<string, unknown> = {}
  const fileIds: string[] = []

  for (const [key, prop] of Object.entries(flattenedSchema.properties)) {
    const uploadedFile = uploadedFiles[key]
    if (uploadedFile) {
      fileIds.push(uploadedFile.fileId)

      if (executorType === 'ssh_job') {
        const runtimePath = `input/${uploadedFile.filename}`

        if (prop._parentKey === 'input_files') {
          assignFieldValue(params, key, prop, runtimePath)
        } else if (!prop._parentKey && isFileSchemaProperty(prop)) {
          assignWrappedRootValue(params, 'input_files', key, runtimePath)
        } else {
          assignFieldValue(params, key, prop, runtimePath)
        }
      } else {
        assignFieldValue(params, key, prop, uploadedFile.downloadUrl)
      }
      continue
    }

    const value = formState[key]
    if (!hasValue(value)) {
      continue
    }

    if (executorType === 'ssh_job' && !prop._parentKey) {
      assignWrappedRootValue(params, 'params', key, value)
    } else {
      assignFieldValue(params, key, prop, value)
    }
  }

  return {
    params,
    fileIds: [...new Set(fileIds)]
  }
}
