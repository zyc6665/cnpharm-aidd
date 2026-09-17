<template>
  <aside class="workflow-workbench-rail">
    <div class="canvas-preset-selector">
      <span class="rail-kicker">{{ t('workflow.definition.templateLabel') }}</span>
      <a-select
        class="canvas-preset-select"
        data-testid="workflow-preset-select"
        :value="canvasPresetId"
        :options="canvasPresetOptions"
        @change="emit('update:canvasPresetId', $event)"
      />
    </div>

    <div class="workflow-status-summary">
      <div class="status-summary-item is-ready">
        <span>{{ t('workflow.statusSummary.ready') }}</span>
        <strong>{{ readyCount }}</strong>
      </div>
      <div class="status-summary-item is-blocked">
        <span>{{ t('workflow.statusSummary.blocked') }}</span>
        <strong>{{ blockedCount }}</strong>
      </div>
      <div class="status-summary-item is-running">
        <span>{{ t('workflow.statusSummary.running') }}</span>
        <strong>{{ runningCount }}</strong>
      </div>
      <div class="status-summary-item is-completed">
        <span>{{ t('workflow.statusSummary.completed') }}</span>
        <strong>{{ completedCount }}</strong>
      </div>
      <div class="status-summary-item is-failed">
        <span>{{ t('workflow.statusSummary.failed') }}</span>
        <strong>{{ failedCount }}</strong>
      </div>
    </div>

    <div class="canvas-node-list">
      <button
        v-for="node in nodes"
        :key="node.id"
        type="button"
        class="canvas-node-item"
        :class="{ 'is-active': node.id === activeNodeId }"
        @click="emit('select-node', node.id)"
      >
        <span class="node-item-title">{{ formatNodeTitle(node.titleKey) }}</span>
        <span class="node-item-reason">{{ resolveNodeStatusReason(node.id) }}</span>
        <WorkflowNodeStatusBadge :status="nodeStatuses[node.id] ?? 'idle'" />
      </button>
    </div>

    <WorkflowControlNodePalette @add-control-node="emit('add-control-node', $event)" />

    <WorkflowToolPalette
      :search-keyword="toolSearchKeyword"
      :stage-options="stageOptions"
      :input-options="inputOptions"
      :output-options="outputOptions"
      :executor-options="executorOptions"
      :stage-filter="stageFilter"
      :input-filter="inputFilter"
      :output-filter="outputFilter"
      :executor-filter="executorFilter"
      :tools="tools"
      @update:search-keyword="emit('update:toolSearchKeyword', $event)"
      @update:stage-filter="emit('update:stageFilter', $event)"
      @update:input-filter="emit('update:inputFilter', $event)"
      @update:output-filter="emit('update:outputFilter', $event)"
      @update:executor-filter="emit('update:executorFilter', $event)"
      @add-tool="emit('add-tool', $event)"
    />
  </aside>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import type { WorkflowStepStatus } from '@/workflow/artifact-types'
  import type { WorkflowCanvasNode, WorkflowCanvasNodeType } from '@/workflow/canvas-types'
  import WorkflowControlNodePalette from './WorkflowControlNodePalette.vue'
  import WorkflowNodeStatusBadge from './WorkflowNodeStatusBadge.vue'
  import WorkflowToolPalette from './WorkflowToolPalette.vue'

  interface SelectOption {
    value: string
    label: string
  }

  interface WorkflowWorkbenchRailTool {
    slug: string
    name: string
    description?: string
    category_id?: string
    category?: string
    tags?: Array<{ id?: string; name: string; color?: string }>
    capability?: string
    stage?: string
    executorType?: string
    resourceProfile?: Record<string, unknown>
  }

  defineProps<{
    canvasPresetId: string
    canvasPresetOptions: SelectOption[]
    nodes: readonly WorkflowCanvasNode[]
    activeNodeId?: string | null
    nodeStatuses: Record<string, WorkflowStepStatus>
    readyCount: number
    blockedCount: number
    runningCount: number
    completedCount: number
    failedCount: number
    toolSearchKeyword: string
    stageFilter?: string
    inputFilter?: string
    outputFilter?: string
    executorFilter?: string
    stageOptions: SelectOption[]
    inputOptions: SelectOption[]
    outputOptions: SelectOption[]
    executorOptions: SelectOption[]
    tools: WorkflowWorkbenchRailTool[]
    formatNodeTitle: (key: string) => string
    resolveNodeStatusReason: (nodeId: string) => string
  }>()

  const emit = defineEmits<{
    'update:canvasPresetId': [value: unknown]
    'update:toolSearchKeyword': [value: string]
    'update:stageFilter': [value: string | undefined]
    'update:inputFilter': [value: string | undefined]
    'update:outputFilter': [value: string | undefined]
    'update:executorFilter': [value: string | undefined]
    'select-node': [nodeId: string]
    'add-control-node': [type: Extract<WorkflowCanvasNodeType, 'condition' | 'map'>]
    'add-tool': [toolSlug: string]
  }>()

  const { t } = useI18n()
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-workbench-rail {
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
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
    max-height: 260px;
    padding: @spacing-sm;
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
    color: @text-color-light-primary;
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
</style>
