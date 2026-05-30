<template>
  <section class="workflow-column tools-column">
    <div class="column-card">
      <h2 class="column-title">{{ t('workflow.columns.tools') }}</h2>
      <p class="column-subtitle">{{ t('workflow.columns.toolsHint') }}</p>

      <div v-if="group" class="group-banner">
        <div class="group-banner-copy">
          <span class="group-banner-label">{{ t('workflow.currentGroup.label') }}</span>
          <strong class="group-banner-title">{{ group.name }}</strong>
          <p v-if="group.description" class="group-banner-desc">{{ group.description }}</p>
        </div>
      </div>

      <div v-if="group?.tools.length" class="tool-option-list">
        <button
          v-for="toolOption in group.tools"
          :key="toolOption.slug"
          type="button"
          class="tool-option-card"
          :class="{ 'tool-option-active': selectedToolSlug === toolOption.slug }"
          @click="selectTool(toolOption.slug)"
        >
          <div class="tool-option-copy">
            <h3 class="tool-option-title">{{ toolOption.name }}</h3>
            <p class="tool-option-desc">{{ toolOption.description || toolOption.slug }}</p>
          </div>
          <div class="tool-option-tags">
            <a-tag v-if="toolOption.is_recommended" color="gold">
              {{ t('workflow.toolStatus.recommended') }}
            </a-tag>
            <a-tag color="green">{{ t('workflow.toolStatus.available') }}</a-tag>
          </div>
        </button>
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
      <a-alert
        v-else-if="userStore.isGuest"
        type="warning"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #message>
          {{ t('tools.guestWarning') }}
        </template>
      </a-alert>

      <a-spin :spinning="selectedToolLoading || submitting">
        <div v-if="selectedTool && selectedToolSlug && group" class="form-shell">
          <div class="action-summary-card">
            <div class="action-summary-copy">
              <span class="action-summary-label">{{ t('workflow.currentTool.label') }}</span>
              <strong class="action-summary-title">{{ selectedTool.name }}</strong>
              <p class="action-summary-desc">
                {{ selectedTool.description || t('workflow.currentTool.descriptionFallback') }}
              </p>
            </div>
            <div class="action-summary-tags">
              <a-tag v-if="selectedToolSummary?.is_recommended" color="gold">
                {{ t('workflow.toolStatus.recommended') }}
              </a-tag>
              <a-tag v-if="activeTask" :color="taskStatusColor(activeTask.status)">
                {{ activeTask.status }}
              </a-tag>
            </div>
          </div>

          <div v-if="activeTask" class="task-summary-card">
            <div class="task-summary-row">
              <span class="task-summary-label">{{ t('tasks.status') }}</span>
              <span class="task-summary-value">{{ activeTask.status }}</span>
            </div>
            <div class="task-summary-row">
              <span class="task-summary-label">{{ t('tasks.progress') }}</span>
              <span class="task-summary-value">{{ activeTask.progress }}%</span>
            </div>
            <div v-if="activeTask.error_message" class="task-summary-row">
              <span class="task-summary-label">{{ t('common.error') }}</span>
              <span class="task-summary-value">{{ activeTask.error_message }}</span>
            </div>
          </div>

          <a-form ref="formRef" :model="formState" layout="vertical" @finish="handleSubmit">
            <template v-for="(prop, key) in flattenedSchema.properties" :key="key">
              <a-form-item
                :name="key"
                :label="prop.title"
                :rules="getFieldRules(key, prop)"
                :extra="prop.description"
              >
                <a-input
                  v-if="prop.type === 'string' && !prop.format && !prop.enum"
                  v-model:value="formState[key]"
                  :placeholder="prop.description"
                />
                <a-textarea
                  v-else-if="prop.type === 'string' && (prop.format === 'textarea' || prop.format === 'fasta' || prop.format === 'pdb')"
                  v-model:value="formState[key]"
                  :placeholder="prop.description"
                  :rows="prop.format === 'fasta' || prop.format === 'pdb' ? 8 : 4"
                  :class="{ 'code-input': prop.format === 'fasta' || prop.format === 'pdb' }"
                />
                <a-input-number
                  v-else-if="prop.type === 'number'"
                  v-model:value="formState[key]"
                  :min="prop.minimum"
                  :max="prop.maximum"
                  style="width: 100%"
                />
                <a-switch
                  v-else-if="prop.type === 'boolean'"
                  v-model:checked="formState[key]"
                />
                <a-select
                  v-else-if="prop.type === 'select' || (prop.enum && prop.type !== 'array')"
                  v-model:value="formState[key]"
                  :placeholder="prop.description"
                >
                  <a-select-option v-for="opt in prop.enum" :key="opt" :value="opt">
                    {{ opt }}
                  </a-select-option>
                </a-select>
                <a-select
                  v-else-if="prop.type === 'array' && prop.items?.enum"
                  v-model:value="formState[key]"
                  mode="multiple"
                  :placeholder="prop.description"
                >
                  <a-select-option v-for="opt in prop.items.enum" :key="opt" :value="opt">
                    {{ opt }}
                  </a-select-option>
                </a-select>
                <ArtifactFilePicker
                  v-else-if="prop.type === 'file' || prop.format === 'uri' || prop.format === 'file'"
                  :upload-list="fileList[key] ?? []"
                  :selected-artifact="selectedArtifacts[key] ?? null"
                  :accept="prop.accept"
                  :allow-artifacts="userStore.isLoggedIn"
                  @update:upload-list="(files) => handleFileListChange(String(key), files)"
                  @update:selected-artifact="(artifact) => handleArtifactSelection(String(key), artifact)"
                />
              </a-form-item>
            </template>

            <a-form-item>
              <div class="form-action-bar">
                <div class="form-action-copy">
                  <strong class="form-action-title">{{ t('workflow.currentTool.runAction') }}</strong>
                  <p class="form-action-desc">{{ t('workflow.currentTool.runHint') }}</p>
                </div>
                <a-space wrap>
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
  import type { FormInstance, Rule } from 'ant-design-vue/es/form'
  import type { UploadFile } from 'ant-design-vue'
  import { PlayCircleOutlined } from '@ant-design/icons-vue'
  import ArtifactFilePicker from '@/components/tools/ArtifactFilePicker.vue'
  import { getTaskDetail, isTaskTerminalStatus } from '@/api/tasks'
  import { getToolDetail } from '@/api/tools'
  import { uploadFile } from '@/api/files'
  import { useArtifactsStore, useTasksStore, useUserStore, useWorkflowStore } from '@/stores'
  import type {
    ArtifactFile,
    SchemaProperty,
    Tool,
    ToolPreparedSubmissionPayload,
    ToolSchema,
    WorkbenchGroup
  } from '@/types/models'
  import {
    buildTaskSubmissionPayload,
    buildToolFormInitialState,
    isFileSchemaProperty,
    flattenToolInputSchema,
    type UploadedToolFile
  } from '@/views/tools/detail-schema'
  import { toWorkflowTaskRef } from '@/workflow/task-state'

  const props = defineProps<{
    group?: WorkbenchGroup | null
    selectedToolSlug?: string | null
  }>()

  const emit = defineEmits<{
    selectTool: [toolSlug: string]
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
  const formState = reactive<Record<string, unknown>>({})
  const fileList = reactive<Record<string, UploadFile[]>>({})
  const selectedArtifacts = reactive<Record<string, ArtifactFile | undefined>>({})
  let detailRequestToken = 0
  let pollTimer: number | null = null

  const selectedToolSummary = computed(() => {
    return props.group?.tools.find((tool) => tool.slug === props.selectedToolSlug) ?? null
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

  const submitDisabled = computed(() => {
    if (submitting.value || selectedToolLoading.value) {
      return true
    }

    if (!userStore.isAuthenticated || userStore.isGuest) {
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

  function getFieldRules(key: string, prop: SchemaProperty): Rule[] {
    const rules: Rule[] = []
    const schema = flattenedSchema.value

    if (schema.required?.includes(key)) {
      if (isFileSchemaProperty(prop)) {
        rules.push({
          validator: async () => {
            if (fileList[key]?.length || selectedArtifacts[key]) {
              return Promise.resolve()
            }
            return Promise.reject(new Error(`${prop.title} ${t('common.required')}`))
          },
          trigger: 'change'
        })
      } else {
        rules.push({ required: true, message: `${prop.title} ${t('common.required')}` })
      }
    }

    if (prop.minLength) {
      rules.push({ min: prop.minLength, message: t('validation.minLength', { min: prop.minLength }) })
    }

    if (prop.maxLength) {
      rules.push({ max: prop.maxLength, message: t('validation.maxLength', { max: prop.maxLength }) })
    }

    return rules
  }

  function handleFileListChange(key: string, files: UploadFile[]) {
    fileList[key] = files
  }

  function handleArtifactSelection(key: string, artifact: ArtifactFile | null) {
    selectedArtifacts[key] = artifact ?? undefined
  }

  function resetForm() {
    formRef.value?.resetFields()

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
        tool_id: toolId,
        ...preparedPayload
      })

      workflowStore.recordTask(toolSlug, toWorkflowTaskRef(task))
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

  .group-banner {
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    padding: @spacing-md;
    margin-bottom: @spacing-md;
    background: fade(@accent-color-light, 35%);
  }

  .group-banner-label,
  .action-summary-label {
    display: inline-block;
    margin-bottom: @spacing-xs;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .group-banner-title,
  .action-summary-title,
  .form-action-title {
    display: block;
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
  }

  .group-banner-desc,
  .action-summary-desc,
  .form-action-desc {
    margin: @spacing-xs 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
  }

  .tool-option-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-md;
    margin-bottom: @spacing-md;
  }

  .tool-option-card {
    display: flex;
    justify-content: space-between;
    gap: @spacing-md;
    width: 100%;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    padding: @spacing-md;
    background: @bg-card-light;
    cursor: pointer;
    text-align: left;
    transition: border-color 0.2s ease, transform 0.2s ease;

    &:hover,
    &:focus-visible {
      border-color: @accent-color;
      transform: translateY(-1px);
    }

    &:focus-visible {
      outline: 3px solid rgba(24, 144, 255, 0.28);
      outline-offset: 3px;
    }
  }

  .tool-option-active {
    border-color: @accent-color;
    box-shadow: @shadow-sm;
  }

  .tool-option-copy {
    min-width: 0;
    flex: 1;
  }

  .tool-option-title {
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-xs;
  }

  .tool-option-desc {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .tool-option-tags {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-xs;
    justify-content: flex-end;
  }

  .form-shell {
    display: flex;
    flex-direction: column;
    gap: @spacing-lg;
  }

  .action-summary-card,
  .task-summary-card,
  .form-action-bar {
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    padding: @spacing-md;
    background: @bg-card-light;
  }

  .action-summary-card,
  .form-action-bar {
    display: flex;
    justify-content: space-between;
    gap: @spacing-md;
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .action-summary-copy,
  .form-action-copy {
    min-width: 0;
    flex: 1;
  }

  .action-summary-tags {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-xs;
  }

  .task-summary-card {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .task-summary-row {
    display: flex;
    justify-content: space-between;
    gap: @spacing-md;
  }

  .task-summary-label {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .task-summary-value {
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    text-align: right;
  }
</style>
