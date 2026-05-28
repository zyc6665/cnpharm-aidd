<template>
  <section class="workflow-column tools-column">
    <div class="column-card">
      <h2 class="column-title">{{ t('workflow.columns.tools') }}</h2>
      <p class="column-subtitle">{{ t('workflow.columns.toolsHint') }}</p>

      <div class="active-step-banner">
        <span class="active-step-label">{{ t('workflow.columns.steps') }}</span>
        <strong class="active-step-value">{{ t(`workflow.steps.${step.key}.title`) }}</strong>
      </div>

      <a-alert
        v-if="invalidatedDownstreamStepKeys.length > 0"
        type="warning"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #message>
          {{ t('workflow.invalidations.notice') }}
        </template>
      </a-alert>

      <div class="tool-option-list">
        <div
          v-for="toolOption in toolViewModel.tools"
          :key="toolOption.slug"
          :class="[
            'tool-option-card',
            {
              'tool-option-active': selectedToolSlug === toolOption.slug,
              'tool-option-missing': toolOption.availability === 'missing'
            }
          ]"
          @click="selectTool(toolOption.slug, toolOption.availability)"
        >
          <div class="tool-option-copy">
            <h3 class="tool-option-title">{{ toolOption.tool?.name ?? toolOption.slug }}</h3>
            <p class="tool-option-desc">{{ toolOption.tool?.description ?? toolOption.slug }}</p>
          </div>
          <div class="tool-option-tags">
            <a-tag v-if="toolOption.isRecommended" color="gold">
              {{ t('workflow.toolStatus.recommended') }}
            </a-tag>
            <a-tag v-if="toolOption.availability === 'available'" color="green">
              {{ t('workflow.toolStatus.available') }}
            </a-tag>
            <a-tag v-else>
              {{ t('workflow.toolStatus.unavailable') }}
            </a-tag>
          </div>
        </div>
      </div>

      <a-spin :spinning="selectedToolLoading || submitting">
        <div v-if="selectedTool && flattenedSchema" class="form-shell">
          <div class="bound-source-list">
            <h3 class="section-subtitle-inline">{{ t('workflow.boundSources.title') }}</h3>
            <div
              v-for="source in boundSources"
              :key="`${source.field}:${source.semanticType}`"
              class="bound-source-item"
            >
              <span class="bound-source-field">{{ source.field }}</span>
              <span class="bound-source-value">
                {{ source.artifact?.name ?? t('workflow.boundSources.waiting') }}
              </span>
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
                <a-upload
                  v-else-if="prop.type === 'file' || prop.format === 'uri' || prop.format === 'file'"
                  v-model:file-list="fileList[key]"
                  :accept="prop.accept"
                  :before-upload="() => false"
                  :max-count="1"
                >
                  <a-button>
                    <UploadOutlined />
                    {{ t('tools.selectFile') }}
                  </a-button>
                  <template #itemRender="{ file }">
                    <span class="file-item">
                      <FileOutlined />
                      {{ file.name }}
                    </span>
                  </template>
                </a-upload>
              </a-form-item>
            </template>

            <a-form-item>
              <a-space>
                <a-button
                  type="primary"
                  html-type="submit"
                  size="large"
                  :loading="submitting"
                  :disabled="selectedToolSlug == null"
                >
                  <PlayCircleOutlined />
                  {{ t('tools.runTool') }}
                </a-button>
                <a-button size="large" @click="resetForm">
                  {{ t('common.reset') }}
                </a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </div>

        <div v-else class="placeholder-list">
          <div class="placeholder-card">
            <h3 class="placeholder-title">{{ t('workflow.placeholders.availableTools.title') }}</h3>
            <p class="placeholder-desc">{{ t('workflow.placeholders.availableTools.description') }}</p>
          </div>
          <div class="placeholder-card">
            <h3 class="placeholder-title">{{ t('workflow.placeholders.parameterSetup.title') }}</h3>
            <p class="placeholder-desc">{{ t('workflow.placeholders.parameterSetup.description') }}</p>
          </div>
        </div>
      </a-spin>
    </div>
  </section>
</template>

