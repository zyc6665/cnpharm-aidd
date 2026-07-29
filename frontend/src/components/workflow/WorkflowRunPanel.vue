<template>
  <section class="workflow-column tools-column">
    <div class="column-card tool-lab-panel">
      <h2 class="column-title">{{ t('workflow.columns.tools') }}</h2>
      <p class="column-subtitle">{{ t('workflow.columns.toolsHint') }}</p>

      <div v-if="group?.tools.length" class="tool-select-panel">
        <div class="tool-select-meta">
          <span class="tool-select-label">{{ t('workflow.currentTool.label') }}</span>
          <strong class="tool-select-title">{{ selectedToolSummary?.name ?? group.tools[0]?.name }}</strong>
          <p v-if="selectedToolDescription" class="tool-select-desc">{{ selectedToolDescription }}</p>
        </div>
        <div class="tool-select-control">
          <a-select
            class="tool-select"
            size="large"
            :value="selectedToolSlug ?? undefined"
            :placeholder="t('workflow.currentTool.empty')"
            @change="handleToolSelectChange"
          >
            <a-select-option
              v-for="toolOption in group.tools"
              :key="toolOption.slug"
              :value="toolOption.slug"
            >
              <div class="tool-select-option">
                <span class="tool-select-option-name">{{ toolOption.name }}</span>
                <span class="tool-select-option-tags">
                  <a-tag v-if="toolOption.is_recommended" color="gold">
                    {{ t('workflow.toolStatus.recommended') }}
                  </a-tag>
                  <a-tag color="green">{{ t('workflow.toolStatus.available') }}</a-tag>
                </span>
              </div>
            </a-select-option>
          </a-select>
        </div>
      </div>

      <a-alert
        v-else-if="group"
        type="info"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #message>
          {{ t('workflow.groups.noTools') }}
        </template>
      </a-alert>

      <a-alert
        v-if="!userStore.isAuthenticated"
        type="info"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #message>
          {{ t('auth.loginRequired') }}
        </template>
      </a-alert>
      <a-spin :spinning="selectedToolLoading || submitting">
        <div v-if="selectedTool && selectedToolSlug && group" class="form-shell">
          <a-form ref="formRef" :model="formState" layout="vertical" @finish="handleSubmit">
            <a-form-item :label="t('tasks.name')">
              <a-input
                v-model:value="taskName"
                :placeholder="t('tasks.namePlaceholder')"
              />
            </a-form-item>
            <ToolParameterForm
              :schema="flattenedSchema"
              :form-state="formState"
              :file-list="fileList"
              :selected-artifacts="selectedArtifacts"
              :allow-artifacts="userStore.isLoggedIn"
              :preferred-group-id="group?.id"
              :preferred-tool-slug="selectedTool?.slug ?? selectedToolSummary?.slug"
              :tool-id="selectedTool?.id ?? selectedToolSummary?.id"
              :tool-slug="selectedTool?.slug ?? selectedToolSummary?.slug"
              :external-selection-path="artifactSelectionPath"
              @update:file-list="handleFileListChange"
              @update:selected-artifact="handleArtifactSelection"
            />

            <a-form-item>
              <div class="form-action-bar">
                <div class="form-action-copy">
                  <strong class="form-action-title">{{ t('workflow.currentTool.runAction') }}</strong>
                  <p class="form-action-desc">{{ t('workflow.currentTool.runHint') }}</p>
                </div>
                <a-space class="form-action-buttons" wrap>
                  <a-button
                    type="primary"
                    size="large"
                    @click="submitWorkflowForm"
                    :loading="submitting"
                    :disabled="submitDisabled"
                  >
                    <PlayCircleOutlined />
                    {{ t('tools.runTool') }}
                  </a-button>
                  <a-button size="large" @click="resetForm">
                    {{ t('common.reset') }}
                  </a-button>
                  <a-button size="large" @click="openToolDetail">
                    {{ t('workflow.currentTool.viewDetail') }}
                  </a-button>
                  <a-button v-if="activeTask" size="large" @click="openTaskDetail">
                    {{ t('workflow.currentTool.viewTask') }}
                  </a-button>
                </a-space>
              </div>
            </a-form-item>
          </a-form>

          <a-collapse
            v-model:activeKey="resultPanelActiveKeys"
            class="result-collapse"
            :bordered="false"
          >
            <a-collapse-panel key="result">
              <template #header>
                <div class="result-collapse-header">
                  <div class="result-collapse-copy">
                    <span class="result-collapse-label">{{ t('tasks.result') }}</span>
                    <strong class="result-collapse-title">{{ t('workflow.results.title') }}</strong>
                    <p class="result-collapse-desc">{{ resultPanelHint }}</p>
                  </div>
                  <a-tag v-if="activeTask" :color="taskStatusColor(activeTask.status)">
                    {{ activeTask.status }}
                  </a-tag>
                </div>
              </template>
              <WorkflowTaskResultPanel
                :task-id="resolvedResultTaskId"
                :task-summary="resultTaskSummary"
              />
            </a-collapse-panel>
          </a-collapse>
        </div>

        <a-empty
          v-else-if="group && group.tools.length > 0"
          :description="t('workflow.currentTool.empty')"
        />
        <a-empty
          v-else
          :description="t('workflow.groups.empty')"
        />
      </a-spin>
    </div>
  </section>
