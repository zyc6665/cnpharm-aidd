import type { UploadFile } from 'ant-design-vue'
import type { TypedArtifact } from '@/types/artifacts'
import type { ArtifactFile, FileUploadResponse, TaskCreateParams, ToolSchema } from '@/types/models'
import {
  artifactFileToUploadedToolFile,
  fileResponseToUploadedToolFile,
} from './detail-file-inputs'
import {
  buildTaskSubmissionPayload,
  type UploadedToolFile,
} from './detail-schema'
import {
  buildStandardInputBindings,
  buildStandardInputBindingsFromFileFields,
  buildStandardInputUploadsFromFileFields,
  hasStandardInputFileFieldBindings,
  type StandardArtifactInputSlot,
} from './standard-artifact-inputs'
import { buildStandardRunTaskExtras } from './standard-artifact-run-context'

export type ToolRunUploadFile = (file: File) => Promise<FileUploadResponse>

export interface ToolRunResolvedFiles {
  example?: Record<string, FileUploadResponse | undefined>
  converted?: Record<string, FileUploadResponse | undefined>
}

export interface BuildToolRunTaskPayloadOptions {
  toolId: string
  taskName?: string
  projectId?: string
  flattenedSchema: ToolSchema
  formState: Record<string, unknown>
  fileList: Record<string, UploadFile[] | undefined>
  selectedArtifacts: Record<string, ArtifactFile | undefined>
  resolvedFiles?: ToolRunResolvedFiles
  standardInputSlots: readonly StandardArtifactInputSlot[]
  standardInputFileFieldBindings: Record<string, string>
  selectedStandardArtifacts: Record<string, TypedArtifact | undefined>
  standardInputFileList: Record<string, UploadFile[] | undefined>
  executorType?: string
  uploadFile: ToolRunUploadFile
}

export interface ToolRunStandardInputOptions {
  standardInputSlots: readonly StandardArtifactInputSlot[]
  standardInputFileFieldBindings: Record<string, string>
  selectedArtifacts: Record<string, ArtifactFile | undefined>
  uploadedFiles: Record<string, UploadedToolFile | undefined>
  selectedStandardArtifacts: Record<string, TypedArtifact | undefined>
  directStandardInputUploads: Record<string, string>
}

export interface ToolRunStandardInputProjection {
  usesConcreteStandardInputFields: boolean
  inputBindings: Record<string, string>
  standardInputUploads: Record<string, string>
  boundFieldKeys: string[]
}

export type ToolRunSubmissionGate =
  | { status: 'requires_login' }
  | { status: 'missing_schema' }
  | { status: 'missing_standard_inputs'; slotNames: string[] }
  | { status: 'ready'; toolId: string; schema: ToolSchema }

export interface ResolveToolRunSubmissionGateOptions {
  isLoggedIn: boolean
  toolId?: string
  schema?: ToolSchema
  missingRequiredStandardSlots: readonly StandardArtifactInputSlot[]
}

export function resolveToolRunSubmissionGate(
  options: ResolveToolRunSubmissionGateOptions,
): ToolRunSubmissionGate {
  if (!options.isLoggedIn) {
    return { status: 'requires_login' }
  }

  if (!options.schema || !options.toolId) {
    return { status: 'missing_schema' }
  }

  if (options.missingRequiredStandardSlots.length) {
    return {
      status: 'missing_standard_inputs',
      slotNames: options.missingRequiredStandardSlots.map(slot => slot.name),
    }
  }

  return {
    status: 'ready',
    toolId: options.toolId,
    schema: options.schema,
  }
}

function compactName(value?: string): string | undefined {
  return value?.trim() || undefined
}

function omitRecordKeys<T>(record: Record<string, T>, keys: readonly string[]): Record<string, T> {
  if (!keys.length) {
    return record
  }

  const omitted = new Set(keys)
  return Object.fromEntries(
    Object.entries(record).filter(([key]) => !omitted.has(key))
  ) as Record<string, T>
}

function addResolvedFiles(
  uploadedFiles: Record<string, UploadedToolFile | undefined>,
  files?: Record<string, FileUploadResponse | undefined>,
) {
  for (const [key, file] of Object.entries(files ?? {})) {
    if (file) {
      uploadedFiles[key] = fileResponseToUploadedToolFile(file)
    }
  }
}

async function collectUploadedFiles(
  options: BuildToolRunTaskPayloadOptions,
): Promise<Record<string, UploadedToolFile | undefined>> {
  const uploadedFiles: Record<string, UploadedToolFile | undefined> = {}

  addResolvedFiles(uploadedFiles, options.resolvedFiles?.example)
  addResolvedFiles(uploadedFiles, options.resolvedFiles?.converted)

  for (const [key, artifact] of Object.entries(options.selectedArtifacts)) {
    if (artifact) {
      uploadedFiles[key] = artifactFileToUploadedToolFile(artifact)
    }
  }

  for (const [key, items] of Object.entries(options.fileList)) {
    const fileItem = items?.[0]
    if (!fileItem?.originFileObj) {
      continue
    }

    const uploaded = await options.uploadFile(fileItem.originFileObj as File)
    uploadedFiles[key] = fileResponseToUploadedToolFile(uploaded)
  }

  return uploadedFiles
}

