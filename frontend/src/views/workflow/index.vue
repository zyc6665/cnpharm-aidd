<template>
  <div class="workflow-page">
    <div class="workflow-shell">
      <ProjectWorkspaceNav v-if="routeProjectId" :project-id="routeProjectId" />

      <AppPageHeader
        :title="t('workflow.advanced.title')"
        :subtitle="t('workflow.advanced.subtitle')"
        align="center"
      />

      <div class="workflow-deck">
          <WorkflowWorkbenchShell
            :workflow-name="workflowName"
            :ready-count="readyNodeCount"
            :running-count="runningNodeCount"
            :completed-count="completedNodeCount"
            :failed-count="failedNodeCount"
            :left-width="leftWorkbenchWidth"
            :right-width="rightWorkbenchWidth"
            :left-collapsed="leftWorkbenchCollapsed"
            :right-collapsed="rightWorkbenchCollapsed"
            @update:left-width="setLeftWorkbenchWidth"
            @update:right-width="setRightWorkbenchWidth"
            @update:left-collapsed="leftWorkbenchCollapsed = $event"
            @update:right-collapsed="rightWorkbenchCollapsed = $event"
          >
            <template #actions>
              <a-input
                :value="workflowName"
                class="workflow-name-input"
                :placeholder="t('workflow.definition.namePlaceholder')"
                @update:value="workflowName = $event"
              />
              <a-select
                :value="selectedSavedWorkflowId"
                class="workflow-load-select"
                allow-clear
                :placeholder="t('workflow.definition.loadPlaceholder')"
                :loading="workflowDefinitionsStore.loading"
                :options="savedWorkflowOptions"
                @change="selectedSavedWorkflowId = $event"
              />
              <a-button @click="handleNewWorkflow">
                {{ t('workflow.definition.new') }}
              </a-button>
              <a-button
                type="primary"
                :loading="workflowDefinitionsStore.saving"
                @click="handleSaveWorkflow"
              >
                {{ t('workflow.definition.save') }}
              </a-button>
              <a-button
                :disabled="!selectedSavedWorkflowId"
                :loading="workflowDefinitionsStore.loading"
                @click="handleLoadWorkflow"
              >
                {{ t('workflow.definition.load') }}
              </a-button>
              <a-button
                :disabled="!selectedSavedWorkflowId"
                :loading="workflowDefinitionsStore.saving"
                @click="handleDuplicateWorkflow"
              >
                {{ t('workflow.definition.duplicate') }}
              </a-button>
              <a-popconfirm
                :title="t('workflow.definition.archiveConfirm')"
                :ok-text="t('workflow.definition.archive')"
                :cancel-text="t('common.cancel')"
                @confirm="handleArchiveWorkflow"
              >
                <a-button
                  :disabled="!selectedSavedWorkflowId"
                  :loading="workflowDefinitionsStore.loading"
                >
                  {{ t('workflow.definition.archive') }}
                </a-button>
              </a-popconfirm>
              <a-popconfirm
                :title="t('workflow.canvasPresets.deleteConfirm')"
                :ok-text="t('common.delete')"
                :cancel-text="t('common.cancel')"
                ok-type="danger"
                @confirm="handleDeleteWorkflow"
              >
                <a-button
                  danger
                  :disabled="!selectedSavedWorkflowId"
                  :loading="workflowDefinitionsStore.loading"
                >
                  {{ t('workflow.definition.delete') }}
                </a-button>
              </a-popconfirm>
              <a-tag v-if="routeProjectId" color="blue">{{ t('workflow.definition.projectScoped') }}</a-tag>
              <a-button
                :disabled="workflowStore.isRunningWorkflowDefinition"
                :loading="workflowStore.isRunningWorkflowDefinition"
                @click="handleRunWorkflowDefinition"
              >
                {{ t('workflow.definition.startFullRun') }}
              </a-button>
            </template>

            <template #left>
              <WorkflowWorkbenchRail
                :canvas-preset-id="workflowStore.canvasPresetId"
                :canvas-preset-options="canvasPresetOptions"
                :nodes="editableCanvasPreset.nodes"
                :active-node-id="activeNode?.id ?? null"
                :node-statuses="nodeStatuses"
                :ready-count="readyNodeCount"
                :blocked-count="blockedNodeCount"
                :running-count="runningNodeCount"
                :completed-count="completedNodeCount"
                :failed-count="failedNodeCount"
                :tool-search-keyword="sidebarToolSearchKeyword"
                :stage-options="sidebarStageOptions"
                :input-options="sidebarInputOptions"
                :output-options="sidebarOutputOptions"
                :stage-filter="sidebarStageFilter"
                :input-filter="sidebarInputFilter"
                :output-filter="sidebarOutputFilter"
                :tools="filteredSidebarToolOptions"
                :format-node-title="formatKey"
                :resolve-node-status-reason="resolveNodeStatusReason"
                @update:canvas-preset-id="handleCanvasPresetChangeGuarded"
                @update:tool-search-keyword="sidebarToolSearchKeyword = $event"
                @update:stage-filter="sidebarStageFilter = $event"
                @update:input-filter="sidebarInputFilter = $event"
                @update:output-filter="sidebarOutputFilter = $event"
                @select-node="workflowStore.setActiveNode"
                @add-control-node="handleAddControlNode"
                @add-tool="handleAddToolNode"
              />
            </template>

            <template #canvas>
            <WorkflowCanvasBoard
              :preset="editableCanvasPreset"
              :active-node-id="activeNode?.id ?? null"
              :node-statuses="nodeStatuses"
              :node-positions="workflowStore.nodePositionById"
              :task-by-node="workflowStore.taskByNode"
              :artifacts="artifactsStore.items"
              @select-node="workflowStore.setActiveNode"
              @configure-node="handleConfigureWorkflowNode"
              @move-node="workflowStore.moveNode"
              @add-tool-node="handleAddToolNode"
              @delete-node="handleDeleteNode"
              @delete-edge="handleDeleteEdge"
              @add-edge="handleAddEdge"
            />
            </template>

            <template #right>
              <WorkflowResultsSidebar>
                <template #node>
                  <WorkflowNodeInspector
                    ref="workflowNodeInspector"
                    :node="activeNode"
                    :project-id="routeProjectId"
                    :template="editableCanvasPreset"
                    :artifacts="artifactsStore.items"
                    :task-by-node="workflowStore.taskByNode"
                    :available-tools="availableWorkflowTools"
                    :status="activeNode ? nodeStatuses[activeNode.id] : 'idle'"
                    :selected-tool-slug="activeNode ? selectedToolByActiveNode : null"
                    :task="activeNode ? (workflowStore.taskByNode[activeNode.id] ?? null) : null"
                    :input-requirements="workflowInputRequirementDetails"
                    :input-selections="workflowRunInputSelections"
                    :input-options-by-semantic-type="artifactOptionsBySemanticType"
                    :input-options-loading="workflowInputOptionsLoading"
                    :can-upload-input="userStore.isLoggedIn"
                    :uploading-input-key="uploadingWorkflowInputKey"
                    @select-tool="handleNodeToolSelect"
                    @update-node="workflowStore.updateCanvasNode"
                    @add-edge="handleAddEdge"
                    @delete-edge="handleDeleteEdge"
                    @update-edge-branch="handleUpdateWorkflowEdgeBranch"
                    @view-task-detail="handleViewTaskDetail"
                    @select-input="handleWorkflowInputSelect"
                    @upload-input="handleWorkflowInputUpload"
                  />
                </template>

                <template #inputs>
                <WorkflowRunInputPanel
                  :requirements="workflowInputRequirements"
                  :artifact-requirements="workflowInputRequirementDetails"
                  :selections="workflowRunInputSelections"
                  :options-by-semantic-type="artifactOptionsBySemanticType"
                  :loading="workflowInputOptionsLoading"
                  :auto-fill-disabled="workflowInputOptionsLoading || !hasWorkflowInputOptions"
                  :can-upload="userStore.isLoggedIn"
                  :uploading-key="uploadingWorkflowInputKey"
                  @auto-fill="autofillWorkflowInputSelections"
                  @select="handleWorkflowInputSelect"
                  @upload="handleWorkflowInputUpload"
                />
                </template>

                <template #preflight>
                <WorkflowPreflightPanel
                  :preflight="workflowPreflight"
                  :running="workflowStore.isRunningWorkflowDefinition"
                  :repairable-count="workflowRepairableCount"
                  :repair-actions="workflowRepairActions"
                  @run-ready-nodes="handleRunWorkflowDefinition"
                  @apply-auto-repair="handleApplyWorkflowAutoRepair"
                  @select-node="workflowStore.setActiveNode"
                />
                </template>

                <template #report>
                <WorkflowRunStatusPanel
                  v-if="workflowStore.activeWorkflowRun"
                  :run="workflowStore.activeWorkflowRun"
                  :syncing="workflowStore.isSyncingWorkflowRun || workflowStore.isLoadingWorkflowRun"
                  :canceling="workflowStore.isCancelingWorkflowRun"
                  :retrying-node-id="workflowStore.retryingWorkflowRunNodeId"
                  @sync="handleSyncWorkflowRun"
                  @cancel="handleCancelWorkflowRun"
                  @retry-node="handleRetryWorkflowRunNode"
                />

                  <WorkflowResultsReportPanel :workflow-name="workflowName" :rows="workflowReportRows" />
                </template>

                <template #artifacts>
                  <WorkflowArtifactPanel
                    :selected-tool-slug="activeNode ? selectedToolByActiveNode : null"
                    :active-task="activeNode ? (workflowStore.taskByNode[activeNode.id] ?? null) : null"
                  />
                </template>

                <template #history>
                <WorkflowRunHistoryPanel
                  v-if="userStore.isLoggedIn"
                  :runs="workflowStore.workflowRuns"
                  :active-run-id="workflowStore.activeWorkflowRunId"
                  :loading="workflowStore.isLoadingWorkflowRuns"
                  :has-more="workflowStore.hasMoreWorkflowRuns"
                  :loading-more="workflowStore.isLoadingMoreWorkflowRuns"
                  @select="handleWorkflowRunSelect"
                  @view-detail="handleWorkflowRunDetail"
                  @refresh="handleRefreshWorkflowRuns"
                  @load-more="handleLoadMoreWorkflowRuns"
                />
                </template>
              </WorkflowResultsSidebar>
            </template>
          </WorkflowWorkbenchShell>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { useRoute, useRouter } from 'vue-router'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import WorkflowArtifactPanel from '@/components/workflow/WorkflowArtifactPanel.vue'
  import WorkflowNodeInspector from '@/components/workflow/WorkflowNodeInspector.vue'
  import WorkflowPreflightPanel from '@/components/workflow/WorkflowPreflightPanel.vue'
  import WorkflowResultsReportPanel from '@/components/workflow/WorkflowResultsReportPanel.vue'
  import WorkflowRunHistoryPanel from '@/components/workflow/WorkflowRunHistoryPanel.vue'
  import WorkflowRunInputPanel from '@/components/workflow/WorkflowRunInputPanel.vue'
  import WorkflowRunStatusPanel from '@/components/workflow/WorkflowRunStatusPanel.vue'
  import WorkflowCanvasBoard from '@/components/workflow/WorkflowCanvasBoard.vue'
  import WorkflowResultsSidebar from '@/components/workflow/WorkflowResultsSidebar.vue'
  import WorkflowWorkbenchShell from '@/components/workflow/WorkflowWorkbenchShell.vue'
  import WorkflowWorkbenchRail from '@/components/workflow/WorkflowWorkbenchRail.vue'
  import { useWorkflowCanvas } from '@/composables/useWorkflowCanvas'
  import { useWorkflowNodeTaskPolling } from '@/composables/useWorkflowNodeTaskPolling'
  import { useWorkflowPersistence } from '@/composables/useWorkflowPersistence'
  import { useWorkflowWorkbenchLayout } from '@/composables/useWorkflowWorkbenchLayout'
  import {
    buildWorkflowDefinitionListParams,
    buildWorkflowRunListParams,
    resolveWorkflowRouteProjectId
  } from '@/workflow/project-context'
  import { buildWorkflowPreflight } from '@/workflow/preflight'
  import { buildWorkflowPreflightLabels } from '@/workflow/preflight-labels'
  import {
    useArtifactsStore,
    useToolsStore,
    useUserStore,
    useWorkflowDefinitionsStore,
    useWorkflowStore
  } from '@/stores'

  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()
  const artifactsStore = useArtifactsStore()
  const toolsStore = useToolsStore()
  const userStore = useUserStore()
  const workflowStore = useWorkflowStore()
  const workflowDefinitionsStore = useWorkflowDefinitionsStore()
  const workflowNodeInspector = ref<{ focusConfiguration: () => void } | null>(null)

  workflowStore.normalizeSessionShape()

  const routeProjectId = computed(() =>
    resolveWorkflowRouteProjectId({
      paramsProjectId: route.params?.projectId,
      queryProjectId: route.query.project_id
    })
  )

  const {
    sidebarToolSearchKeyword,
    sidebarStageFilter,
    sidebarInputFilter,
    sidebarOutputFilter,
    editableCanvasPreset,
    activeNode,
    selectedToolByActiveNode,
    canvasPresetOptions,
    availableWorkflowTools,
    sidebarStageOptions,
    sidebarInputOptions,
    sidebarOutputOptions,
    filteredSidebarToolOptions,
    workflowInputRequirements,
    workflowInputRequirementDetails,
    nodeStatuses,
    readyToolNodeIds,
    readyNodeCount,
    blockedNodeCount,
    runningNodeCount,
    completedNodeCount,
    failedNodeCount,
    workflowReportRows,
    workflowRepairActions,
    workflowRepairableCount,
    handleCanvasPresetChange: setCanvasPreset,
    resolveNodeStatusReason,
    handleNodeToolSelect,
    handleAddToolNode,
    handleApplyWorkflowAutoRepair,
    handleAddControlNode,
    handleDeleteNode,
    handleAddEdge,
    handleDeleteEdge,
    formatKey,
    buildCurrentWorkflowDefinition
  } = useWorkflowCanvas({
    workflowStore,
    toolsStore,
    artifactsStore
  })

  const workflowToolsBySlug = computed(() => availableWorkflowTools.value.reduce<
    Record<string, (typeof availableWorkflowTools.value)[number]>
  >((accumulator, tool) => {
    accumulator[tool.slug] = tool
    return accumulator
  }, {}))

  const workflowPersistenceLabels = computed(() => ({
    untitledWorkflow: t('workflow.persistence.untitledWorkflow'),
    duplicateName: (name: string) => t('workflow.persistence.duplicateName', { name }),
    saved: t('workflow.persistence.saved'),
    duplicated: t('workflow.persistence.duplicated'),
    archived: t('workflow.persistence.archived'),
    deleted: t('workflow.persistence.deleted'),
    draftSaved: t('workflow.persistence.draftSaved'),
    runCanceled: t('workflow.persistence.runCanceled'),
    nodeRetried: t('workflow.persistence.nodeRetried'),
    loaded: t('workflow.persistence.loaded'),
    discardUnsavedTitle: t('workflow.persistence.discardUnsavedTitle'),
    discardUnsavedContent: t('workflow.persistence.discardUnsavedContent'),
    discardUnsavedConfirm: t('workflow.persistence.discardUnsavedConfirm'),
    discardUnsavedCancel: t('workflow.persistence.discardUnsavedCancel'),
    missingInputs: (inputs: string[]) => t('workflow.canvasPresets.missingInputs', { inputs: inputs.join(', ') }),
  }))

  const workflowPreflightLabels = computed(() => buildWorkflowPreflightLabels((key, params) => t(key, params ?? {})))

  const {
    leftWidth: leftWorkbenchWidth,
    rightWidth: rightWorkbenchWidth,
    leftCollapsed: leftWorkbenchCollapsed,
    rightCollapsed: rightWorkbenchCollapsed,
    setLeftWidth: setLeftWorkbenchWidth,
    setRightWidth: setRightWorkbenchWidth,
  } = useWorkflowWorkbenchLayout({
    left: { defaultWidth: 320, minWidth: 280, maxWidth: 480 },
    right: { defaultWidth: 380, minWidth: 320, maxWidth: 560 },
  })

  const {
    workflowName,
    selectedSavedWorkflowId,
    workflowRunInputSelections,
    savedWorkflowOptions,
    selectedWorkflowInputFiles,
    artifactOptionsBySemanticType,
    workflowInputOptionsLoading,
    hasWorkflowInputOptions,
    uploadingWorkflowInputKey,
    handleSaveWorkflow,
    handleNewWorkflow,
    handleDuplicateWorkflow,
    handleArchiveWorkflow,
    handleDeleteWorkflow,
    handleRefreshWorkflowRuns,
    handleLoadMoreWorkflowRuns,
    handleRunWorkflowDefinition,
    handleWorkflowRunSelect,
    handleSyncWorkflowRun,
    handleCancelWorkflowRun,
    handleRetryWorkflowRunNode,
    handleWorkflowRunDetail,
    confirmDiscardWorkflowChanges,
    autofillWorkflowInputSelections,
    handleWorkflowInputSelect,
    handleWorkflowInputUpload,
    scheduleWorkflowRunAutoSync,
    clearWorkflowRunAutoSync,
    restoreActiveWorkflowRun,
    handleLoadWorkflow
  } = useWorkflowPersistence({
    userStore,
    artifactsStore,
    workflowStore,
    workflowDefinitionsStore,
    editableCanvasPreset,
    projectId: routeProjectId,
    workflowInputRequirements,
    workflowToolsBySlug,
    buildCurrentWorkflowDefinition,
    labels: workflowPersistenceLabels
  })

  const workflowPreflight = computed(() => {
    return buildWorkflowPreflight({
      template: editableCanvasPreset.value,
      nodeStatuses: nodeStatuses.value,
      readyNodeIds: readyToolNodeIds.value,
      requiredWorkflowInputs: workflowInputRequirements.value,
      selectedWorkflowInputFiles: selectedWorkflowInputFiles.value,
      artifacts: artifactsStore.items,
      artifactBindingsByNode: workflowStore.artifactBindingsByNode,
      taskByNode: workflowStore.taskByNode,
      workflowRunNodeStates: workflowStore.activeWorkflowRun?.node_states,
      selectedToolByNode: workflowStore.selectedToolByNode,
      toolsBySlug: workflowToolsBySlug.value,
      labels: workflowPreflightLabels.value
    })
  })

  useWorkflowNodeTaskPolling({
    taskByNode: computed(() => workflowStore.taskByNode),
    recordNodeTask: workflowStore.recordNodeTask,
    refreshArtifacts: () => artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
  })

  async function handleCanvasPresetChangeGuarded(canvasPresetId: unknown) {
    if (typeof canvasPresetId !== 'string') return
    if (!await confirmDiscardWorkflowChanges()) return
    setCanvasPreset(canvasPresetId)
  }

  function handleConfigureWorkflowNode(nodeId: string) {
    workflowStore.setActiveNode(nodeId)
    workflowNodeInspector.value?.focusConfiguration()
  }

  function handleUpdateWorkflowEdgeBranch(edgeId: string, branch: 'true' | 'false' | undefined) {
    workflowStore.updateCanvasEdge(edgeId, { branch })
  }

  function handleViewTaskDetail(nodeId: string) {
    const taskId = workflowStore.taskByNode[nodeId]?.id
    if (!taskId) {
      return
    }

    router.push(`/tasks/${taskId}`)
  }

  watch(
    () => [userStore.authReady, userStore.isLoggedIn, userStore.user?.id, routeProjectId.value] as const,
    async ([authReady, isLoggedIn, userId, projectId]) => {
      if (!authReady) {
        return
      }

      workflowStore.syncOwnerUserId(isLoggedIn ? (userId ?? undefined) : undefined)

      if (!isLoggedIn) {
        artifactsStore.resetArtifacts()
        workflowDefinitionsStore.clearCurrentWorkflowDefinition()
        selectedSavedWorkflowId.value = undefined
        clearWorkflowRunAutoSync()
        return
      }

      await Promise.allSettled([
        artifactsStore.fetchArtifacts({ page: 1, page_size: 100 }),
        workflowDefinitionsStore.fetchWorkflowDefinitions(
          buildWorkflowDefinitionListParams(projectId)
        ),
        workflowStore.loadWorkflowRuns(
          buildWorkflowRunListParams({ projectId, page: 1, pageSize: 20 })
        )
      ])
    },
    { immediate: true }
  )

  watch(
    () => workflowStore.activeWorkflowRunId,
    async () => {
      await scheduleWorkflowRunAutoSync()
    }
  )

  onMounted(async () => {
    await Promise.allSettled([toolsStore.fetchWorkbenchGroups(), toolsStore.fetchWorkflowTools()])
  })

  onMounted(async () => {
    await restoreActiveWorkflowRun()
  })

  onBeforeUnmount(() => {
    clearWorkflowRunAutoSync()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-page {
    min-height: calc(100vh - @header-height);
    padding: 0;
    background: @bg-light;
  }

  .workflow-shell {
    width: 100%;
    max-width: none;
    margin: 0 auto;
  }

  .workflow-deck {
    position: relative;
    padding: @spacing-sm;
    border-radius: 32px;
    background:
      linear-gradient(180deg, @bg-surface 0%, @bg-body 100%),
      linear-gradient(135deg, @accent-color-light 0%, @success-color-light 100%);
    border: 1px solid @border-color;
    box-shadow: inset 0 1px 0 @border-color-hover;
  }

  .workflow-mode-tabs {
    min-height: calc(100vh - @header-height);

    :deep(.ant-tabs-nav) {
      margin: 0;
      padding: 0 @spacing-md;
      background: @bg-surface;
      border-bottom: 1px solid @border-color-light;
    }

    :deep(.ant-tabs-content-holder),
    :deep(.ant-tabs-content),
    :deep(.ant-tabs-tabpane) {
      min-height: 0;
    }

    :deep(.ant-tabs-tab) {
      padding: @spacing-sm @spacing-md;
      color: @text-color-light-secondary;
      font-weight: 600;
      letter-spacing: 0;
    }

    :deep(.ant-tabs-tab-active .ant-tabs-tab-btn) {
      color: @primary-color;
      font-weight: 700;
    }
  }

  .workflow-name-input {
    width: min(280px, 100%);
  }

  .workflow-load-select {
    width: min(320px, 100%);
  }

  .workflow-workbench :deep(.workflow-results-sidebar) {
    height: 100%;
  }

  .workflow-workbench :deep(.workflow-node-inspector) {
    max-height: none;
    border-radius: @border-radius-sm;
  }

  .workflow-workbench :deep(.workflow-results-report-panel) {
    margin-top: 0;
  }

  .workflow-workbench :deep(.workflow-run-history-panel),
  .workflow-workbench :deep(.workflow-run-input-panel) {
    margin: 0;
  }

  .workflow-workbench :deep(.workflow-column) {
    min-width: 0;
  }

  .workflow-workbench :deep(.workflow-canvas-board) {
    height: 100%;
    border: 0;
    border-radius: 0;
    box-shadow: none;
  }

  .workflow-workbench :deep(.canvas-viewport) {
    flex: 1;
    min-height: 0;
  }
</style>