<script setup lang="ts">
  import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import type { FormInstance, Rule } from 'ant-design-vue/es/form'
  import type { UploadFile } from 'ant-design-vue'
  import { FileOutlined, PlayCircleOutlined, UploadOutlined } from '@ant-design/icons-vue'
  import { getTaskDetail, isTaskTerminalStatus } from '@/api/tasks'
  import { getToolDetail } from '@/api/tools'
  import { uploadFile } from '@/api/files'
  import { useTasksStore, useWorkflowStore } from '@/stores'
  import type {
    SchemaProperty,
    Tool,
    ToolPreparedSubmissionPayload,
    ToolSchema
  } from '@/types/models'
  import type { WorkflowArtifact, WorkflowArtifactSemanticType, WorkflowStepKey } from '@/workflow/artifact-types'
  import { resolveWorkflowInputSourcesForTool } from '@/workflow/artifact-resolver'
  import {
    buildTaskSubmissionPayload,
    buildToolFormInitialState,
    flattenToolInputSchema,
    isFileSchemaProperty,
    type UploadedToolFile
  } from '@/views/tools/detail-schema'
  import type { WorkflowStepCatalogItem } from '@/workflow/aidd-catalog'
  import { toWorkflowTaskRef } from '@/workflow/task-state'
  import type { WorkflowBoundToolSlug } from '@/workflow/tool-bindings'
  import type { WorkflowStepToolViewModel, WorkflowToolAvailability } from '@/workflow/step-tools'

  interface WorkflowBoundSourceItem {
    field: string
    semanticType: WorkflowArtifactSemanticType
    artifact: WorkflowArtifact | null
  }

  const props = defineProps<{
    step: WorkflowStepCatalogItem
    toolViewModel: WorkflowStepToolViewModel
    selectedToolSlug?: WorkflowBoundToolSlug | null
  }>()

  const emit = defineEmits<{
    selectTool: [toolSlug: WorkflowBoundToolSlug]
  }>()

  const { t } = useI18n()
  const tasksStore = useTasksStore()
  const workflowStore = useWorkflowStore()

  const formRef = ref<FormInstance>()
  const selectedTool = ref<Tool | null>(null)
  const selectedToolLoading = ref(false)
  const submitting = ref(false)
  const formState = reactive<Record<string, unknown>>({})
  const fileList = reactive<Record<string, UploadFile[]>>({})
  let detailRequestToken = 0
  let pollTimer: number | null = null

  const selectedToolSummary = computed(() => {
    return props.toolViewModel.tools.find((tool) => tool.slug === props.selectedToolSlug)?.tool ?? null
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

  const flattenedSchema = computed<ToolSchema | undefined>(() => {
    return flattenToolInputSchema(inputSchema.value)
  })

  const boundSources = computed<WorkflowBoundSourceItem[]>(() => {
    if (!props.selectedToolSlug) {
      return []
    }

    return resolveWorkflowInputSourcesForTool({
      toolSlug: props.selectedToolSlug,
      artifacts: workflowStore.artifacts,
      invalidArtifactIds: workflowStore.invalidArtifactIds
    })
  })

  const linkedArtifactFiles = computed<Record<string, UploadedToolFile>>(() => {
    const schema = flattenedSchema.value?.properties
    if (!schema) {
      return {}
    }

    return boundSources.value.reduce<Record<string, UploadedToolFile>>((accumulator, source) => {
      const prop = schema[source.field]
      if (!prop || !isFileSchemaProperty(prop) || !source.artifact?.url) {
        return accumulator
      }

      accumulator[source.field] = {
        fileId: String(source.artifact.fileId ?? source.artifact.id),
        filename: source.artifact.name,
        downloadUrl: source.artifact.url
      }

      return accumulator
    }, {})
  })

  const invalidatedDownstreamStepKeys = computed(() => {
    return Object.entries(workflowStore.stepStateByKey)
      .filter(([stepKey, stepState]) => stepKey !== props.step.key && stepState?.status === 'invalidated')
      .map(([stepKey]) => stepKey)
  })

  function selectTool(toolSlug: WorkflowBoundToolSlug, availability: WorkflowToolAvailability) {
    if (availability === 'missing' || props.selectedToolSlug === toolSlug) {
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

  function applyInitialFormState(stepKey: WorkflowStepKey, schema?: ToolSchema, resetDraft = false) {
    const draft = resetDraft ? {} : workflowStore.stepFormDrafts[stepKey]
    const initialState = buildToolFormInitialState({
      flattenedSchema: schema,
      draft
    })

    if (schema?.properties) {
      for (const source of boundSources.value) {
        const prop = schema.properties[source.field]
        const metadataValue = source.artifact?.metadata?.value

        if (
          !prop ||
          isFileSchemaProperty(prop) ||
          metadataValue === undefined ||
          Object.prototype.hasOwnProperty.call(initialState.formState, source.field)
        ) {
          continue
        }

        initialState.formState[source.field] = metadataValue
      }
    }

    replaceFormState(initialState.formState)
    replaceFileList(initialState.fileFieldKeys)
  }

  function getFieldRules(key: string, prop: SchemaProperty): Rule[] {
    const rules: Rule[] = []
    const schema = flattenedSchema.value

    if (schema?.required?.includes(key)) {
      if (isFileSchemaProperty(prop)) {
        rules.push({
          validator: async () => {
            if (fileList[key]?.length) {
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

  function resetForm() {
    formRef.value?.resetFields()
    workflowStore.setStepFormDraft(props.step.key, {})
    applyInitialFormState(props.step.key, flattenedSchema.value, true)
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
      const response = await getTaskDetail(taskId)
      workflowStore.recordTask(props.step.key, toWorkflowTaskRef(response.data))

      if (response.data.status === 'success' && props.selectedToolSlug) {
        workflowStore.registerTaskArtifacts(props.step.key, props.selectedToolSlug, toWorkflowTaskRef(response.data))
      }

      if (isTaskTerminalStatus(response.data.status)) {
        clearTaskPoll()
        return
      }

      pollTimer = window.setTimeout(poll, 3000)
    }

    pollTimer = window.setTimeout(poll, 3000)
  }

  async function handleSubmit() {
    const schema = flattenedSchema.value
    const toolId = selectedTool.value?.id

    if (!schema || !toolId) {
      return
    }

    submitting.value = true
    try {
      workflowStore.invalidateDownstreamFrom(props.step.key)

      const uploadedFiles: Record<string, UploadedToolFile | undefined> = {
        ...linkedArtifactFiles.value
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
        flattenedSchema: schema,
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

      workflowStore.recordTask(props.step.key, toWorkflowTaskRef(task))
      if (task.status === 'success' && props.selectedToolSlug) {
        workflowStore.registerTaskArtifacts(props.step.key, props.selectedToolSlug, toWorkflowTaskRef(task))
      }
      await pollTaskUntilTerminal(task.id)
    } finally {
      submitting.value = false
    }
  }

  watch(
    () => props.selectedToolSlug,
    async (selectedToolSlug) => {
      const requestToken = ++detailRequestToken
      const toolId = selectedToolSummary.value?.id

      if (!selectedToolSlug || !toolId) {
        selectedToolLoading.value = false
        selectedTool.value = null
        replaceFormState({})
        replaceFileList([])
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
    () => [props.step.key, flattenedSchema.value, props.selectedToolSlug] as const,
    ([stepKey, schema, selectedToolSlug]) => {
      if (!selectedToolSlug) {
        replaceFormState({})
        replaceFileList([])
        return
      }

      applyInitialFormState(stepKey, schema)
    },
    { immediate: true }
  )

  watch(
    formState,
    () => {
      workflowStore.setStepFormDraft(props.step.key, { ...formState })
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

  .active-step-banner {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    padding: @spacing-sm @spacing-md;
    margin-bottom: @spacing-md;
    background: fade(@accent-color-light, 35%);
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
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    padding: @spacing-md;
    background: @bg-card-light;
    cursor: pointer;
    transition: border-color 0.2s ease, transform 0.2s ease;

    &:hover {
      border-color: @accent-color;
      transform: translateY(-1px);
    }
  }

  .tool-option-active {
    border-color: @accent-color;
    box-shadow: @shadow-sm;
  }

  .tool-option-missing {
    cursor: default;
    opacity: 0.72;
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

  .active-step-label {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .active-step-value {
    color: @text-color-primary;
    font-size: @font-size-md;
  }

  .form-shell {
    display: flex;
    flex-direction: column;
    gap: @spacing-lg;
  }

  .bound-source-list,
  .placeholder-card {
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    padding: @spacing-md;
    background: @bg-card-light;
  }

  .section-subtitle-inline {
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-sm;
  }

  .bound-source-item {
    display: flex;
    justify-content: space-between;
    gap: @spacing-md;
    padding: @spacing-xs 0;
    border-top: 1px solid @border-color-light;

    &:first-of-type {
      border-top: 0;
      padding-top: 0;
    }
  }

  .bound-source-field {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .bound-source-value {
    color: @text-color-primary;
    font-size: @font-size-sm;
    text-align: right;
  }

  .placeholder-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-md;
  }

  .placeholder-title {
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-xs;
  }

  .placeholder-desc {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
  }

  .file-item {
    display: inline-flex;
    align-items: center;
    gap: @spacing-xs;
  }
</style>
