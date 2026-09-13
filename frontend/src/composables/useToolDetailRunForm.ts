import { computed, nextTick, reactive, ref, unref, type Ref } from 'vue'
import type { UploadFile } from 'ant-design-vue'
import type { TypedArtifact } from '@/types/artifacts'
import type { ArtifactFile, FileUploadResponse, SchemaProperty, Tool } from '@/types/models'
import {
  buildStandardInputBindings,
  buildStandardInputBindingsFromFileFields,
  buildToolFormInitialState,
  getSdfConversionStatusText,
  missingRequiredStandardInputSlots,
  resolveToolRunInputSurface,
  shouldShowSdfToPdbConverter,
} from '@/domain/tools'

type MaybeRef<T> = T | Ref<T>

export interface ToolDetailRunFormOptions {
  tool: MaybeRef<Tool | null | undefined>
  isAuthenticated: MaybeRef<boolean>
  sdfConversion?: {
    convert: (file: File) => Promise<FileUploadResponse>
    getErrorMessage: (error: unknown) => string
    clearFieldValidation?: (key: string) => void
    revalidateField?: (key: string) => void | Promise<void>
    onInvalidFile?: () => void
    onSuccess?: () => void
  }
}

export function useToolDetailRunForm(options: ToolDetailRunFormOptions) {
  const taskName = ref('')
  const formState = reactive<Record<string, unknown>>({})
  const fileList = reactive<Record<string, UploadFile[]>>({})
  const selectedArtifacts = reactive<Record<string, ArtifactFile | undefined>>({})
  const selectedStandardArtifacts = reactive<Record<string, TypedArtifact | undefined>>({})
  const standardInputFileList = reactive<Record<string, UploadFile[]>>({})
  const exampleFiles = reactive<Record<string, FileUploadResponse | undefined>>({})
  const convertedFiles = reactive<Record<string, FileUploadResponse | undefined>>({})
  const sdfConversionLoading = reactive<Record<string, boolean>>({})
  const sdfConversionErrors = reactive<Record<string, string | undefined>>({})

  const inputSurface = computed(() => resolveToolRunInputSurface(unref(options.tool)))
  const flattenedSchema = computed(() => inputSurface.value.flattenedSchema)
  const standardInputSlots = computed(() => inputSurface.value.standardInputSlots)
  const standardInputFileFieldBindings = computed(
    () => inputSurface.value.standardInputFileFieldBindings
  )
  const showStandardArtifactInputs = computed(() => inputSurface.value.showStandardArtifactInputs)
  const concreteStandardInputBindingProjection = computed(() => {
    if (Object.keys(standardInputFileFieldBindings.value).length === 0) {
      return { inputBindings: {}, boundFieldKeys: [] }
    }

    return buildStandardInputBindingsFromFileFields({
      slots: standardInputSlots.value,
      fileFieldBindings: standardInputFileFieldBindings.value,
      selectedArtifacts,
    })
  })
  const selectedStandardArtifactRecord = computed<Record<string, TypedArtifact | undefined>>(() => {
    return Object.fromEntries(
      standardInputSlots.value.map(slot => [slot.name, selectedStandardArtifacts[slot.name]])
    )
  })
  const standardInputBindings = computed(() => {
    if (Object.keys(standardInputFileFieldBindings.value).length > 0) {
      return concreteStandardInputBindingProjection.value.inputBindings
    }

    return buildStandardInputBindings(selectedStandardArtifactRecord.value)
  })
  const missingRequiredStandardSlots = computed(() => {
    return missingRequiredStandardInputSlots({
      slots: standardInputSlots.value,
      inputBindings: standardInputBindings.value,
      hasUpload: hasStandardInputUploadSelection,
    })
  })
  const canSubmit = computed(() => {
    if (!unref(options.isAuthenticated)) {
      return false
    }
    if (Object.values(sdfConversionLoading).some(Boolean)) {
      return false
    }
    return missingRequiredStandardSlots.value.length === 0
  })

  function initializeFromSurface() {
    const initialState = buildToolFormInitialState({ flattenedSchema: flattenedSchema.value })
    replaceRecord(formState, initialState.formState)
    replaceRecord(fileList, emptyArrayRecord(initialState.fileFieldKeys))
    replaceRecord(selectedArtifacts, undefinedRecord(initialState.fileFieldKeys))
    replaceRecord(exampleFiles, undefinedRecord(initialState.fileFieldKeys))
    replaceRecord(convertedFiles, undefinedRecord(initialState.fileFieldKeys))
    replaceRecord(sdfConversionLoading, Object.fromEntries(initialState.fileFieldKeys.map(key => [key, false])))
    replaceRecord(sdfConversionErrors, undefinedRecord(initialState.fileFieldKeys))
    replaceRecord(
      selectedStandardArtifacts,
      undefinedRecord(standardInputSlots.value.map(slot => slot.name))
    )
    replaceRecord(
      standardInputFileList,
      emptyArrayRecord(standardInputSlots.value.map(slot => slot.name))
    )
  }

  function reset() {
    taskName.value = ''
    initializeFromSurface()
  }

  function selectStandardArtifact(
    slotName: string,
    versionId: string | undefined,
    projectArtifacts: readonly TypedArtifact[],
  ) {
    selectedStandardArtifacts[slotName] = versionId
      ? projectArtifacts.find(artifact => artifact.latest_version.id === versionId)
      : undefined
    if (selectedStandardArtifacts[slotName]) {
      standardInputFileList[slotName] = []
    }
  }

  function updateStandardInputFileList(slotName: string, files: UploadFile[]) {
    standardInputFileList[slotName] = files
    if (files.length > 0) {
      selectedStandardArtifacts[slotName] = undefined
    }
  }

  function handleFileListChange(key: string, files: UploadFile[]) {
    fileList[key] = files
    if (files.length > 0) {
      const uploadedFile = files[0]
      const rawFile = uploadedFile?.originFileObj as File | undefined
      const filename = rawFile?.name || uploadedFile?.name || ''
      if (showSdfToPdbConverter(key) && rawFile && filename.toLowerCase().endsWith('.sdf')) {
        fileList[key] = []
        formState[key] = undefined
        options.sdfConversion?.clearFieldValidation?.(key)
        void convertSdfToPdbField(key, rawFile)
        return
      }

      selectedArtifacts[key] = undefined
      exampleFiles[key] = undefined
      convertedFiles[key] = undefined
      sdfConversionErrors[key] = undefined
      formState[key] = uploadedFile?.uid ?? uploadedFile?.name
      options.sdfConversion?.clearFieldValidation?.(key)
      return
    }

    convertedFiles[key] = undefined
    sdfConversionErrors[key] = undefined
    formState[key] = undefined
  }

  function handleArtifactSelection(key: string, artifact: ArtifactFile | null) {
    selectedArtifacts[key] = artifact ?? undefined
    if (artifact) {
      fileList[key] = []
      exampleFiles[key] = undefined
      convertedFiles[key] = undefined
      sdfConversionErrors[key] = undefined
      formState[key] = artifact.id
      options.sdfConversion?.clearFieldValidation?.(key)
    } else {
      formState[key] = undefined
    }
  }

  function isFileFieldSatisfied(key: string, _prop?: SchemaProperty): boolean {
    return Boolean(
      sdfConversionLoading[key] ||
      formState[key] ||
      fileList[key]?.length ||
      selectedArtifacts[key] ||
      exampleFiles[key] ||
      convertedFiles[key]
    )
  }

  function clearExampleFile(key: string) {
    exampleFiles[key] = undefined
    formState[key] = undefined
  }

  function clearConvertedFile(key: string) {
    convertedFiles[key] = undefined
    fileList[key] = []
    formState[key] = undefined
    sdfConversionErrors[key] = undefined
    void nextTick().then(() => options.sdfConversion?.revalidateField?.(key))
  }

  function showSdfToPdbConverter(key: string) {
    return shouldShowSdfToPdbConverter(unref(options.tool)?.slug, key)
  }

  function sdfConversionStatusText(key: string) {
    return getSdfConversionStatusText({
      error: sdfConversionErrors[key],
      loading: sdfConversionLoading[key],
      convertedFilename: convertedFiles[key]?.filename,
    })
  }

  async function convertSdfToPdbField(key: string, file: File) {
    if (!file.name.toLowerCase().endsWith('.sdf')) {
      options.sdfConversion?.onInvalidFile?.()
      return
    }
    if (!options.sdfConversion) {
      return
    }

    sdfConversionLoading[key] = true
    sdfConversionErrors[key] = undefined
    options.sdfConversion.clearFieldValidation?.(key)
    try {
      const converted = await options.sdfConversion.convert(file)
      convertedFiles[key] = converted
      fileList[key] = [createConvertedUploadFile(converted)]
      selectedArtifacts[key] = undefined
      exampleFiles[key] = undefined
      formState[key] = converted.id
      await nextTick()
      options.sdfConversion.clearFieldValidation?.(key)
      options.sdfConversion.onSuccess?.()
    } catch (error) {
      convertedFiles[key] = undefined
      fileList[key] = []
      formState[key] = undefined
      sdfConversionErrors[key] = options.sdfConversion.getErrorMessage(error)
    } finally {
      sdfConversionLoading[key] = false
    }
  }

  function createSdfUploadBefore(key: string) {
    return (file: File) => {
      void convertSdfToPdbField(key, file)
      return false
    }
  }

  return {
    taskName,
    formState,
    fileList,
    selectedArtifacts,
    selectedStandardArtifacts,
    standardInputFileList,
    exampleFiles,
    convertedFiles,
    sdfConversionLoading,
    sdfConversionErrors,
    inputSurface,
    flattenedSchema,
    standardInputSlots,
    standardInputFileFieldBindings,
    showStandardArtifactInputs,
    standardInputBindings,
    missingRequiredStandardSlots,
    canSubmit,
    initializeFromSurface,
    reset,
    selectStandardArtifact,
    updateStandardInputFileList,
    handleFileListChange,
    handleArtifactSelection,
    isFileFieldSatisfied,
    clearExampleFile,
    clearConvertedFile,
    showSdfToPdbConverter,
    sdfConversionStatusText,
    convertSdfToPdbField,
    createSdfUploadBefore,
  }

  function hasConcreteStandardInputUploadSelection(slotName: string) {
    const fieldKey = standardInputFileFieldBindings.value[slotName]
    if (!fieldKey || selectedArtifacts[fieldKey]?.artifact_version_id?.trim()) {
      return false
    }

    return Boolean(
      fileList[fieldKey]?.length ||
      exampleFiles[fieldKey] ||
      convertedFiles[fieldKey] ||
      selectedArtifacts[fieldKey]?.id
    )
  }

  function hasStandardInputUploadSelection(slotName: string) {
    if (Object.keys(standardInputFileFieldBindings.value).length > 0) {
      return hasConcreteStandardInputUploadSelection(slotName)
    }

    return Boolean(standardInputFileList[slotName]?.length)
  }
}

function replaceRecord<T>(target: Record<string, T>, next: Record<string, T>) {
  for (const key of Object.keys(target)) {
    delete target[key]
  }
  for (const [key, value] of Object.entries(next)) {
    target[key] = value as T
  }
}

function emptyArrayRecord(keys: readonly string[]): Record<string, UploadFile[]> {
  return Object.fromEntries(keys.map(key => [key, []]))
}

function undefinedRecord<T = undefined>(keys: readonly string[]): Record<string, T | undefined> {
  return Object.fromEntries(keys.map(key => [key, undefined]))
}

function createConvertedUploadFile(file: FileUploadResponse): UploadFile {
  return {
    uid: `converted-${file.id}`,
    name: file.filename,
    status: 'done',
    url: `/api/v1/files/${file.id}/download`,
  }
}
