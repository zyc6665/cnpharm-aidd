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

export async function buildToolRunTaskPayload(
  options: BuildToolRunTaskPayloadOptions,
): Promise<TaskCreateParams> {
  const uploadedFiles = await collectUploadedFiles(options)
  const concreteBindingProjection = buildStandardInputBindingsFromFileFields({
    slots: options.standardInputSlots,
    fileFieldBindings: options.standardInputFileFieldBindings,
    selectedArtifacts: options.selectedArtifacts,
  })
  const concreteUploadProjection = buildStandardInputUploadsFromFileFields({
    slots: options.standardInputSlots,
    fileFieldBindings: options.standardInputFileFieldBindings,
    uploadedFiles,
    selectedArtifacts: options.selectedArtifacts,
    inputBindings: concreteBindingProjection.inputBindings,
  })
  const concreteBoundFieldKeys = [
    ...concreteBindingProjection.boundFieldKeys,
    ...concreteUploadProjection.boundFieldKeys,
  ]
  const usesConcreteStandardInputFields = hasStandardInputFileFieldBindings(
    options.standardInputFileFieldBindings,
  )
  const inputBindings = usesConcreteStandardInputFields
    ? concreteBindingProjection.inputBindings
    : buildStandardInputBindings(options.selectedStandardArtifacts)
  const standardInputUploads = usesConcreteStandardInputFields
    ? concreteUploadProjection.standardInputUploads
    : await collectStandardInputUploads(options)
  const payload = buildTaskSubmissionPayload({
    flattenedSchema: options.flattenedSchema,
    formState: omitRecordKeys(options.formState, concreteBoundFieldKeys),
    uploadedFiles: omitRecordKeys(uploadedFiles, concreteBoundFieldKeys),
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
      inputBindings,
      standardInputUploads,
    }),
  }
}
