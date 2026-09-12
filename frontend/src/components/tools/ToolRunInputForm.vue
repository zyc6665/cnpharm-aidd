<template>
  <div class="tool-run-input-form">
    <StandardArtifactInputs
      v-if="showStandardArtifactInputs"
      :slots="standardInputSlots"
      :current-project-id="currentProjectId"
      :project-artifacts="projectArtifacts"
      :loading="standardArtifactsLoading"
      :selected-artifacts="selectedStandardArtifacts"
      :upload-lists="standardInputFileList"
      :tool-id="toolId"
      :tool-slug="toolSlug"
      @select-artifact="(slotName, versionId) => emit('select-standard-artifact', slotName, versionId)"
      @update-upload-list="(slotName, files) => emit('update-standard-upload-list', slotName, files)"
    />
    <ToolParameterForm
      v-if="schema"
      :schema="schema"
      :form-state="formState"
      :file-list="fileList"
      :selected-artifacts="selectedArtifacts"
      :allow-artifacts="allowArtifacts"
      :allow-uploads="allowUploads"
      :tool-id="toolId"
      :tool-slug="toolSlug"
      :preferred-group-id="preferredGroupId"
      :preferred-tool-slug="preferredToolSlug"
      :external-selection-path="externalSelectionPath"
      :hidden-field-keys="hiddenFieldKeys"
      :get-file-accept="getFileAccept"
      :is-file-field-satisfied="isFileFieldSatisfied"
      :required-message="requiredMessage"
      :min-length-message="minLengthMessage"
      :max-length-message="maxLengthMessage"
      @update:file-list="(key, files) => emit('update:fileList', key, files)"
      @update:selected-artifact="(key, artifact) => emit('update:selectedArtifact', key, artifact)"
    >
      <template #file-field-extra="slotProps">
        <slot name="file-field-extra" v-bind="slotProps" />
      </template>
    </ToolParameterForm>
  </div>
</template>

<script setup lang="ts">
  import type { UploadFile } from 'ant-design-vue'
  import type { TypedArtifact } from '@/types/artifacts'
  import type { ArtifactFile, SchemaProperty, ToolSchema } from '@/types/models'
  import type { WorkflowArtifactSelectionPath } from '@/workflow/artifact-hierarchy'
  import type { StandardArtifactInputSlot } from '@/domain/tools'
  import StandardArtifactInputs from './StandardArtifactInputs.vue'
  import ToolParameterForm from './ToolParameterForm.vue'

  withDefaults(
    defineProps<{
      schema?: ToolSchema
      formState: Record<string, unknown>
      fileList: Record<string, UploadFile[]>
      selectedArtifacts: Record<string, ArtifactFile | undefined>
      standardInputSlots: readonly StandardArtifactInputSlot[]
      showStandardArtifactInputs: boolean
      currentProjectId?: string
      projectArtifacts: readonly TypedArtifact[]
      standardArtifactsLoading?: boolean
      selectedStandardArtifacts: Record<string, TypedArtifact | undefined>
      standardInputFileList: Record<string, UploadFile[]>
      allowArtifacts?: boolean
      allowUploads?: boolean
      toolId?: string | null
      toolSlug?: string | null
      preferredGroupId?: string | null
      preferredToolSlug?: string | null
      externalSelectionPath?: WorkflowArtifactSelectionPath | null
      hiddenFieldKeys?: string[]
      getFileAccept?: (key: string, property: SchemaProperty) => string | undefined
      isFileFieldSatisfied?: (key: string, property: SchemaProperty) => boolean
      requiredMessage?: (title: string) => string
      minLengthMessage?: (min: number) => string
      maxLengthMessage?: (max: number) => string
    }>(),
    {
      schema: undefined,
      currentProjectId: undefined,
      standardArtifactsLoading: false,
      allowArtifacts: true,
      allowUploads: true,
      toolId: null,
      toolSlug: null,
      preferredGroupId: null,
      preferredToolSlug: null,
      externalSelectionPath: null,
      hiddenFieldKeys: () => [],
      getFileAccept: undefined,
      isFileFieldSatisfied: undefined,
      requiredMessage: undefined,
      minLengthMessage: undefined,
      maxLengthMessage: undefined,
    }
  )

  const emit = defineEmits<{
    'select-standard-artifact': [slotName: string, versionId: string | undefined]
    'update-standard-upload-list': [slotName: string, files: UploadFile[]]
    'update:fileList': [key: string, files: UploadFile[]]
    'update:selectedArtifact': [key: string, artifact: ArtifactFile | null]
  }>()
</script>
