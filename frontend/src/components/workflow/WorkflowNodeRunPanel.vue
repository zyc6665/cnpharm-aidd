<template>
  <section class="workflow-node-run-panel">
    <a-alert
      v-if="!userStore.isAuthenticated"
      type="info"
      show-icon
      :message="t('workflow.nodeRun.loginPrompt')"
    />
    <a-spin :spinning="selectedToolLoading">
      <div v-if="selectedTool && selectedToolSlug" class="node-run-form">
        <div class="run-tool-summary">
          <span class="section-title">{{ t('workflow.inspector.nodeParameters') }}</span>
          <strong>{{ selectedTool.name }}</strong>
          <p v-if="selectedTool.description">{{ selectedTool.description }}</p>
        </div>

        <a-form ref="formRef" :model="formState" layout="vertical">
          <ToolRunInputForm
            :schema="flattenedSchema"
            :form-state="formState"
            :file-list="fileList"
            :selected-artifacts="selectedArtifacts"
            :standard-input-slots="standardInputSlots"
            :show-standard-artifact-inputs="inputSurface.showStandardArtifactInputs"
            :current-project-id="projectId ?? undefined"
            :project-artifacts="standardProjectArtifacts"
            :standard-artifacts-loading="standardArtifactsLoading"
            :project-artifact-placeholder="t('tools.selectProjectArtifact')"
            :selected-standard-artifacts="selectedStandardArtifacts"
            :standard-input-file-list="standardInputFileList"
            :hidden-field-keys="autoBoundFieldKeys"
            :allow-artifacts="userStore.isLoggedIn"
            :allow-uploads="true"
            :tool-id="selectedTool?.id"
            :tool-slug="selectedTool?.slug"
            :preferred-tool-slug="selectedTool?.slug"
            @update:file-list="handleFileListChange"
            @update:selected-artifact="handleArtifactSelection"
            @select-standard-artifact="handleStandardArtifactSelection"
            @update-standard-upload-list="handleStandardInputFileListChange"
          />

          <div v-if="autoBoundArtifactCards.length" class="auto-bound-artifacts">
            <span class="auto-bound-title">{{ t('workflow.nodeRun.autoBoundTitle') }}</span>
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
              {{ t('workflow.nodeRun.runCurrentNode') }}
            </a-button>
            <a-button @click="resetForm">{{ t('workflow.nodeRun.reset') }}</a-button>
          </div>
        </a-form>
      </div>

      <a-empty
        v-else
        :description="t('workflow.nodeRun.selectToolFirst')"
      />
    </a-spin>
  </section>
</template>

