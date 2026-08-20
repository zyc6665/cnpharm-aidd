<template>
  <section class="workflow-node-run-panel">
    <a-alert
      v-if="!userStore.isAuthenticated"
      type="info"
      show-icon
      message="请登录后选择已保存产物"
    />
    <a-spin :spinning="selectedToolLoading">
      <div v-if="selectedTool && selectedToolSlug" class="node-run-form">
        <div class="run-tool-summary">
          <span class="section-title">{{ t('workflow.inspector.nodeParameters') }}</span>
          <strong>{{ selectedTool.name }}</strong>
          <p v-if="selectedTool.description">{{ selectedTool.description }}</p>
        </div>

        <a-form ref="formRef" :model="formState" layout="vertical">
          <ToolParameterForm
            :schema="flattenedSchema"
            :form-state="formState"
            :file-list="fileList"
            :selected-artifacts="selectedArtifacts"
            :allow-artifacts="userStore.isLoggedIn"
            :allow-uploads="true"
            :tool-id="selectedTool?.id"
            :tool-slug="selectedTool?.slug"
            :preferred-tool-slug="selectedTool?.slug"
            @update:file-list="handleFileListChange"
            @update:selected-artifact="handleArtifactSelection"
          />

          <div v-if="autoBoundArtifacts.length" class="auto-bound-artifacts">
            <a-tag v-for="artifact in autoBoundArtifacts" :key="artifact.id" color="blue">
              {{ artifact.filename }}
            </a-tag>
          </div>

          <div class="node-run-actions">
            <a-button
              type="primary"
              data-testid="run-current-node"
              :loading="submitting"
              :disabled="!selectedTool || !selectedToolSlug"
              @click="runCurrentNode"
            >
              运行当前节点
            </a-button>
            <a-button @click="resetForm">Reset</a-button>
          </div>
        </a-form>
      </div>

      <a-empty
        v-else
        description="Select a real tool before configuring this node"
      />
    </a-spin>
  </section>
</template>

