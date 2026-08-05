<template>
  <div class="workflow-page">
    <div class="workflow-shell workflow-deck">
      <ProjectWorkspaceNav v-if="routeProjectId" :project-id="routeProjectId" />
      <AppPageHeader
        :title="t('workflow.title')"
        :subtitle="t('workflow.subtitle')"
        align="center"
      />

      <a-tabs v-model:activeKey="activeMode" class="workflow-mode-tabs">
        <a-tab-pane key="manual" :tab="t('workflow.mode.manual')">
          <div class="workflow-definition-bar">
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
            <a-tag v-if="routeProjectId" color="blue">项目工作流</a-tag>
            <a-space size="small" wrap>
              <a-button @click="handleNewWorkflow">
                {{ t('workflow.definition.new') }}
              </a-button>
              <a-button
                type="primary"
                :loading="workflowDefinitionsStore.saving"
                @click="handleSaveWorkflow"
              >
                保存
              </a-button>
              <a-button
                :disabled="!selectedSavedWorkflowId"
                :loading="workflowDefinitionsStore.loading"
                @click="handleLoadWorkflow"
              >
                加载
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
              <a-button
                :disabled="workflowStore.isRunningWorkflowDefinition"
                :loading="workflowStore.isRunningWorkflowDefinition"
                @click="handleRunWorkflowDefinition"
              >
                运行工作流
              </a-button>
            </a-space>
          </div>

          <WorkflowRunInputPanel
            :requirements="workflowInputRequirements"
            :artifact-requirements="workflowInputRequirementDetails"
            :selections="workflowRunInputSelections"
            :options-by-semantic-type="artifactOptionsBySemanticType"
            :loading="artifactsStore.loading"
            :auto-fill-disabled="artifactsStore.loading || artifactsStore.items.length === 0"
            @auto-fill="autofillWorkflowInputSelections"
            @select="handleWorkflowInputSelect"
          />

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

          <section class="workflow-preflight-region">
            <WorkflowPreflightPanel
              :preflight="workflowPreflight"
              :running="workflowStore.isRunningWorkflowDefinition"
              @run-ready-nodes="handleRunWorkflowDefinition"
              @select-node="workflowStore.setActiveNode"
            />
          </section>

          <div class="workflow-canvas-layout">
            <aside class="workflow-step-rail">
              <div class="workflow-status-summary">
                <div class="status-summary-item is-ready">
                  <span>可运行</span>
                  <strong>{{ readyNodeCount }}</strong>
                </div>
                <div class="status-summary-item is-blocked">
                  <span>阻塞</span>
                  <strong>{{ blockedNodeCount }}</strong>
                </div>
                <div class="status-summary-item is-running">
                  <span>运行中</span>
                  <strong>{{ runningNodeCount }}</strong>
                </div>
                <div class="status-summary-item is-completed">
                  <span>完成</span>
                  <strong>{{ completedNodeCount }}</strong>
                </div>
                <div class="status-summary-item is-failed">
                  <span>失败</span>
                  <strong>{{ failedNodeCount }}</strong>
                </div>
              </div>

              <div class="canvas-node-list">
                <button
                  v-for="node in editableCanvasPreset.nodes"
                  :key="node.id"
                  type="button"
                  class="canvas-node-item"
                  :class="{ 'is-active': node.id === activeNode?.id }"
                  @click="workflowStore.setActiveNode(node.id)"
                >
                  <span class="node-item-title">{{ formatKey(node.titleKey) }}</span>
                  <span class="node-item-reason">{{ resolveNodeStatusReason(node.id) }}</span>
                  <WorkflowNodeStatusBadge :status="nodeStatuses[node.id] ?? 'idle'" />
                </button>
              </div>

              <WorkflowToolPalette
                :search-keyword="sidebarToolSearchKeyword"
                :stage-options="sidebarStageOptions"
                :input-options="sidebarInputOptions"
                :output-options="sidebarOutputOptions"
                :executor-options="sidebarExecutorOptions"
                :stage-filter="sidebarStageFilter"
                :input-filter="sidebarInputFilter"
                :output-filter="sidebarOutputFilter"
                :executor-filter="sidebarExecutorFilter"
                :tools="filteredSidebarToolOptions"
                @update:search-keyword="sidebarToolSearchKeyword = $event"
                @update:stage-filter="sidebarStageFilter = $event"
                @update:input-filter="sidebarInputFilter = $event"
                @update:output-filter="sidebarOutputFilter = $event"
                @update:executor-filter="sidebarExecutorFilter = $event"
                @add-tool="handleAddToolNode"
              />
            </aside>

            <WorkflowCanvasBoard
              :preset="editableCanvasPreset"
              :active-node-id="activeNode?.id ?? null"
              :node-statuses="nodeStatuses"
              :node-positions="workflowStore.nodePositionById"
              @select-node="workflowStore.setActiveNode"
              @move-node="workflowStore.moveNode"
              @add-tool-node="handleAddToolNode"
              @delete-node="handleDeleteNode"
              @delete-edge="handleDeleteEdge"
              @add-edge="handleAddEdge"
            />

            <WorkflowNodeInspector
              :node="activeNode"
              :template="editableCanvasPreset"
              :artifacts="artifactsStore.items"
              :task-by-node="workflowStore.taskByNode"
              :available-tools="availableWorkflowTools"
              :status="activeNode ? nodeStatuses[activeNode.id] : 'idle'"
              :selected-tool-slug="activeNode ? selectedToolByActiveNode : null"
              :task="activeNode ? (workflowStore.taskByNode[activeNode.id] ?? null) : null"
              @select-tool="handleNodeToolSelect"
              @add-edge="handleAddEdge"
              @delete-edge="handleDeleteEdge"
              @run-node="handleRunWorkflowDefinition"
              @view-task-detail="handleViewTaskDetail"
            />
          </div>

          <section class="workflow-results-region">
            <WorkflowResultsReportPanel :workflow-name="workflowName" :rows="workflowReportRows" />
          </section>
        </a-tab-pane>

        <a-tab-pane key="agent" :tab="t('workflow.mode.agent')">
          <AiddAgentPanel />
        </a-tab-pane>
      </a-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { useRoute, useRouter } from 'vue-router'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import AiddAgentPanel from '@/components/workflow/AiddAgentPanel.vue'
  import WorkflowNodeInspector from '@/components/workflow/WorkflowNodeInspector.vue'
  import WorkflowNodeStatusBadge from '@/components/workflow/WorkflowNodeStatusBadge.vue'
  import WorkflowPreflightPanel from '@/components/workflow/WorkflowPreflightPanel.vue'
  import WorkflowResultsReportPanel from '@/components/workflow/WorkflowResultsReportPanel.vue'
  import WorkflowRunHistoryPanel from '@/components/workflow/WorkflowRunHistoryPanel.vue'
  import WorkflowRunInputPanel from '@/components/workflow/WorkflowRunInputPanel.vue'
  import WorkflowRunStatusPanel from '@/components/workflow/WorkflowRunStatusPanel.vue'
  import WorkflowCanvasBoard from '@/components/workflow/WorkflowCanvasBoard.vue'
  import WorkflowToolPalette from '@/components/workflow/WorkflowToolPalette.vue'
  import { useWorkflowCanvas } from '@/composables/useWorkflowCanvas'
  import { useWorkflowPersistence } from '@/composables/useWorkflowPersistence'
  import {
    buildWorkflowDefinitionListParams,
    buildWorkflowRunListParams,
    resolveWorkflowRouteProjectId
  } from '@/workflow/project-context'
  import { buildWorkflowPreflight } from '@/workflow/preflight'
  import type { AiddWorkflowDraft } from '@/types/models'
  import {
    useArtifactsStore,
    useToolsStore,
    useUserStore,
    useWorkflowDefinitionsStore,
    useWorkflowStore
  } from '@/stores'

  type WorkflowMode = 'manual' | 'agent'

  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()
  const artifactsStore = useArtifactsStore()
  const toolsStore = useToolsStore()
  const userStore = useUserStore()
  const workflowStore = useWorkflowStore()
  const workflowDefinitionsStore = useWorkflowDefinitionsStore()

  workflowStore.normalizeSessionShape()

  const activeMode = ref<WorkflowMode>('manual')
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
    sidebarExecutorFilter,
    editableCanvasPreset,
    activeNode,
    selectedToolByActiveNode,
    availableWorkflowTools,
    sidebarStageOptions,
    sidebarInputOptions,
    sidebarOutputOptions,
    sidebarExecutorOptions,
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
    resolveNodeStatusReason,
    handleNodeToolSelect,
    handleAddToolNode,
    handleDeleteNode,
    handleAddEdge,
    handleDeleteEdge,
    resolveToolForNode,
    formatKey,
    buildCurrentWorkflowDefinition
  } = useWorkflowCanvas({
    workflowStore,
    toolsStore,
    artifactsStore
  })

  const {
    workflowName,
    selectedSavedWorkflowId,
    workflowRunInputSelections,
    savedWorkflowOptions,
    selectedWorkflowInputFiles,
    artifactOptionsBySemanticType,
    handleSaveWorkflow,
    handleNewWorkflow,
    handleDuplicateWorkflow,
    handleArchiveWorkflow,
    handleDeleteWorkflow,
    applyWorkflowDraft,
    saveWorkflowDraft,
    handleRefreshWorkflowRuns,
    handleLoadMoreWorkflowRuns,
    handleRunWorkflowDefinition,
    handleWorkflowRunSelect,
    handleSyncWorkflowRun,
    handleCancelWorkflowRun,
    handleRetryWorkflowRunNode,
    handleWorkflowRunDetail,
    autofillWorkflowInputSelections,
    handleWorkflowInputSelect,
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
    buildCurrentWorkflowDefinition
  })

  const workflowPreflight = computed(() => {
    return buildWorkflowPreflight({
      template: editableCanvasPreset.value,
      nodeStatuses: nodeStatuses.value,
      readyNodeIds: readyToolNodeIds.value,
      selectedWorkflowInputFiles: selectedWorkflowInputFiles.value,
      artifacts: artifactsStore.items,
      taskByNode: workflowStore.taskByNode,
      selectedToolByNode: workflowStore.selectedToolByNode,
      toolsBySlug: availableWorkflowTools.value.reduce<
        Record<string, (typeof availableWorkflowTools.value)[number]>
      >((accumulator, tool) => {
        accumulator[tool.slug] = tool
        return accumulator
      }, {})
    })
  })

  async function handleAgentWorkflowDraft(draft: AiddWorkflowDraft, projectId?: string) {
    const targetProjectId = projectId ?? routeProjectId.value
    if (targetProjectId) {
      await saveWorkflowDraft(draft, targetProjectId)
    } else {
      applyWorkflowDraft(draft)
    }
    activeMode.value = 'manual'
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
    const boardDraft = sessionStorage.getItem('research-board-workflow-draft')
    if (boardDraft) {
      sessionStorage.removeItem('research-board-workflow-draft')
      handleAgentWorkflowDraft(JSON.parse(boardDraft) as AiddWorkflowDraft)
    }
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
    min-height: calc(100vh - @header-height - @footer-height);
    padding: @spacing-xl 0 @spacing-xxl;
    background:
      radial-gradient(circle at top, rgba(13, 110, 253, 0.08) 0%, rgba(255, 255, 255, 0) 32%),
      linear-gradient(180deg, rgba(59, 130, 246, 0.04) 0%, rgba(255, 255, 255, 0) 260px), @bg-light;
  }

  .workflow-shell {
    width: min(100%, calc(100vw - 32px));
    max-width: none;
    margin: 0 auto;
  }

  .workflow-deck {
    position: relative;
    padding: @spacing-sm;
    border-radius: 32px;
    background:
      linear-gradient(180deg, @bg-surface 0%, @bg-body 100%),
      linear-gradient(135deg, rgba(13, 110, 253, 0.04) 0%, rgba(46, 196, 182, 0.04) 100%);
    border: 1px solid @border-color;
    box-shadow: inset 0 1px 0 @border-color-hover;
  }

  .workflow-mode-tabs {
    :deep(.ant-tabs-nav) {
      margin: 0 0 @spacing-lg;
      padding: 0 @spacing-md;
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

  .workflow-definition-bar {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    padding: @spacing-md;
    margin-bottom: @spacing-md;
    border: 1px solid @border-color-hover;
    border-radius: @border-radius-md;
    background: @bg-elevated;
    box-shadow: @shadow-sm;
  }

  .workflow-name-input {
    width: min(280px, 100%);
  }

  .workflow-load-select {
    width: min(320px, 100%);
  }

  .workflow-preflight-region {
    margin-bottom: @spacing-md;
  }

  .workflow-canvas-layout {
    display: grid;
    grid-template-columns: minmax(220px, 260px) minmax(0, 1fr) minmax(300px, 360px);
    gap: @spacing-md;
    align-items: start;
  }

  .workflow-results-region {
    margin-top: @spacing-md;
  }

  .workflow-step-rail {
    min-width: 0;
    max-height: 720px;
    display: flex;
    flex-direction: column;
    border: 1px solid @border-color-hover;
    border-radius: @border-radius-md;
    background: @bg-light-secondary;
    box-shadow: @shadow-sm;
    overflow: hidden;
  }

  .canvas-preset-selector {
    padding: @spacing-md;
    border-bottom: 1px solid @border-color-light;
  }

  .rail-kicker {
    display: block;
    margin-bottom: @spacing-xs;
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: 800;
    letter-spacing: 0;
    text-transform: uppercase;
  }

  .canvas-preset-select {
    width: 100%;
  }

  .canvas-node-list {
    display: grid;
    gap: @spacing-xs;
    padding: @spacing-sm;
    max-height: 260px;
    overflow: auto;
  }

  .canvas-node-item {
    width: 100%;
    display: grid;
    gap: @spacing-xs;
    padding: @spacing-sm;
    border: 1px solid transparent;
    border-radius: @border-radius-sm;
    background: transparent;
    color: @text-color-light-primary;
    text-align: left;
    cursor: pointer;
  }

  .canvas-node-item:hover,
  .canvas-node-item.is-active {
    border-color: rgba(59, 130, 246, 0.16);
    background: @primary-color-light;
  }

  .node-item-title {
    min-width: 0;
    font-size: @font-size-sm;
    font-weight: 700;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .node-item-reason {
    min-width: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .workflow-status-summary {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: @spacing-xs;
    padding: @spacing-sm;
    border-bottom: 1px solid @border-color-light;
  }

  .status-summary-item {
    min-width: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-xs;
    padding: @spacing-xs @spacing-sm;
    border: 1px solid @accent-color-border;
    border-radius: @border-radius-sm;
    background: @bg-elevated;
  }

  .status-summary-item span {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .status-summary-item strong {
    color: @text-color-light-primary;
    font-size: @font-size-md;
  }

  .status-summary-item.is-ready strong {
    color: @success-color;
  }

  .status-summary-item.is-blocked strong {
    color: @warning-color;
  }

  .status-summary-item.is-running strong {
    color: @primary-color;
  }

  .status-summary-item.is-failed strong {
    color: @error-color;
  }

  @media (max-width: @screen-xl) {
    .workflow-canvas-layout {
      grid-template-columns: 220px minmax(0, 1fr);
    }

    .workflow-node-inspector {
      grid-column: 1 / -1;
    }
  }

  @media (max-width: @screen-md) {
    .workflow-definition-bar {
      align-items: stretch;
      flex-direction: column;
    }

    .workflow-name-input,
    .workflow-load-select {
      width: 100%;
    }

    .workflow-canvas-layout {
      grid-template-columns: 1fr;
    }
  }
</style>