async function collectStandardInputUploads(
  options: BuildToolRunTaskPayloadOptions,
): Promise<Record<string, string>> {
  const standardInputUploads: Record<string, string> = {}

  for (const slot of options.standardInputSlots) {
    const fileItem = options.standardInputFileList[slot.name]?.[0]
    if (!fileItem?.originFileObj) {
      continue
    }

    const uploaded = await options.uploadFile(fileItem.originFileObj as File)
    standardInputUploads[slot.name] = String(uploaded.id)
  }

  return standardInputUploads
}

export function resolveToolRunStandardInputs(
  options: ToolRunStandardInputOptions,
): ToolRunStandardInputProjection {
  const usesConcreteStandardInputFields = hasStandardInputFileFieldBindings(
    options.standardInputFileFieldBindings,
  )
  if (!usesConcreteStandardInputFields) {
    return {
      usesConcreteStandardInputFields: false,
      inputBindings: buildStandardInputBindings(options.selectedStandardArtifacts),
      standardInputUploads: options.directStandardInputUploads,
      boundFieldKeys: [],
    }
  }

  const concreteBindingProjection = buildStandardInputBindingsFromFileFields({
    slots: options.standardInputSlots,
    fileFieldBindings: options.standardInputFileFieldBindings,
    selectedArtifacts: options.selectedArtifacts,
  })
  const concreteUploadProjection = buildStandardInputUploadsFromFileFields({
    slots: options.standardInputSlots,
    fileFieldBindings: options.standardInputFileFieldBindings,
    uploadedFiles: options.uploadedFiles,
    selectedArtifacts: options.selectedArtifacts,
    inputBindings: concreteBindingProjection.inputBindings,
  })

  return {
    usesConcreteStandardInputFields: true,
    inputBindings: concreteBindingProjection.inputBindings,
    standardInputUploads: concreteUploadProjection.standardInputUploads,
    boundFieldKeys: [
      ...concreteBindingProjection.boundFieldKeys,
      ...concreteUploadProjection.boundFieldKeys,
    ],
  }
}

export async function buildToolRunTaskPayload(
  options: BuildToolRunTaskPayloadOptions,
): Promise<TaskCreateParams> {
  const uploadedFiles = await collectUploadedFiles(options)
  const usesConcreteStandardInputFields = hasStandardInputFileFieldBindings(
    options.standardInputFileFieldBindings,
  )
  const standardInputs = resolveToolRunStandardInputs({
    standardInputSlots: options.standardInputSlots,
    standardInputFileFieldBindings: options.standardInputFileFieldBindings,
    selectedArtifacts: options.selectedArtifacts,
    uploadedFiles,
    selectedStandardArtifacts: options.selectedStandardArtifacts,
    directStandardInputUploads: usesConcreteStandardInputFields
      ? {}
      : await collectStandardInputUploads(options),
  })
  const payload = buildTaskSubmissionPayload({
    flattenedSchema: options.flattenedSchema,
    formState: parseStructuredFormValues(
      options.flattenedSchema,
      omitRecordKeys(options.formState, standardInputs.boundFieldKeys),
    ),
    uploadedFiles: omitRecordKeys(uploadedFiles, standardInputs.boundFieldKeys),
    executorType: options.executorType,
  })

  const name = compactName(options.taskName)
  const projectId = options.projectId?.trim() || undefined

  return {
    ...(name ? { name } : {}),
    tool_id: options.toolId,
    ...(projectId ? { project_id: projectId } : {}),
    params: payload.params,
    file_ids: payload.fileIds.length > 0 ? payload.fileIds : undefined,
    ...buildStandardRunTaskExtras({
      inputBindings: standardInputs.inputBindings,
      standardInputUploads: standardInputs.standardInputUploads,
    }),
  }
}

function parseStructuredFormValues(
  schema: ToolSchema,
  formState: Record<string, unknown>,
): Record<string, unknown> {
  const normalized = { ...formState }
  for (const [key, property] of Object.entries(schema.properties)) {
    if (property.type !== 'object' && property.type !== 'array') continue
    const value = normalized[key]
    if (value === undefined || value === null || value === '') continue
    if (typeof value !== 'string') continue

    let parsed: unknown
    try {
      parsed = JSON.parse(value)
    } catch {
      throw new Error(`${property.title ?? key} must contain valid JSON`)
    }
    const validShape = property.type === 'object'
      ? parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)
      : Array.isArray(parsed)
    if (!validShape) {
      throw new Error(`${property.title ?? key} must be a JSON ${property.type}`)
    }
    normalized[key] = parsed
  }
  return normalized
}