</template>

<script setup lang="ts">
  import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
  import { useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import type { FormInstance } from 'ant-design-vue/es/form'
  import type { UploadFile } from 'ant-design-vue'
  import { PlayCircleOutlined } from '@ant-design/icons-vue'
  import ToolParameterForm from '@/components/workflow/ToolParameterForm.vue'
  import WorkflowTaskResultPanel from '@/components/workflow/WorkflowTaskResultPanel.vue'
  import { getTaskDetail, isTaskTerminalStatus } from '@/api/tasks'
  import { getToolDetail } from '@/api/tools'
  import { uploadFile } from '@/api/files'
  import { useArtifactsStore, useTasksStore, useUserStore, useWorkflowStore } from '@/stores'
  import type {
    ArtifactFile,
    Tool,
    ToolPreparedSubmissionPayload,
    ToolSchema,
    WorkbenchGroup
  } from '@/types/models'
  import {
    buildTaskSubmissionPayload,
    buildToolFormInitialState,
    flattenToolInputSchema,
    type UploadedToolFile
  } from '@/views/tools/detail-schema'
  import { toWorkflowTaskRef } from '@/workflow/task-state'
  import type { WorkflowTaskRef } from '@/workflow/artifact-types'
  import type { WorkflowArtifactSelectionPath } from '../../workflow/artifact-hierarchy.ts'

  const props = defineProps<{
    group?: WorkbenchGroup | null
    selectedToolSlug?: string | null
    artifactSelectionPath?: WorkflowArtifactSelectionPath | null
    resultTaskId?: string | null
    resultTaskSummary?: WorkflowTaskRef | null
  }>()

  const emit = defineEmits<{
    selectTool: [toolSlug: string]
    resultTaskChange: [taskId: string]
  }>()

  const { t } = useI18n()
  const router = useRouter()
  const artifactsStore = useArtifactsStore()
  const tasksStore = useTasksStore()
  const userStore = useUserStore()
  const workflowStore = useWorkflowStore()

  const formRef = ref<FormInstance>()
  const selectedTool = ref<Tool | null>(null)
  const selectedToolLoading = ref(false)
  const submitting = ref(false)
  const taskName = ref('')
  const resultPanelActiveKeys = ref<string[]>([])
  const formState = reactive<Record<string, unknown>>({})
  const fileList = reactive<Record<string, UploadFile[]>>({})
  const selectedArtifacts = reactive<Record<string, ArtifactFile | undefined>>({})
  let detailRequestToken = 0
  let pollTimer: number | null = null

  const selectedToolSummary = computed(() => {
    return props.group?.tools.find((tool) => tool.slug === props.selectedToolSlug) ?? null
  })

  const selectedToolDescription = computed(() => {
    return selectedTool.value?.description || selectedToolSummary.value?.description || t('workflow.currentTool.descriptionFallback')
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

  const activeTask = computed(() => {
    if (!props.selectedToolSlug) {
      return null
    }

    return workflowStore.taskByTool[props.selectedToolSlug] ?? null
  })

  const resolvedResultTaskId = computed(() => {
    return props.resultTaskId ?? activeTask.value?.id ?? null
  })

  const resultTaskSummary = computed<WorkflowTaskRef | null>(() => {
    if (!resolvedResultTaskId.value) {
      return null
    }

    if (props.resultTaskSummary?.id === resolvedResultTaskId.value) {
      return props.resultTaskSummary
    }

    if (activeTask.value?.id === resolvedResultTaskId.value) {
      return activeTask.value
    }

    return null
  })

  const resultPanelHint = computed(() => {
    if (!activeTask.value) {
      return t('workflow.results.emptyHint')
    }

    const taskName = activeTask.value.name || t('workflow.results.latestTask')
    return `${taskName} · ${activeTask.value.progress}%`
  })

  const submitDisabled = computed(() => {
    if (submitting.value || selectedToolLoading.value) {
      return true
    }

    if (!userStore.isAuthenticated) {
      return true
    }

    return !selectedTool.value || !props.selectedToolSlug
  })

  function taskStatusColor(status: string): string {
    const colorMap: Record<string, string> = {
      pending: 'gold',
      running: 'processing',
      success: 'green',
      failure: 'red',
      canceled: 'default'
    }

    return colorMap[status] ?? 'default'
  }

  function selectTool(toolSlug: string) {
    if (props.selectedToolSlug === toolSlug) {
      return
    }

    emit('selectTool', toolSlug)
  }

  function handleToolSelectChange(value: string) {
    selectTool(value)
  }

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

  function applyInitialFormState(toolSlug: string, schema: ToolSchema, resetDraft = false) {
    const draft = resetDraft ? {} : workflowStore.toolFormDrafts[toolSlug]
    const initialState = buildToolFormInitialState({
      flattenedSchema: schema,
      draft
    })

    replaceFormState(initialState.formState)
    replaceFileList(initialState.fileFieldKeys)
    replaceSelectedArtifacts(initialState.fileFieldKeys)
  }

  function handleFileListChange(key: string, files: UploadFile[]) {
    fileList[key] = files
  }

  function handleArtifactSelection(key: string, artifact: ArtifactFile | null) {
    selectedArtifacts[key] = artifact ?? undefined
  }

  function resetForm() {
    formRef.value?.resetFields()
    taskName.value = ''

    if (props.selectedToolSlug) {
      workflowStore.clearToolFormDraft(props.selectedToolSlug)
      applyInitialFormState(props.selectedToolSlug, flattenedSchema.value, true)
    }
  }

  async function refreshArtifacts() {
    if (!userStore.isLoggedIn) {
      return
    }

    await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
  }

  async function submitWorkflowForm() {
    if (submitDisabled.value) {
      return
    }

    await formRef.value?.validate()
    await handleSubmit()
  }

  function openTaskDetail() {
    if (!activeTask.value?.id) {
      return
    }

    router.push(`/tasks/${activeTask.value.id}`)
  }

  function openToolDetail() {
    if (!selectedTool.value?.id) {
      return
    }

    router.push(`/tools/${selectedTool.value.id}`)
  }

  function clearTaskPoll() {
    if (pollTimer !== null) {
      window.clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  async function pollTaskUntilTerminal(taskId: string, toolSlug: string) {
    clearTaskPoll()

    const poll = async () => {
      try {
        const response = await getTaskDetail(taskId)
        workflowStore.recordTask(toolSlug, toWorkflowTaskRef(response.data))

        if (isTaskTerminalStatus(response.data.status)) {
          clearTaskPoll()
          if (response.data.status === 'success') {
            await refreshArtifacts()
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
    const toolSlug = props.selectedToolSlug

    if (!toolId || !toolSlug) {
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

      const preparedPayload: ToolPreparedSubmissionPayload = {
        params: payload.params,
        file_ids: payload.fileIds.length > 0 ? payload.fileIds : undefined
      }

      const task = await tasksStore.createTask({
        name: taskName.value.trim() || undefined,
        tool_id: toolId,
        ...preparedPayload
      })

      workflowStore.recordTask(toolSlug, toWorkflowTaskRef(task))
      emit('resultTaskChange', task.id)
      resultPanelActiveKeys.value = ['result']
      taskName.value = ''
      if (task.status === 'success') {
        await refreshArtifacts()
      } else {
        await pollTaskUntilTerminal(task.id, toolSlug)
      }
    } finally {
      submitting.value = false
    }
  }

  watch(
    () => props.selectedToolSlug,
    async () => {
      taskName.value = ''
      const requestToken = ++detailRequestToken
      const toolId = selectedToolSummary.value?.id

      if (!toolId) {
        selectedToolLoading.value = false
        selectedTool.value = null
        replaceFormState({})
        replaceFileList([])
        replaceSelectedArtifacts([])
        return
      }

      selectedToolLoading.value = true
      selectedTool.value = null

      try {
        const response = await getToolDetail(toolId)
        if (requestToken !== detailRequestToken) {
          return
        }

        selectedTool.value = response.data
      } finally {
        if (requestToken === detailRequestToken) {
          selectedToolLoading.value = false
        }
      }
    },
    { immediate: true }
  )

  watch(
    () => [props.selectedToolSlug, flattenedSchema.value] as const,
    ([toolSlug, schema]) => {
      if (!toolSlug) {
        replaceFormState({})
        replaceFileList([])
        replaceSelectedArtifacts([])
        return
      }

      applyInitialFormState(toolSlug, schema)
    },
    { immediate: true }
  )

  watch(
    formState,
    () => {
      if (!props.selectedToolSlug) {
        return
      }

      workflowStore.setToolFormDraft(props.selectedToolSlug, { ...formState })
    },
    { deep: true }
  )

  onBeforeUnmount(() => {
    clearTaskPoll()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-column {
    min-width: 0;
  }

  .tools-column {
    @media (max-width: @screen-xl) {
      grid-column: span 2;
    }

    @media (max-width: @screen-md) {
      grid-column: auto;
    }
  }

  .column-card {
    .card();
    height: 100%;
    border: 1px solid rgba(205, 217, 235, 0.9);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(246, 250, 255, 0.99) 100%);
    box-shadow: 0 22px 44px rgb(15 23 42 / 6%);
  }

  .tool-lab-panel {
    position: relative;
    overflow: hidden;

    &::before {
      content: '';
      position: absolute;
      inset: 0 0 auto;
      height: 180px;
      background: linear-gradient(135deg, rgba(13, 110, 253, 0.08) 0%, rgba(111, 66, 193, 0.08) 100%);
      pointer-events: none;
    }

    > * {
      position: relative;
      z-index: 1;
    }
  }

  .column-title {
    font-size: @font-size-xl;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-xs;
  }

  .column-subtitle {
    color: @text-color-light-secondary;
    margin-bottom: @spacing-lg;
  }

  .form-action-title {
    display: block;
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
  }

  .form-action-desc {
    margin: @spacing-xs 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
  }

  .tool-select-panel {
    display: grid;
    grid-template-columns: minmax(240px, 1fr) minmax(260px, 0.8fr);
    gap: @spacing-md;
    align-items: start;
    margin-bottom: @spacing-lg;
    padding: @spacing-md;
    border: 1px solid rgba(210, 221, 236, 0.9);
    border-radius: @border-radius-lg;
    background: linear-gradient(180deg, @bg-elevated 0%, @accent-color-light 100%);
    box-shadow: 0 16px 30px rgb(15 23 42 / 4%);
  }

  .tool-select-meta {
    min-width: 0;
  }

  .tool-select-label {
    display: block;
    margin-bottom: @spacing-xs;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .tool-select-title {
    display: block;
    color: @text-color-light-primary;
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
    overflow-wrap: anywhere;
  }

  .tool-select-desc {
    margin: @spacing-xs 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
  }

  .tool-select-control {
    display: flex;
    min-width: 0;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .tool-select {
    width: 100%;
  }

  .tool-select-option {
    display: flex;
    justify-content: space-between;
    gap: @spacing-sm;
    align-items: center;
  }

  .tool-select-option-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .tool-select-option-tags {
    display: inline-flex;
    flex: none;
    gap: @spacing-xs;
  }

  .form-shell {
    display: flex;
    flex-direction: column;
    gap: @spacing-lg;
  }

  .form-action-bar,
  .result-collapse {
    border: 1px solid rgba(210, 221, 236, 0.9);
    border-radius: @border-radius-lg;
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 251, 255, 0.98) 100%);
    box-shadow: 0 16px 30px rgb(15 23 42 / 4%);
  }

  .form-action-bar {
    display: flex;
    justify-content: space-between;
    gap: @spacing-md;
    align-items: flex-start;
    flex-wrap: wrap;
    padding: @spacing-md;
  }

  .form-action-copy {
    min-width: 0;
    flex: 1;
  }

  .form-action-title {
    overflow-wrap: anywhere;
  }

  .form-action-buttons {
    justify-content: flex-end;
  }

  .form-action-buttons :deep(.ant-space-item) {
    display: flex;
  }

  .result-collapse {
    overflow: hidden;

    :deep(.ant-collapse-item) {
      border-bottom: 0;
    }

    :deep(.ant-collapse-header) {
      align-items: center;
      padding: @spacing-md !important;
    }

    :deep(.ant-collapse-content) {
      background: transparent;
      border-top: 1px solid rgba(210, 221, 236, 0.9);
    }

    :deep(.ant-collapse-content-box) {
      padding: @spacing-md;
    }
  }

  .result-collapse-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: @spacing-md;
    width: 100%;
  }

  .result-collapse-copy {
    min-width: 0;
  }

  .result-collapse-label {
    display: block;
    margin-bottom: @spacing-xs;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .result-collapse-title {
    display: block;
    color: @text-color-light-primary;
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
  }

  .result-collapse-desc {
    margin: @spacing-xs 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
    overflow-wrap: anywhere;
  }

  @media (max-width: @screen-md) {
    .tools-column {
      grid-column: auto;
    }

    .form-action-bar {
      flex-direction: column;
    }

    .form-action-buttons {
      justify-content: flex-start;
    }

    .form-action-buttons,
    .form-action-buttons :deep(.ant-space-item),
    .form-action-buttons :deep(.ant-btn) {
      width: 100%;
    }
  }

  @media (max-width: @screen-sm) {
    .tool-select-panel {
      grid-template-columns: minmax(0, 1fr);
      gap: @spacing-md;
    }
  }
</style>
