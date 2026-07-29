<template>
  <section class="workflow-node-run-panel">
    <a-alert
      v-if="!userStore.isAuthenticated"
      type="info"
      show-icon
      message="请登录后运行节点"
    />
    <a-spin :spinning="selectedToolLoading || submitting">
      <div v-if="selectedTool && selectedToolSlug" class="node-run-form">
        <div class="run-tool-summary">
          <span class="section-title">Run tool</span>
          <strong>{{ selectedTool.name }}</strong>
          <p v-if="selectedTool.description">{{ selectedTool.description }}</p>
        </div>

        <a-form ref="formRef" :model="formState" layout="vertical" @finish="handleSubmit">
          <a-form-item label="Task name">
            <a-input v-model:value="taskName" placeholder="Optional task name" />
          </a-form-item>

          <ToolParameterForm
            :schema="flattenedSchema"
            :form-state="formState"
            :file-list="fileList"
            :selected-artifacts="selectedArtifacts"
            :allow-artifacts="userStore.isLoggedIn"
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
              :loading="submitting"
              :disabled="submitDisabled"
              @click="submitWorkflowForm"
            >
              <PlayCircleOutlined />
              Run current node
            </a-button>
            <a-button @click="resetForm">Reset</a-button>
          </div>
        </a-form>
      </div>

      <a-empty
        v-else
        description="Select a real tool before running this node"
      />
    </a-spin>
  </section>
</template>

<script setup lang="ts">
  import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
  import type { FormInstance } from 'ant-design-vue/es/form'
  import type { UploadFile } from 'ant-design-vue'
  import { PlayCircleOutlined } from '@ant-design/icons-vue'
  import ToolParameterForm from '@/components/workflow/ToolParameterForm.vue'
  import { getTaskDetail, isTaskTerminalStatus } from '@/api/tasks'
  import { getToolDetail } from '@/api/tools'
  import { uploadFile } from '@/api/files'
  import { useArtifactsStore, useTasksStore, useUserStore, useWorkflowStore } from '@/stores'
  import type { ArtifactFile, Tool, ToolSchema } from '@/types/models'
  import {
    buildTaskSubmissionPayload,
    buildToolFormInitialState,
    flattenToolInputSchema,
    type UploadedToolFile
  } from '@/views/tools/detail-schema'
  import { toWorkflowTaskRef } from '@/workflow/task-state'
  import type { WorkflowNodeArtifactRecommendation } from '@/workflow/template-artifacts'

  interface WorkflowAvailableTool {
    id?: string
    slug: string
    name: string
    description?: string
  }

  const props = defineProps<{
    nodeId: string
    selectedToolSlug?: string | null
    availableTools?: WorkflowAvailableTool[]
    recommendedArtifacts?: WorkflowNodeArtifactRecommendation[]
  }>()

  const emit = defineEmits<{
    (event: 'task-submitted', taskId: string): void
  }>()

  const artifactsStore = useArtifactsStore()
  const tasksStore = useTasksStore()
  const userStore = useUserStore()
  const workflowStore = useWorkflowStore()

  const formRef = ref<FormInstance>()
  const selectedTool = ref<Tool | null>(null)
  const selectedToolLoading = ref(false)
  const submitting = ref(false)
  const taskName = ref('')
  const formState = reactive<Record<string, unknown>>({})
  const fileList = reactive<Record<string, UploadFile[]>>({})
  const selectedArtifacts = reactive<Record<string, ArtifactFile | undefined>>({})
  const autoBoundArtifacts = ref<ArtifactFile[]>([])
  let detailRequestToken = 0
  let pollTimer: number | null = null

  const selectedToolSummary = computed(() => {
    if (!props.selectedToolSlug) {
      return null
    }

    return props.availableTools?.find(tool => tool.slug === props.selectedToolSlug) ?? null
  })

  const inputSchema = computed<ToolSchema | undefined>(() => {
    const config = selectedTool.value?.current_version?.config
    if (config && typeof config === 'object' && 'input_schema' in config) {
      return config.input_schema as ToolSchema
    }
    return undefined
  })

  const executorType = computed<string | undefined>(() => {
    const config = selectedTool.value?.current_version?.config
    if (config && typeof config === 'object' && 'type' in config && typeof config.type === 'string') {
      return config.type
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

  const submitDisabled = computed(() => {
    return (
      submitting.value ||
      selectedToolLoading.value ||
      !userStore.isAuthenticated ||
      !selectedTool.value ||
      !props.selectedToolSlug
    )
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

  function resetForm() {
    formRef.value?.resetFields()
    taskName.value = ''
    workflowStore.setNodeFormDraft(props.nodeId, {})
    applyInitialFormState(true)
  }

  async function submitWorkflowForm() {
    if (submitDisabled.value) {
      return
    }

    await formRef.value?.validate()
    await handleSubmit()
  }

  function clearTaskPoll() {
    if (pollTimer !== null) {
      window.clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  async function pollTaskUntilTerminal(taskId: string) {
    clearTaskPoll()

    const poll = async () => {
      try {
        const response = await getTaskDetail(taskId)
        workflowStore.recordNodeTask(props.nodeId, toWorkflowTaskRef(response.data))

        if (isTaskTerminalStatus(response.data.status)) {
          clearTaskPoll()
          if (response.data.status === 'success') {
            await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
          }
          return
        }

        pollTimer = window.setTimeout(poll, 3000)
      } catch {
        pollTimer = window.setTimeout(poll, 5000)
      }
    }

    pollTimer = window.setTimeout(poll, 3000)
  }

  async function handleSubmit() {
    const toolId = selectedTool.value?.id
    if (!toolId) {
      return
    }

    submitting.value = true
    try {
      const uploadedFiles: Record<string, UploadedToolFile | undefined> = {}

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

      for (const [key, items] of Object.entries(fileList)) {
        const fileItem = items?.[0]
        if (!fileItem?.originFileObj) {
          continue
        }

        const response = await uploadFile(fileItem.originFileObj as File)
        uploadedFiles[key] = {
          fileId: response.data.id.toString(),
          filename: response.data.filename,
          downloadUrl: `/api/v1/files/${response.data.id}/download`
        }
      }

      const payload = buildTaskSubmissionPayload({
        flattenedSchema: flattenedSchema.value,
        formState,
        uploadedFiles,
        executorType: executorType.value
      })

      const task = await tasksStore.createTask({
        name: taskName.value.trim() || selectedTool.value?.name,
        tool_id: toolId,
        params: payload.params,
        file_ids: payload.fileIds.length > 0 ? payload.fileIds : undefined,
        priority: 'normal'
      })

      workflowStore.recordNodeTask(props.nodeId, toWorkflowTaskRef(task))
      emit('task-submitted', task.id)
      taskName.value = ''

      if (task.status === 'success') {
        await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
      } else {
        await pollTaskUntilTerminal(task.id)
      }
    } finally {
      submitting.value = false
    }
  }

  watch(
    () => props.selectedToolSlug,
    async () => {
      const requestToken = ++detailRequestToken
      const toolId = selectedToolSummary.value?.id
      taskName.value = ''

      if (!toolId) {
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

  onBeforeUnmount(() => {
    clearTaskPoll()
  })
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
