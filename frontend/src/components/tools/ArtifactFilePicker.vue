<template>
  <div class="artifact-file-picker">
    <a-radio-group
      v-if="allowArtifacts && allowUploads"
      :value="activeSourceMode"
      size="small"
      class="source-switch"
      @update:value="handleSourceModeChange"
    >
      <a-radio-button value="upload">{{ t('tools.fileSourceUpload') }}</a-radio-button>
      <a-radio-button value="artifact">{{ t('tools.fileSourceArtifact') }}</a-radio-button>
    </a-radio-group>

    <div v-if="activeSourceMode === 'upload' && allowUploads" class="source-panel">
      <a-upload
        :file-list="uploadList"
        :accept="accept"
        :before-upload="() => false"
        :max-count="1"
        @update:file-list="handleUploadListChange"
      >
        <a-button>
          <UploadOutlined />
          {{ t('tools.selectFile') }}
        </a-button>
      </a-upload>
    </div>

    <div v-else-if="allowArtifacts" class="source-panel artifact-panel">
      <div class="artifact-toolbar">
        <span class="artifact-toolbar-label">{{ t('tools.selectCompatibleArtifact') }}</span>
        <a-button type="link" size="small" :loading="artifactsStore.loading" @click="refreshArtifacts">
          {{ t('common.refresh') }}
        </a-button>
      </div>

      <div v-if="artifactGroupNodes.length > 0" class="artifact-flow">
        <ArtifactPickerPath
          :segments="pathSegments"
          :active-step="activeStep"
          @select="handlePathSegmentClick"
        />

        <ArtifactPickerStepPanel
          :label="currentStepLabel"
          :title="currentStepTitle"
          :count="currentStepCount"
          :options="currentStepOptions"
          @select="handleStepOptionSelect"
        />

        <ArtifactPickerSelectionSummary
          :label="summaryLabel"
          :title="summaryTitle"
          :meta="summaryMeta"
          :show-clear="Boolean(selectedArtifact)"
          @clear="clearArtifactSelection"
        />
      </div>

      <a-empty
        v-else
        class="artifact-empty"
        :description="t('tools.noCompatibleArtifacts')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import type { UploadFile } from 'ant-design-vue'
  import { UploadOutlined } from '@ant-design/icons-vue'
  import ArtifactPickerPath from './ArtifactPickerPath.vue'
  import ArtifactPickerStepPanel from './ArtifactPickerStepPanel.vue'
  import ArtifactPickerSelectionSummary from './ArtifactPickerSelectionSummary.vue'
  import {
    applyArtifactPickerExternalSelectionPath,
    buildArtifactPickerStepOptions,
    buildArtifactPickerViewModel,
    fingerprintArtifactPickerGroups,
    resolveArtifactPickerActiveSourceMode,
    resolveArtifactPickerSelectionState,
    resolveArtifactPickerSyncedSourceMode,
    type ArtifactPickerSelectionState,
    type ArtifactPickerSourceMode,
    type ArtifactPickerStep
  } from '@/domain/tools'
  import { useArtifactsStore, useToolsStore } from '@/stores'
  import type { ArtifactFile } from '@/types/models'
  import {
    buildWorkflowArtifactHierarchy,
    type WorkflowArtifactSelectionPath
  } from '../../workflow/artifact-hierarchy.ts'

  const props = withDefaults(
    defineProps<{
      uploadList: UploadFile[]
      selectedArtifact?: ArtifactFile | null
      accept?: string
      allowArtifacts?: boolean
      allowUploads?: boolean
      currentToolSlug?: string | null
      preferredGroupId?: string | null
      preferredToolSlug?: string | null
      externalSelectionPath?: WorkflowArtifactSelectionPath | null
    }>(),
    {
      selectedArtifact: null,
      accept: undefined,
      allowArtifacts: true,
      allowUploads: true,
      currentToolSlug: null,
      preferredGroupId: null,
      preferredToolSlug: null,
      externalSelectionPath: null
    }
  )

  const emit = defineEmits<{
    'update:uploadList': [files: UploadFile[]]
    'update:selectedArtifact': [artifact: ArtifactFile | null]
  }>()

  const { t } = useI18n()

  const artifactsStore = useArtifactsStore()
  const toolsStore = useToolsStore()
  const sourceMode = ref<ArtifactPickerSourceMode>('upload')
  const activeSourceMode = computed(() => resolveArtifactPickerActiveSourceMode({
    allowArtifacts: props.allowArtifacts,
    allowUploads: props.allowUploads,
    sourceMode: sourceMode.value
  }))
  const activeStep = ref<ArtifactPickerStep>('group')
  const selectedGroupId = ref<string>()
  const selectedToolSlug = ref<string>()
  const selectedTaskId = ref<string>()
  const focusedArtifactId = ref<string>()

  const artifactGroupNodes = computed(() => {
    return buildWorkflowArtifactHierarchy({
      groups: toolsStore.workbenchGroups,
      artifacts: artifactsStore.items,
      accept: props.accept,
      scope: 'global'
    }).groups
  })

  const pickerLabels = computed(() => ({
    groupLabel: t('tools.artifactGroupLabel'),
    toolLabel: t('tools.artifactToolLabel'),
    taskLabel: t('tools.artifactTaskLabel'),
    outputLabel: t('tools.artifactOutputLabel'),
    selectGroup: t('tools.selectArtifactGroup'),
    selectTool: t('tools.selectArtifactTool'),
    selectTask: t('tools.selectArtifactTask'),
    selectOutput: t('tools.selectArtifactOutput'),
    summarySelected: t('tools.artifactSummarySelected'),
    summaryFocused: t('tools.artifactSummaryFocused'),
    summaryPending: t('tools.artifactSummaryPending'),
    ungroupedGroup: t('workflow.artifacts.ungroupedGroup'),
    groupMeta: t('tools.artifactGroupMeta'),
    toolMeta: t('tools.artifactToolMeta'),
    noArtifacts: t('tools.noArtifacts'),
    noCompatibleArtifacts: t('tools.noCompatibleArtifacts'),
    artifactSelectedTag: t('tools.artifactSelectedTag'),
    artifactFocusTag: t('tools.artifactFocusTag')
  }))

  const pickerViewModel = computed(() => buildArtifactPickerViewModel({
    groupNodes: artifactGroupNodes.value,
    activeStep: activeStep.value,
    selectedGroupId: selectedGroupId.value,
    selectedToolSlug: selectedToolSlug.value,
    selectedTaskId: selectedTaskId.value,
    focusedArtifactId: focusedArtifactId.value,
    selectedArtifact: props.selectedArtifact,
    labels: pickerLabels.value
  }))

  const selectedGroupTools = computed(() => pickerViewModel.value.selectedGroupTools)
  const selectedToolNode = computed(() => pickerViewModel.value.selectedToolNode)
  const selectedToolTasks = computed(() => pickerViewModel.value.selectedToolTasks)
  const selectedTaskArtifacts = computed(() => pickerViewModel.value.selectedTaskArtifacts)
  const compatibleArtifacts = computed(() => pickerViewModel.value.compatibleArtifacts)
  const pathSegments = computed(() => pickerViewModel.value.pathSegments)
  const currentStepLabel = computed(() => pickerViewModel.value.currentStep.label)
  const currentStepTitle = computed(() => pickerViewModel.value.currentStep.title)
  const currentStepCount = computed(() => pickerViewModel.value.currentStep.count)
  const summaryLabel = computed(() => pickerViewModel.value.summary.label)
  const summaryTitle = computed(() => pickerViewModel.value.summary.title)
  const summaryMeta = computed(() => pickerViewModel.value.summary.meta)

  const currentStepOptions = computed(() => buildArtifactPickerStepOptions({
    activeStep: activeStep.value,
    groupNodes: artifactGroupNodes.value,
    selectedGroupTools: selectedGroupTools.value,
    selectedToolNode: selectedToolNode.value,
    selectedToolTasks: selectedToolTasks.value,
    selectedTaskArtifacts: selectedTaskArtifacts.value,
    selectedGroupId: selectedGroupId.value,
    selectedToolSlug: selectedToolSlug.value,
    selectedTaskId: selectedTaskId.value,
    selectedArtifact: props.selectedArtifact,
    focusedArtifactId: focusedArtifactId.value,
    labels: pickerLabels.value,
    formatTaskArtifactCount: (count) => t('workflow.artifacts.taskCount', { count })
  }))

  function syncSourceMode() {
    sourceMode.value = resolveArtifactPickerSyncedSourceMode({
      allowArtifacts: props.allowArtifacts,
      allowUploads: props.allowUploads,
      hasSelectedArtifact: Boolean(props.selectedArtifact)
    })
  }

  async function refreshArtifacts() {
    if (!props.allowArtifacts) {
      return
    }

    await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
  }

  function resetUploadSelection() {
    if (props.uploadList.length > 0) {
      emit('update:uploadList', [])
    }
  }

  function clearSelectedArtifactValue() {
    focusedArtifactId.value = undefined
    if (props.selectedArtifact) {
      emit('update:selectedArtifact', null)
    }
  }

  function handleSourceModeChange(value: ArtifactPickerSourceMode) {
    if (value === 'upload' && !props.allowUploads) {
      return
    }

    sourceMode.value = value
    if (value === 'upload') {
      emit('update:selectedArtifact', null)
      return
    }

    emit('update:uploadList', [])
    syncSelectionPath()
  }

  function handleUploadListChange(files: UploadFile[]) {
    if (!props.allowUploads) {
      emit('update:uploadList', [])
      return
    }

    emit('update:uploadList', files)
    if (files.length > 0) {
      emit('update:selectedArtifact', null)
    }
  }

  function handleGroupSelect(groupId: string) {
    selectedGroupId.value = groupId
    selectedToolSlug.value = undefined
    selectedTaskId.value = undefined
    clearSelectedArtifactValue()
    resetUploadSelection()
    activeStep.value = 'tool'
  }

  function handleToolSelect(toolSlug: string) {
    selectedToolSlug.value = toolSlug
    selectedTaskId.value = undefined
    clearSelectedArtifactValue()
    resetUploadSelection()
    activeStep.value = 'task'
  }

  function handleTaskSelect(taskId: string) {
    selectedTaskId.value = taskId
    clearSelectedArtifactValue()
    resetUploadSelection()
    activeStep.value = 'artifact'
  }

  function handleArtifactSelect(artifactId: string | undefined) {
    if (!artifactId) {
      emit('update:selectedArtifact', null)
      focusedArtifactId.value = undefined
      return
    }

    const artifact = selectedTaskArtifacts.value.find((item) => item.id === artifactId) ?? null
    focusedArtifactId.value = artifactId
    emit('update:selectedArtifact', artifact)
    resetUploadSelection()
    activeStep.value = 'artifact'
  }

  function handleStepOptionSelect(optionId: string) {
    if (activeStep.value === 'group') {
      handleGroupSelect(optionId)
      return
    }

    if (activeStep.value === 'tool') {
      handleToolSelect(optionId)
      return
    }

    if (activeStep.value === 'task') {
      handleTaskSelect(optionId)
      return
    }

    handleArtifactSelect(optionId)
  }

  function handlePathSegmentClick(step: ArtifactPickerStep) {
    if (step === 'group') {
      selectedToolSlug.value = undefined
      selectedTaskId.value = undefined
      clearSelectedArtifactValue()
      activeStep.value = 'group'
      return
    }

    if (step === 'tool' && selectedGroupId.value) {
      selectedTaskId.value = undefined
      clearSelectedArtifactValue()
      activeStep.value = 'tool'
      return
    }

    if (step === 'task' && selectedToolSlug.value) {
      clearSelectedArtifactValue()
      activeStep.value = 'task'
      return
    }

    if (step === 'artifact' && selectedTaskId.value) {
      activeStep.value = 'artifact'
    }
  }

  function clearArtifactSelection() {
    clearSelectedArtifactValue()
    activeStep.value = selectedTaskId.value ? 'artifact' : 'task'
  }

  function currentSelectionState(): ArtifactPickerSelectionState {
    return {
      activeStep: activeStep.value,
      selectedGroupId: selectedGroupId.value,
      selectedToolSlug: selectedToolSlug.value,
      selectedTaskId: selectedTaskId.value,
      focusedArtifactId: focusedArtifactId.value
    }
  }

  function applySelectionState(nextState: ArtifactPickerSelectionState) {
    selectedGroupId.value = nextState.selectedGroupId
    selectedToolSlug.value = nextState.selectedToolSlug
    selectedTaskId.value = nextState.selectedTaskId
    focusedArtifactId.value = nextState.focusedArtifactId
    activeStep.value = nextState.activeStep
  }

  function syncSelectionPath() {
    applySelectionState(resolveArtifactPickerSelectionState({
      groupNodes: artifactGroupNodes.value,
      currentState: currentSelectionState(),
      allowArtifacts: props.allowArtifacts,
      selectedArtifact: props.selectedArtifact,
      preferredGroupId: props.preferredGroupId,
      preferredToolSlug: props.preferredToolSlug,
      currentToolSlug: props.currentToolSlug
    }))
  }

  function syncExternalSelectionPath(path: WorkflowArtifactSelectionPath | null) {
    applySelectionState(applyArtifactPickerExternalSelectionPath({
      groupNodes: artifactGroupNodes.value,
      currentState: currentSelectionState(),
      allowArtifacts: props.allowArtifacts,
      path
    }))
  }

  watch(
    () => [props.selectedArtifact, props.allowArtifacts, props.allowUploads] as const,
    () => {
      syncSourceMode()
    },
    { immediate: true }
  )

  watch(
    () => [
      props.selectedArtifact?.id,
      props.allowArtifacts,
      props.allowUploads,
      props.accept,
      props.currentToolSlug,
      props.preferredGroupId,
      props.preferredToolSlug,
      fingerprintArtifactPickerGroups(artifactGroupNodes.value)
    ] as const,
    () => {
      syncSelectionPath()
      syncExternalSelectionPath(props.externalSelectionPath ?? null)
    },
    { immediate: true }
  )

  watch(
    () => [
      props.externalSelectionPath?.token,
      props.externalSelectionPath?.groupId,
      props.externalSelectionPath?.toolSlug,
      props.externalSelectionPath?.taskId,
      props.externalSelectionPath?.artifactId
    ] as const,
    () => {
      syncExternalSelectionPath(props.externalSelectionPath ?? null)
    },
    { immediate: true }
  )

  watch(
    compatibleArtifacts,
    (nextArtifacts) => {
      if (props.selectedArtifact && !nextArtifacts.some((artifact) => artifact.id === props.selectedArtifact?.id)) {
        emit('update:selectedArtifact', null)
      }

      if (focusedArtifactId.value && !nextArtifacts.some((artifact) => artifact.id === focusedArtifactId.value)) {
        focusedArtifactId.value = undefined
      }
    }
  )

  onMounted(async () => {
    if (props.allowArtifacts && artifactsStore.items.length === 0) {
      await refreshArtifacts()
    }
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .artifact-file-picker {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .source-switch {
    width: fit-content;
  }

  .source-panel {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .artifact-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-sm;
  }

  .artifact-toolbar-label {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .artifact-flow {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .artifact-empty {
    padding: @spacing-md;
    border: 1px dashed #d8e1ee;
    border-radius: @border-radius-md;
    background: @accent-color-light;
  }

</style>