<script setup lang="ts">
  import { computed, reactive, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import type { FormInstance } from 'ant-design-vue/es/form'
  import type { UploadFile } from 'ant-design-vue'
  import ToolParameterForm from '@/components/workflow/ToolParameterForm.vue'
  import { uploadFile } from '@/api/files'
  import { createTask } from '@/api/tasks'
  import { getToolDetail } from '@/api/tools'
  import { useUserStore, useWorkflowStore } from '@/stores'
  import type { ArtifactFile, Tool, ToolSchema } from '@/types/models'
  import {
    buildTaskSubmissionPayload,
    buildToolFormInitialState,
    flattenToolInputSchema
  } from '@/domain/tools'
  import type { WorkflowNodeArtifactRecommendation } from '@/workflow/canvas-artifacts'

  interface WorkflowAvailableTool {
    id?: string
    slug: string
    name: string
    description?: string
  }

  interface ContractArtifactInput {
    name: string
    type: string
    required?: boolean
  }

  const props = defineProps<{
    nodeId: string
    projectId?: string | null
    selectedToolSlug?: string | null
    availableTools?: WorkflowAvailableTool[]
    recommendedArtifacts?: WorkflowNodeArtifactRecommendation[]
  }>()

  const { t } = useI18n()
  const userStore = useUserStore()
  const workflowStore = useWorkflowStore()

  const formRef = ref<FormInstance>()
  const selectedTool = ref<Tool | null>(null)
  const selectedToolLoading = ref(false)
  const formState = reactive<Record<string, unknown>>({})
  const fileList = reactive<Record<string, UploadFile[]>>({})
  const selectedArtifacts = reactive<Record<string, ArtifactFile | undefined>>({})
  const autoBoundArtifacts = ref<ArtifactFile[]>([])
  const submitting = ref(false)
  let detailRequestToken = 0

  const selectedToolSummary = computed(() => {
    if (!props.selectedToolSlug) {
      return null
    }

    return props.availableTools?.find(tool => tool.slug === props.selectedToolSlug) ?? null
  })

  const contractArtifactInputs = computed<ContractArtifactInput[]>(() =>
    selectedTool.value?.contract?.artifacts?.inputs ?? []
  )

  const inputSchema = computed<ToolSchema | undefined>(() => {
    const config = selectedTool.value?.current_version?.config
    if (config && typeof config === 'object' && 'input_schema' in config) {
      const schema = config.input_schema as ToolSchema
      if (schema?.properties && Object.keys(schema.properties).length > 0) {
        return schema
      }
    }

    if (contractArtifactInputs.value.length > 0) {
      return buildArtifactInputSchema(contractArtifactInputs.value)
    }

    return undefined
  })

  const executorType = computed(() => {
    const contractExecutorType = selectedTool.value?.contract?.executor?.type
    if (contractExecutorType) {
      return contractExecutorType
    }

    const config = selectedTool.value?.current_version?.config
    if (config && typeof config === 'object' && 'type' in config) {
      return String(config.type)
    }

    return undefined
  })

  const flattenedSchema = computed<ToolSchema>(() => {
    return flattenToolInputSchema(inputSchema.value) ?? {
      type: 'object',
      properties: {},
      required: []
    }
  })

  function replaceFormState(nextState: Record<string, unknown>) {
    for (const key of Object.keys(formState)) {
      delete formState[key]
    }

    for (const [key, value] of Object.entries(nextState)) {
      formState[key] = value
    }
  }

  function replaceFileList(nextKeys: string[]) {
    for (const key of Object.keys(fileList)) {
      delete fileList[key]
    }

    for (const key of nextKeys) {
      fileList[key] = []
    }
  }

  function replaceSelectedArtifacts(nextKeys: string[]) {
    for (const key of Object.keys(selectedArtifacts)) {
      delete selectedArtifacts[key]
    }

    for (const key of nextKeys) {
      selectedArtifacts[key] = undefined
    }
  }

  function applyRecommendedArtifacts(fileFieldKeys: string[]) {
    autoBoundArtifacts.value = []
    const availableArtifacts = (props.recommendedArtifacts ?? [])
      .map(recommendation => recommendation.artifact)
      .filter((artifact): artifact is ArtifactFile => Boolean(artifact))

    if (!availableArtifacts.length || !fileFieldKeys.length) {
      return
    }

    const firstFileKey = fileFieldKeys[0]!
    if (formState[firstFileKey] || selectedArtifacts[firstFileKey]) {
      return
    }

    const artifact = availableArtifacts[0]!
    selectedArtifacts[firstFileKey] = artifact
    formState[firstFileKey] = artifact.id
    autoBoundArtifacts.value = [artifact]
  }

  function applyInitialFormState(resetDraft = false) {
    const draft = resetDraft ? {} : workflowStore.nodeFormDrafts[props.nodeId]
    const initialState = buildToolFormInitialState({
      flattenedSchema: flattenedSchema.value,
      draft
    })

    replaceFormState(initialState.formState)
    replaceFileList(initialState.fileFieldKeys)
    replaceSelectedArtifacts(initialState.fileFieldKeys)
    applyRecommendedArtifacts(initialState.fileFieldKeys)
  }

  function handleFileListChange(key: string, files: UploadFile[]) {
    fileList[key] = files
    selectedArtifacts[key] = undefined
    formState[key] = files[0]?.uid ?? files[0]?.name
  }

  function handleArtifactSelection(key: string, artifact: ArtifactFile | null) {
    selectedArtifacts[key] = artifact ?? undefined
    formState[key] = artifact?.id
    if (artifact) {
      fileList[key] = []
    }
  }

  function buildArtifactInputSchema(artifactInputs: ContractArtifactInput[]): ToolSchema {
    const properties: ToolSchema['properties'] = {}
    const required: string[] = []

    for (const input of artifactInputs) {
      properties[input.name] = {
        type: 'file',
        title: input.name,
        description: `标准产物类型：${input.type}`,
        format: 'file'
      }

      if (input.required) {
        required.push(input.name)
      }
    }

    return {
      type: 'object',
      properties,
      required
    }
  }

  async function resolveUploadedFiles() {
    const uploadedFiles: Record<string, { fileId: string; filename: string; downloadUrl: string } | undefined> = {}

    for (const [key, artifact] of Object.entries(selectedArtifacts)) {
      if (!artifact) {
        continue
      }

      uploadedFiles[key] = {
        fileId: artifact.id,
        filename: artifact.filename,
        downloadUrl: artifact.download_url
      }
    }

    for (const [key, files] of Object.entries(fileList)) {
      const file = files[0]?.originFileObj as File | undefined
      if (!file) {
        continue
      }

      const response = await uploadFile(file)
      const fileId = String(response.data.id)
      uploadedFiles[key] = {
        fileId,
        filename: response.data.filename,
        downloadUrl: response.data.url ?? `/api/v1/files/${fileId}/download`
      }
    }

    return uploadedFiles
  }

  function withBuiltinInputs(
    params: Record<string, unknown>,
    uploadedFiles: Record<string, { fileId: string; filename: string; downloadUrl: string } | undefined>
  ) {
    if (executorType.value !== 'builtin' || contractArtifactInputs.value.length === 0) {
      return params
    }

    const builtinInputs: Record<string, string> = {}
    const nextParams = { ...params }
    for (const input of contractArtifactInputs.value) {
      delete nextParams[input.name]

      const uploadedFile = uploadedFiles[input.name]
      if (uploadedFile?.fileId) {
        builtinInputs[input.type] = uploadedFile.fileId
      }
    }

    if (Object.keys(builtinInputs).length === 0) {
      return params
    }

    return {
      ...nextParams,
      builtin_inputs: builtinInputs
    }
  }

  async function runCurrentNode() {
    if (!selectedTool.value || !props.selectedToolSlug) {
      return
    }

    submitting.value = true
    try {
      const uploadedFiles = await resolveUploadedFiles()
      const payload = buildTaskSubmissionPayload({
        flattenedSchema: flattenedSchema.value,
        formState,
        uploadedFiles,
        executorType: executorType.value
      })
      const params = withBuiltinInputs(payload.params, uploadedFiles)
      const response = await createTask({
        name: `${selectedTool.value.name} · ${props.nodeId}`,
        tool_id: selectedTool.value.id,
        project_id: props.projectId?.trim() || undefined,
        params,
        file_ids: payload.fileIds.length > 0 ? payload.fileIds : undefined
      })

      workflowStore.recordNodeTask(props.nodeId, response.data)
      workflowStore.recordTask(props.selectedToolSlug, response.data)
    } finally {
      submitting.value = false
    }
  }

  function resetForm() {
    formRef.value?.resetFields()
    workflowStore.setNodeFormDraft(props.nodeId, {})
    applyInitialFormState(true)
  }

  watch(
    () => [props.selectedToolSlug, selectedToolSummary.value?.id ?? null] as const,
    async ([selectedToolSlug, toolId]) => {
      const requestToken = ++detailRequestToken

      if (!selectedToolSlug || !toolId) {
        selectedTool.value = null
        selectedToolLoading.value = false
        replaceFormState({})
        replaceFileList([])
        replaceSelectedArtifacts([])
        return
      }

      selectedTool.value = null
      selectedToolLoading.value = true
      try {
        const response = await getToolDetail(toolId)
        if (requestToken === detailRequestToken) {
          selectedTool.value = response.data
        }
      } finally {
        if (requestToken === detailRequestToken) {
          selectedToolLoading.value = false
        }
      }
    },
    { immediate: true }
  )

  watch(
    () => [props.nodeId, props.selectedToolSlug, flattenedSchema.value] as const,
    () => applyInitialFormState(),
    { immediate: true }
  )

  watch(
    formState,
    () => {
      workflowStore.setNodeFormDraft(props.nodeId, { ...formState })
    },
    { deep: true }
  )
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-node-run-panel {
    display: grid;
    gap: @spacing-md;
  }

  .node-run-form {
    display: grid;
    gap: @spacing-md;
  }

  .run-tool-summary {
    display: grid;
    gap: 4px;
    padding: @spacing-sm;
    border: 1px solid @border-color-hover;
    border-radius: @border-radius-sm;
    background: @bg-elevated;
  }

  .run-tool-summary strong {
    color: @text-color-light-primary;
    font-size: @font-size-sm;
  }

  .run-tool-summary p {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: 1.45;
  }

  .section-title {
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: 800;
    letter-spacing: 0;
    text-transform: uppercase;
  }

  .code-input {
    font-family: @font-family-mono;
  }

  .auto-bound-artifacts {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-xs;
    margin-bottom: @spacing-sm;
  }

  .node-run-actions {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-sm;
  }

  .node-run-actions :deep(.ant-btn) {
    min-width: 120px;
  }
</style>
