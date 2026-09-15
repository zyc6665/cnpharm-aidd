import type { UploadFile } from 'ant-design-vue'
import type { TypedArtifact } from '@/types/artifacts'
import type { ArtifactFile, FileUploadResponse, ToolSchema } from '@/types/models'
import { buildToolFormInitialState } from './detail-schema'
import type { StandardArtifactInputSlot } from './standard-artifact-inputs'

export interface BuildToolRunFormStateOptions {
  flattenedSchema?: ToolSchema
  standardInputSlots: readonly StandardArtifactInputSlot[]
  draft?: Record<string, unknown>
}

export interface ToolRunFormState {
  formState: Record<string, unknown>
  fileList: Record<string, UploadFile[]>
  selectedArtifacts: Record<string, ArtifactFile | undefined>
  selectedStandardArtifacts: Record<string, TypedArtifact | undefined>
  standardInputFileList: Record<string, UploadFile[]>
  exampleFiles: Record<string, FileUploadResponse | undefined>
  convertedFiles: Record<string, FileUploadResponse | undefined>
  sdfConversionLoading: Record<string, boolean>
  sdfConversionErrors: Record<string, string | undefined>
}

function emptyArrayRecord<T>(keys: readonly string[]): Record<string, T[]> {
  return Object.fromEntries(keys.map(key => [key, []]))
}

function undefinedRecord<T>(keys: readonly string[]): Record<string, T | undefined> {
  return Object.fromEntries(keys.map(key => [key, undefined]))
}

export function buildToolRunFormState(
  options: BuildToolRunFormStateOptions,
): ToolRunFormState {
  const initialState = buildToolFormInitialState({
    flattenedSchema: options.flattenedSchema,
    draft: options.draft,
  })
  const fileFieldKeys = initialState.fileFieldKeys
  const standardInputSlotNames = options.standardInputSlots.map(slot => slot.name)

  return {
    formState: initialState.formState,
    fileList: emptyArrayRecord<UploadFile>(fileFieldKeys),
    selectedArtifacts: undefinedRecord<ArtifactFile>(fileFieldKeys),
    selectedStandardArtifacts: undefinedRecord<TypedArtifact>(standardInputSlotNames),
    standardInputFileList: emptyArrayRecord<UploadFile>(standardInputSlotNames),
    exampleFiles: undefinedRecord<FileUploadResponse>(fileFieldKeys),
    convertedFiles: undefinedRecord<FileUploadResponse>(fileFieldKeys),
    sdfConversionLoading: Object.fromEntries(fileFieldKeys.map(key => [key, false])),
    sdfConversionErrors: undefinedRecord<string>(fileFieldKeys),
  }
}
