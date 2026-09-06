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
            :hidden-field-keys="autoBoundFieldKeys"
            :allow-artifacts="userStore.isLoggedIn"
            :allow-uploads="true"
            :tool-id="selectedTool?.id"
            :tool-slug="selectedTool?.slug"
            :preferred-tool-slug="selectedTool?.slug"
            @update:file-list="handleFileListChange"
            @update:selected-artifact="handleArtifactSelection"
          />

          <div v-if="autoBoundArtifactCards.length" class="auto-bound-artifacts">
            <span class="auto-bound-title">已自动绑定上游产物</span>
            <div
              v-for="card in autoBoundArtifactCards"
              :key="card.key"
              class="auto-bound-artifact-card"
            >
              <div>
                <strong>{{ card.fieldTitle }}</strong>
                <p>{{ card.sourceLabel }}</p>
              </div>
              <a-tag color="blue">{{ card.filename }}</a-tag>
            </div>
          </div>

          <a-alert
            v-if="preparationBlockedReason"
            type="warning"
            show-icon
            :message="preparationBlockedReason"
          />

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
  import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import type { FormInstance } from 'ant-design-vue/es/form'
  import type { UploadFile } from 'ant-design-vue'
  import ToolParameterForm from '@/components/workflow/ToolParameterForm.vue'
  import { isTaskTerminalStatus } from '@/api/tasks'
  import { getToolDetail } from '@/api/tools'
  import { useUserStore, useWorkflowStore } from '@/stores'
  import { useStandaloneNodeRun } from '@/composables/useStandaloneNodeRun'
  import type { ArtifactFile, SchemaProperty, Tool, ToolSchema } from '@/types/models'
  import {
    buildToolFormInitialState,
    flattenToolInputSchema,
    isFileSchemaProperty
  } from '@/domain/tools'
  import { taskRunPreparationBlockedMessage } from '@/domain/tasks'
  import type { WorkflowNodeArtifactRecommendation } from '@/workflow/canvas-artifacts'
  import { normalizeWorkflowSemanticType } from '@/workflow/semantic-types'

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
    role_preferences?: string[]
    required_roles?: string[]
    readiness_policy?: string | null
    suggested_preparation_tool?: string | null
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
  const {
    submitting,
    preparationPreview,
    run: runStandaloneNode,
    startPolling: startStandaloneTaskPolling,
    stopPolling: stopStandaloneTaskPolling
  } = useStandaloneNodeRun({
    nodeId: computed(() => props.nodeId),
    projectId: computed(() => props.projectId)
  })

  const formRef = ref<FormInstance>()
  const selectedTool = ref<Tool | null>(null)
  const selectedToolLoading = ref(false)
  const formState = reactive<Record<string, unknown>>({})
  const fileList = reactive<Record<string, UploadFile[]>>({})
  const selectedArtifacts = reactive<Record<string, ArtifactFile | undefined>>({})
  const autoBoundArtifactByField = reactive<Record<string, ArtifactFile | undefined>>({})
  let detailRequestToken = 0

  const selectedToolSummary = computed(() => {
    if (!props.selectedToolSlug) {
      return null
    }

    return props.availableTools?.find(tool => tool.slug === props.selectedToolSlug) ?? null
  })

  const currentNodeTask = computed(() => workflowStore.taskByNode[props.nodeId] ?? null)

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

  const fileFieldKeys = computed(() =>
    Object.entries(flattenedSchema.value.properties)
      .filter(([, prop]) => isFileSchemaProperty(prop))
      .map(([key]) => key)
  )

  const recommendedArtifactSignature = computed(() =>
    (props.recommendedArtifacts ?? [])
      .map(recommendation => [
        recommendation.edgeId,
        recommendation.sourceNodeId,
        recommendation.semanticType,
        recommendation.artifact?.id ?? ''
      ].join(':'))
      .join('|')
  )

  const autoBoundFieldKeys = computed(() => Object.keys(autoBoundArtifactByField))

  const autoBoundArtifactCards = computed(() =>
    Object.entries(autoBoundArtifactByField)
      .filter((entry): entry is [string, ArtifactFile] => Boolean(entry[1]))
      .map(([fieldKey, artifact]) => ({
        key: `${fieldKey}-${artifact.id}`,
        fieldTitle: flattenedSchema.value.properties[fieldKey]?.title ?? fieldKey,
        sourceLabel: `${artifact.tool_name || artifact.tool_slug || '上游节点'} · ${artifact.semantic_type || 'artifact'}`,
        filename: artifact.filename,
      }))
  )

  const preparationBlockedReason = computed(() => {
    return taskRunPreparationBlockedMessage(preparationPreview.value)
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

    for (const key of Object.keys(autoBoundArtifactByField)) {
      delete autoBoundArtifactByField[key]
    }

    for (const key of nextKeys) {
      selectedArtifacts[key] = undefined
    }
  }

  function normalizeSemanticToken(value?: string | null): string {
    return String(normalizeWorkflowSemanticType(String(value ?? '').trim())).trim().toLowerCase()
  }

  function normalizeFieldToken(value?: string | null): string {
    return String(value ?? '')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
  }

  function fieldLooksCompatibleWithSemantic(fieldKey: string, prop: SchemaProperty, semanticType: string) {
    const targetSemanticType = normalizeSemanticToken(semanticType)
    const directCandidates = [fieldKey, prop._originalKey]
      .filter((candidate): candidate is string => Boolean(candidate))

    if (directCandidates.some(candidate => normalizeSemanticToken(candidate) === targetSemanticType)) {
      return true
    }

    const fieldText = [fieldKey, prop._originalKey, prop.title, prop.description]
      .map(value => normalizeFieldToken(value))
      .filter(Boolean)
      .join(' ')

    if (!fieldText) {
      return false
    }

    if (targetSemanticType === 'protein_structure@1') {
      return /\b(protein|receptor)\b/.test(fieldText)
    }

    if (targetSemanticType === 'binding_pocket@1') {
      return /\b(pocket|binding)\b/.test(fieldText)
    }

    if (targetSemanticType === 'ligand_structure@1') {
      return /\b(ligand|sdf|mol2?|smiles)\b/.test(fieldText)
    }

    if (targetSemanticType === 'molecule_table@1') {
      return /\b(molecule|table|csv|smiles)\b/.test(fieldText)
    }

    if (targetSemanticType === 'run_report@1') {
      return /\b(report|metadata|json)\b/.test(fieldText)
    }

    return fieldText.includes(normalizeFieldToken(targetSemanticType))
  }

  function pickRecommendedArtifactForField(
    fileFieldKey: string,
    usedArtifactIds: Set<string>
  ): ArtifactFile | null {
    const recommendations = (props.recommendedArtifacts ?? [])
      .filter(recommendation => recommendation.artifact && !usedArtifactIds.has(recommendation.artifact.id))

    if (recommendations.length === 0) {
      return null
    }

    const prop = flattenedSchema.value.properties[fileFieldKey]
    if (!prop) {
      return null
    }

    const matchedRecommendation = recommendations.find(recommendation =>
      fieldLooksCompatibleWithSemantic(fileFieldKey, prop, recommendation.semanticType)
    )

    if (matchedRecommendation?.artifact) {
      return matchedRecommendation.artifact
    }

    return recommendations.length === 1 ? recommendations[0]?.artifact ?? null : null
  }

  function applyRecommendedArtifacts(fileFieldKeys: string[]) {
    if (!fileFieldKeys.length) {
      return
    }

    const usedArtifactIds = new Set(
      Object.values(selectedArtifacts)
        .filter((artifact): artifact is ArtifactFile => Boolean(artifact))
        .map(artifact => artifact.id)
    )

    for (const fileFieldKey of fileFieldKeys) {
      if (selectedArtifacts[fileFieldKey] || fileList[fileFieldKey]?.length) {
        continue
      }

      const artifact = pickRecommendedArtifactForField(fileFieldKey, usedArtifactIds)
      if (!artifact) {
        continue
      }

      selectedArtifacts[fileFieldKey] = artifact
      formState[fileFieldKey] = artifact.id
      autoBoundArtifactByField[fileFieldKey] = artifact
      usedArtifactIds.add(artifact.id)
    }
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
    autoBoundArtifactByField[key] = undefined
    formState[key] = files[0]?.uid ?? files[0]?.name
  }

  function handleArtifactSelection(key: string, artifact: ArtifactFile | null) {
    selectedArtifacts[key] = artifact ?? undefined
    autoBoundArtifactByField[key] = undefined
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

  async function runCurrentNode() {
    if (!selectedTool.value || !props.selectedToolSlug) {
      return
    }

    await runStandaloneNode({
      tool: selectedTool.value,
      selectedToolSlug: props.selectedToolSlug,
      flattenedSchema: flattenedSchema.value,
      formState,
      fileList,
      selectedArtifacts,
      executorType: executorType.value,
      contractArtifactInputs: contractArtifactInputs.value
    })
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
    () => [props.nodeId, props.selectedToolSlug, recommendedArtifactSignature.value, fileFieldKeys.value.join('|')] as const,
    () => applyRecommendedArtifacts(fileFieldKeys.value)
  )

  watch(
    formState,
    () => {
      workflowStore.setNodeFormDraft(props.nodeId, { ...formState })
    },
    { deep: true }
  )

  watch(
    () => [currentNodeTask.value?.id ?? null, currentNodeTask.value?.status ?? null, props.selectedToolSlug ?? null] as const,
    ([taskId, status, selectedToolSlug]) => {
      if (!taskId || !status) {
        return
      }

      if (isTaskTerminalStatus(status)) {
        stopStandaloneTaskPolling()
        return
      }

      startStandaloneTaskPolling(taskId, selectedToolSlug ?? undefined)
    },
    { immediate: true }
  )

  onBeforeUnmount(() => {
    stopStandaloneTaskPolling()
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
    display: grid;
    gap: @spacing-sm;
    margin-bottom: @spacing-md;
  }

  .auto-bound-title {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    font-weight: @font-weight-semibold;
  }

  .auto-bound-artifact-card {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: @spacing-sm;
    padding: @spacing-sm @spacing-md;
    border: 1px solid #bfdbfe;
    border-radius: @border-radius-base;
    background: #eff6ff;

    strong {
      display: block;
      color: @text-color-light;
      font-size: @font-size-sm;
    }

    p {
      margin: 2px 0 0;
      color: @text-color-light-secondary;
      font-size: @font-size-xs;
      line-height: 1.4;
    }
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