<script setup lang="ts">
  import { computed, reactive, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import type { FormInstance } from 'ant-design-vue/es/form'
  import type { UploadFile } from 'ant-design-vue'
  import ToolRunInputForm from '@/components/tools/ToolRunInputForm.vue'
  import { getAllProjectArtifacts } from '@/api/artifacts'
  import { getToolDetail } from '@/api/tools'
  import { useUserStore, useWorkflowStore } from '@/stores'
  import { useStandaloneNodeRun } from '@/composables/useStandaloneNodeRun'
  import { useToolDetailStandardArtifacts } from '@/composables/useToolDetailStandardArtifacts'
  import {
    useWorkflowNodeSelectedTool,
    type WorkflowAvailableTool,
  } from '@/composables/useWorkflowNodeSelectedTool'
  import type { ArtifactFile, ToolSchema } from '@/types/models'
  import type { TypedArtifact } from '@/types/artifacts'
  import { replaceRecord } from '@/utils/record-state'
  import {
    buildToolRunFormState,
    isFileSchemaProperty,
  } from '@/domain/tools'
  import type { WorkflowNodeArtifactRecommendation } from '@/workflow/canvas-artifacts'
  import {
    applyManualArtifactSelection,
    applyManualFileSelection,
    applyRecommendedArtifactBindings,
    buildAutoBoundArtifactCards,
    clearAutoBoundArtifactBindings,
    resolveWorkflowNodeRunInputSurface
  } from '@/workflow/node-run-inputs'

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
    preparationBlockedReason,
    run: runStandaloneNode
  } = useStandaloneNodeRun({
    nodeId: computed(() => props.nodeId),
    projectId: computed(() => props.projectId)
  })

  const formRef = ref<FormInstance>()
  const formState = reactive<Record<string, unknown>>({})
  const fileList = reactive<Record<string, UploadFile[]>>({})
  const selectedArtifacts = reactive<Record<string, ArtifactFile | undefined>>({})
  const selectedStandardArtifacts = reactive<Record<string, TypedArtifact | undefined>>({})
  const standardInputFileList = reactive<Record<string, UploadFile[]>>({})
  const autoBoundArtifactByField = reactive<Record<string, ArtifactFile | undefined>>({})

  function clearNodeRunFormState() {
    replaceRecord(formState, {})
    replaceRecord(fileList, {})
    replaceRecord(selectedArtifacts, {})
    replaceRecord(selectedStandardArtifacts, {})
    replaceRecord(standardInputFileList, {})
    clearAutoBoundArtifactBindings(autoBoundArtifactByField)
  }

  const { selectedTool, selectedToolLoading } = useWorkflowNodeSelectedTool({
    selectedToolSlug: computed(() => props.selectedToolSlug),
    availableTools: computed(() => props.availableTools),
    api: {
      getToolDetail: async toolId => (await getToolDetail(toolId)).data,
    },
    onMissingTool: clearNodeRunFormState,
  })

  const inputSurface = computed(() => resolveWorkflowNodeRunInputSurface({
    tool: selectedTool.value,
    labels: {
      standardArtifactDescription: artifactType => t('workflow.nodeRun.standardArtifactDescription', { artifactType }),
      upstreamNodeFallback: t('workflow.nodeRun.upstreamNodeFallback'),
    },
  }))
  const standardInputSlots = computed(() => inputSurface.value.standardInputSlots)

  const {
    standardProjectArtifacts,
    standardArtifactsLoading,
    loadStandardProjectArtifacts,
    handleStandardArtifactSelection,
    handleStandardInputFileListChange,
  } = useToolDetailStandardArtifacts({
    projectId: computed(() => props.projectId ?? undefined),
    standardInputSlots,
    api: { getAllProjectArtifacts },
    selectStandardArtifact: (slotName, versionId, projectArtifacts) => {
      selectedStandardArtifacts[slotName] = versionId
        ? projectArtifacts.find(artifact => artifact.latest_version.id === versionId)
        : undefined
      if (selectedStandardArtifacts[slotName]) {
        standardInputFileList[slotName] = []
      }
    },
    updateStandardInputFileList: (slotName, files) => {
      standardInputFileList[slotName] = files
      if (files.length) {
        selectedStandardArtifacts[slotName] = undefined
      }
    },
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

  const flattenedSchema = computed<ToolSchema>(() => inputSurface.value.flattenedSchema)

  const fileFieldKeys = computed(() =>
    Object.entries(flattenedSchema.value.properties)
      .filter(([, prop]) => isFileSchemaProperty(prop))
      .map(([key]) => key)
  )
  const standardInputFileFieldBindings = computed(
    () => inputSurface.value.standardInputFileFieldBindings
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

  const autoBoundArtifactCards = computed(() => buildAutoBoundArtifactCards({
    autoBoundArtifactByField,
    flattenedSchema: flattenedSchema.value,
    labels: {
      upstreamNodeFallback: t('workflow.nodeRun.upstreamNodeFallback'),
    },
  }))

  function applyRecommendedArtifacts(fileFieldKeys: string[]) {
    if (!fileFieldKeys.length) {
      return
    }

    applyRecommendedArtifactBindings({
      fileFieldKeys,
      flattenedSchema: flattenedSchema.value,
      selectedArtifacts,
      fileList,
      formState,
      autoBoundArtifactByField,
      recommendations: props.recommendedArtifacts ?? []
    })
  }

  function applyInitialFormState(resetDraft = false) {
    const draft = resetDraft ? {} : workflowStore.nodeFormDrafts[props.nodeId]
    const state = buildToolRunFormState({
      flattenedSchema: flattenedSchema.value,
      standardInputSlots: standardInputSlots.value,
      draft
    })
    const nextFileFieldKeys = Object.keys(state.fileList)

    replaceRecord(formState, state.formState)
    replaceRecord(fileList, state.fileList)
    replaceRecord(selectedArtifacts, state.selectedArtifacts)
    replaceRecord(selectedStandardArtifacts, state.selectedStandardArtifacts)
    replaceRecord(standardInputFileList, state.standardInputFileList)
    clearAutoBoundArtifactBindings(autoBoundArtifactByField)
    applyRecommendedArtifacts(nextFileFieldKeys)
  }

  function handleFileListChange(key: string, files: UploadFile[]) {
    applyManualFileSelection({
      fieldKey: key,
      files,
      fileList,
      selectedArtifacts,
      formState,
      autoBoundArtifactByField
    })
  }

  function handleArtifactSelection(key: string, artifact: ArtifactFile | null) {
    applyManualArtifactSelection({
      fieldKey: key,
      artifact,
      fileList,
      selectedArtifacts,
      formState,
      autoBoundArtifactByField
    })
  }

  async function runCurrentNode() {
    if (!selectedTool.value || !props.selectedToolSlug) {
      return
    }

    try {
      await formRef.value?.validate()
    } catch {
      return
    }

    await runStandaloneNode({
      tool: selectedTool.value,
      flattenedSchema: flattenedSchema.value,
      formState,
      fileList,
      selectedArtifacts,
      executorType: executorType.value,
      standardInputSlots: standardInputSlots.value,
      standardInputFileFieldBindings: standardInputFileFieldBindings.value,
      selectedStandardArtifacts,
      standardInputFileList,
    })
  }

  function resetForm() {
    formRef.value?.resetFields()
    workflowStore.setNodeFormDraft(props.nodeId, {})
    applyInitialFormState(true)
  }

  watch(
    () => [props.nodeId, props.selectedToolSlug, flattenedSchema.value] as const,
    () => applyInitialFormState(),
    { immediate: true }
  )

  watch(
    () => [
      props.projectId,
      props.selectedToolSlug,
      standardInputSlots.value.map(slot => slot.name).join('|'),
      inputSurface.value.showStandardArtifactInputs,
    ] as const,
    () => {
      if (inputSurface.value.showStandardArtifactInputs) {
        void loadStandardProjectArtifacts()
      }
    },
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
