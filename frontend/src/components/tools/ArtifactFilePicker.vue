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
        <div class="artifact-path">
          <button
            v-for="segment in pathSegments"
            :key="segment.step"
            type="button"
            class="artifact-path-segment"
            :class="{
              'is-active': activeStep === segment.step,
              'is-complete': segment.complete
            }"
            :disabled="!segment.clickable"
            @click="handlePathSegmentClick(segment.step)"
          >
            <span class="artifact-path-kicker">{{ segment.label }}</span>
            <strong class="artifact-path-value">{{ segment.value }}</strong>
          </button>
        </div>

        <div class="artifact-step-panel">
          <div class="artifact-step-header">
            <div class="artifact-step-copy">
              <span class="artifact-step-kicker">{{ currentStepLabel }}</span>
              <strong class="artifact-step-title">{{ currentStepTitle }}</strong>
            </div>
            <a-tag class="artifact-step-count">{{ currentStepCount }}</a-tag>
          </div>

          <div v-if="activeStep === 'group'" class="artifact-step-list">
            <button
              v-for="groupNode in artifactGroupNodes"
              :key="groupNode.groupId"
              type="button"
              class="artifact-step-option"
              :class="{ 'is-selected': selectedGroupId === groupNode.groupId }"
              @click="handleGroupSelect(groupNode.groupId)"
            >
              <span class="artifact-step-option-copy">
                <strong class="artifact-step-option-title">
                  {{ groupNode.isUngrouped ? t('workflow.artifacts.ungroupedGroup') : groupNode.groupName }}
                </strong>
                <span class="artifact-step-option-meta">{{ t('tools.artifactGroupMeta') }}</span>
              </span>
              <a-tag class="artifact-step-option-count">{{ groupNode.tools.length }}</a-tag>
            </button>
          </div>

          <div v-else-if="activeStep === 'tool'" class="artifact-step-list">
            <button
              v-for="toolNode in selectedGroupTools"
              :key="toolNode.toolSlug"
              type="button"
              class="artifact-step-option"
              :class="{ 'is-selected': selectedToolSlug === toolNode.toolSlug }"
              @click="handleToolSelect(toolNode.toolSlug)"
            >
              <span class="artifact-step-option-copy">
                <strong class="artifact-step-option-title">{{ toolNode.toolName }}</strong>
                <span class="artifact-step-option-meta">{{ t('tools.artifactToolMeta') }}</span>
              </span>
              <a-tag class="artifact-step-option-count">{{ toolNode.tasks.length }}</a-tag>
            </button>
          </div>

          <div v-else-if="activeStep === 'task'" class="artifact-step-list">
            <button
              v-for="taskNode in selectedToolTasks"
              :key="taskNode.taskId"
              type="button"
              class="artifact-step-option"
              :class="{ 'is-selected': selectedTaskId === taskNode.taskId }"
              @click="handleTaskSelect(taskNode.taskId)"
            >
              <span class="artifact-step-option-copy">
                <strong class="artifact-step-option-title">#{{ taskNode.taskId }}</strong>
                <span class="artifact-step-option-meta">{{ formatTaskMeta(taskNode) }}</span>
              </span>
              <a-tag class="artifact-step-option-count">
                {{ t('workflow.artifacts.taskCount', { count: taskNode.artifacts.length }) }}
              </a-tag>
            </button>
          </div>

          <div v-else class="artifact-step-list">
            <button
              v-for="artifact in selectedTaskArtifacts"
              :key="artifact.id"
              type="button"
              class="artifact-step-option"
              :class="{
                'is-selected': selectedArtifact?.id === artifact.id,
                'is-focused': focusedArtifactId === artifact.id && selectedArtifact?.id !== artifact.id
              }"
              @click="handleArtifactSelect(artifact.id)"
            >
              <span class="artifact-step-option-copy">
                <strong class="artifact-step-option-title">{{ artifact.filename }}</strong>
                <span class="artifact-step-option-meta">{{ formatArtifactMeta(artifact) }}</span>
              </span>
              <a-tag v-if="selectedArtifact?.id === artifact.id" color="blue" class="artifact-step-option-count">
                {{ t('tools.artifactSelectedTag') }}
              </a-tag>
              <a-tag
                v-else-if="focusedArtifactId === artifact.id"
                color="gold"
                class="artifact-step-option-count"
              >
                {{ t('tools.artifactFocusTag') }}
              </a-tag>
            </button>
          </div>
        </div>

        <div class="artifact-selection-summary">
          <div class="artifact-selection-summary-copy">
            <span class="artifact-selection-summary-label">{{ summaryLabel }}</span>
            <strong class="artifact-selection-summary-title">{{ summaryTitle }}</strong>
            <p class="artifact-selection-summary-meta">{{ summaryMeta }}</p>
          </div>
          <a-button
            v-if="selectedArtifact"
            type="link"
            size="small"
            class="artifact-selection-summary-action"
            @click="clearArtifactSelection"
          >
            {{ t('tools.clearArtifactSelection') }}
          </a-button>
        </div>
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
  import {
    applyArtifactPickerExternalSelectionPath,
    buildArtifactPickerViewModel,
    formatArtifactPickerArtifactMeta,
    formatArtifactPickerTaskMeta,
    resolveArtifactPickerSelectionState,
    type ArtifactPickerSelectionState,
    type ArtifactPickerStep,
    type ArtifactPickerTaskNode
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
      currentToolId?: string | null
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
      currentToolId: null,
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
  const sourceMode = ref<'upload' | 'artifact'>('upload')
  const activeSourceMode = computed<'upload' | 'artifact'>(() => {
    if (!props.allowUploads && props.allowArtifacts) {
      return 'artifact'
    }

    if (!props.allowArtifacts && props.allowUploads) {
      return 'upload'
    }

    return sourceMode.value
  })
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
    noCompatibleArtifacts: t('tools.noCompatibleArtifacts')
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

  const selectedGroupNode = computed(() => pickerViewModel.value.selectedGroupNode)
  const selectedGroupTools = computed(() => pickerViewModel.value.selectedGroupTools)
  const selectedToolNode = computed(() => pickerViewModel.value.selectedToolNode)
  const selectedToolTasks = computed(() => pickerViewModel.value.selectedToolTasks)
  const selectedTaskNode = computed(() => pickerViewModel.value.selectedTaskNode)
  const selectedTaskArtifacts = computed(() => pickerViewModel.value.selectedTaskArtifacts)
  const compatibleArtifacts = computed(() => pickerViewModel.value.compatibleArtifacts)
  const pathSegments = computed(() => pickerViewModel.value.pathSegments)
  const currentStepLabel = computed(() => pickerViewModel.value.currentStep.label)
  const currentStepTitle = computed(() => pickerViewModel.value.currentStep.title)
  const currentStepCount = computed(() => pickerViewModel.value.currentStep.count)
  const summaryLabel = computed(() => pickerViewModel.value.summary.label)
  const summaryTitle = computed(() => pickerViewModel.value.summary.title)
  const summaryMeta = computed(() => pickerViewModel.value.summary.meta)

  function syncSourceMode() {
    if (!props.allowArtifacts) {
      sourceMode.value = 'upload'
      return
    }

    if (!props.allowUploads) {
      sourceMode.value = 'artifact'
      return
    }

    if (props.selectedArtifact) {
      sourceMode.value = 'artifact'
      return
    }

    sourceMode.value = 'upload'
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

  function handleSourceModeChange(value: 'upload' | 'artifact') {
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

  function formatArtifactMeta(artifact: ArtifactFile): string {
    return formatArtifactPickerArtifactMeta(artifact)
  }

  function formatTaskMeta(taskNode: ArtifactPickerTaskNode): string {
    return formatArtifactPickerTaskMeta(taskNode, selectedToolNode.value?.toolName)
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
      artifactGroupNodes.value
        .map((group) => `${group.groupId}:${group.tools.map((tool) => `${tool.toolSlug}:${tool.tasks.map((task) => task.taskId).join(',')}`).join('|')}`)
        .join(';')
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

  .artifact-path {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: @spacing-sm;
  }

  .artifact-path-segment {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    padding: @spacing-sm @spacing-md;
    border: 1px solid #d8e1ee;
    border-radius: @border-radius-md;
    background: @bg-elevated;
    text-align: left;
    transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
    cursor: pointer;
  }

  .artifact-path-segment:disabled {
    cursor: not-allowed;
    opacity: 0.72;
  }

  .artifact-path-segment:not(:disabled):hover {
    border-color: rgba(59, 130, 246, 0.35);
    box-shadow: 0 8px 18px rgb(24 144 255 / 8%);
    transform: translateY(-1px);
  }

  .artifact-path-segment.is-active {
    border-color: rgba(59, 130, 246, 0.45);
    box-shadow: 0 0 0 3px rgb(24 144 255 / 10%);
  }

  .artifact-path-segment.is-complete .artifact-path-value {
    color: @text-color-light-primary;
  }

  .artifact-path-kicker {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .artifact-path-value {
    overflow: hidden;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    font-weight: @font-weight-medium;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .artifact-step-panel {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
    padding: @spacing-md;
    border: 1px solid #d8e1ee;
    border-radius: @border-radius-md;
    background: linear-gradient(180deg, @bg-elevated 0%, @accent-color-light 100%);
  }

  .artifact-step-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: @spacing-sm;
  }

  .artifact-step-copy {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    min-width: 0;
  }

  .artifact-step-kicker {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .artifact-step-title {
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    font-weight: @font-weight-semibold;
  }

  .artifact-step-count {
    margin-inline-end: 0;
  }

  .artifact-step-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
  }

  .artifact-step-option {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: @spacing-sm;
    align-items: center;
    padding: @spacing-sm @spacing-md;
    border: 1px solid #e8edf5;
    border-radius: @border-radius-md;
    background: @bg-elevated;
    text-align: left;
    transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
    cursor: pointer;
  }

  .artifact-step-option:hover {
    border-color: rgba(59, 130, 246, 0.35);
    background: @accent-color-light;
  }

  .artifact-step-option.is-selected {
    border-color: rgba(59, 130, 246, 0.45);
    box-shadow: 0 0 0 3px rgb(24 144 255 / 10%);
  }

  .artifact-step-option.is-focused {
    border-color: rgba(250, 173, 20, 0.55);
    background: rgba(250, 173, 20, 0.12);
  }

  .artifact-step-option-copy {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    min-width: 0;
  }

  .artifact-step-option-title {
    overflow: hidden;
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .artifact-step-option-meta {
    overflow: hidden;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .artifact-step-option-count {
    margin-inline-end: 0;
    white-space: nowrap;
  }

  .artifact-selection-summary {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: @spacing-sm;
    padding: @spacing-md;
    border: 1px dashed #d8e1ee;
    border-radius: @border-radius-md;
    background: @accent-color-light;
  }

  .artifact-selection-summary-copy {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    min-width: 0;
  }

  .artifact-selection-summary-label {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .artifact-selection-summary-title {
    overflow: hidden;
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .artifact-selection-summary-meta {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: @line-height-base;
    overflow-wrap: anywhere;
  }

  .artifact-selection-summary-action {
    padding-inline: 0;
  }

  .artifact-empty {
    padding: @spacing-md;
    border: 1px dashed #d8e1ee;
    border-radius: @border-radius-md;
    background: @accent-color-light;
  }

  @media (max-width: @screen-md) {
    .artifact-path {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .artifact-step-option,
    .artifact-selection-summary {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
