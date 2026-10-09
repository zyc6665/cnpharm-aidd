<template>
  <div class="workflow-run-status-panel">
    <div class="run-status-header">
      <div class="run-status-title">
        <span>{{ t('workflow.canvasPresets.runStatus') }}</span>
        <strong>{{ run.name }}</strong>
      </div>
      <div class="run-status-actions">
        <a-tag :color="statusTone">{{ t(`workflow.runStatus.${run.status}`) }}</a-tag>
        <a-button
          class="sync-workflow-run"
          size="small"
          :loading="syncing"
          :disabled="syncing || isTerminal"
          @click="emit('sync')"
        >
          <template #icon><SyncOutlined /></template>
          {{ t('workflow.canvasPresets.syncRun') }}
        </a-button>
        <a-button
          class="cancel-workflow-run"
          size="small"
          danger
          :loading="canceling"
          :disabled="canceling || isTerminal"
          @click="emit('cancel')"
        >
          <template #icon><StopOutlined /></template>
          {{ t('workflow.canvasPresets.cancelRun') }}
        </a-button>
      </div>
    </div>

    <div class="run-status-progress">
      <a-progress :percent="summary.percent" :status="progressStatus" />
      <span>
        {{
          t('workflow.canvasPresets.nodeProgress', {
            completed: summary.completed,
            total: summary.total
          })
        }}
      </span>
    </div>

    <div class="run-node-list">
      <div v-for="(node, index) in summary.nodes" :key="node.id" class="run-node-row">
        <div class="run-node-status">
          <span class="run-node-index">{{ index + 1 }}</span>
          <a-tag :color="getWorkflowRunStatusTone(node.status)">
            {{ statusLabel(node.status) }}
          </a-tag>
        </div>
        <div class="run-node-main">
          <div class="run-node-heading">
            <strong class="run-node-title">{{ resolveNodeTitle(node) }}</strong>
            <span v-if="node.toolVersion" class="run-node-version">
              {{ t('workflow.canvasPresets.toolVersionValue', { version: node.toolVersion }) }}
            </span>
          </div>

          <div v-if="hasNodeSummary(node)" class="run-node-summary">
            <span v-if="node.inputCount" class="run-node-chip">
              {{ t('workflow.canvasPresets.inputBound', { count: node.inputCount }) }}
            </span>
            <span v-if="node.outputSemanticTypes.length" class="run-node-chip">
              {{ t('workflow.canvasPresets.outputSummary', { types: outputLabels(node) }) }}
            </span>
            <span v-for="parameter in node.parameters" :key="parameter.key" class="run-node-chip">
              {{ formatParameterLabel(parameter.key) }}：{{ parameter.value }}
            </span>
          </div>

          <div v-if="node.taskId" class="run-node-actions">
            <router-link class="run-node-action task-detail-link" :to="`/tasks/${node.taskId}`">
              {{ t('workflow.inspector.viewTaskDetail') }}
            </router-link>
            <router-link
              class="run-node-action node-task-list-link"
              :to="nodeTaskListPath(node.id, node.status)"
            >
              {{ t('workflow.canvasPresets.viewNodeTasks') }}
            </router-link>
          </div>

          <span v-if="node.missingOutputs.length" class="run-node-error">
            {{ t('workflow.canvasPresets.missingSemanticOutputs', { types: missingOutputLabels(node) }) }}
          </span>
          <span v-if="node.errorMessage" class="run-node-error">{{ node.errorMessage }}</span>
        </div>
        <a-button
          v-if="node.status === 'failure'"
          class="retry-workflow-node"
          size="small"
          type="link"
          :loading="retryingNodeId === node.id"
          :disabled="Boolean(retryingNodeId)"
          @click="emit('retryNode', node.id)"
        >
          <template #icon><RedoOutlined /></template>
          {{ t('workflow.canvasPresets.retryNode') }}
        </a-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { RedoOutlined, StopOutlined, SyncOutlined } from '@ant-design/icons-vue'
  import type { WorkflowRun } from '@/types/models'
  import type { WorkflowRunNodeSummary } from '@/workflow/workflow-runs'
  import {
    buildWorkflowRunSummary,
    getWorkflowRunStatusTone,
    isWorkflowRunTerminal
  } from '@/workflow/workflow-runs'

  const props = defineProps<{
    run: WorkflowRun
    syncing?: boolean
    canceling?: boolean
    retryingNodeId?: string | null
  }>()

  const emit = defineEmits<{
    sync: []
    cancel: []
    retryNode: [nodeId: string]
  }>()

  const { t, te } = useI18n()
  const summary = computed(() => buildWorkflowRunSummary(props.run))
  const statusTone = computed(() => getWorkflowRunStatusTone(props.run.status))
  const isTerminal = computed(() => isWorkflowRunTerminal(props.run.status))
  const progressStatus = computed(() => {
    if (props.run.status === 'failure') {
      return 'exception'
    }
    if (props.run.status === 'success') {
      return 'success'
    }
    return 'active'
  })

  const toolTitleKeys: Record<string, string> = {
    'builtin-fetch-pdb': 'workflow.canvasPresets.toolNames.fetchPdb',
    'builtin-protein-preparation': 'workflow.canvasPresets.toolNames.proteinPreparation',
    'builtin-ligand-preparation': 'workflow.canvasPresets.toolNames.ligandPreparation',
    'builtin-molecule-standardization': 'workflow.canvasPresets.toolNames.moleculeStandardization',
    'lvpocket-pocket-prediction': 'workflow.canvasPresets.toolNames.pocketPrediction',
    pocket2mol: 'workflow.canvasPresets.toolNames.moleculeGeneration',
    'molp-pc-admet': 'workflow.canvasPresets.toolNames.admetPrediction'
  }

  const semanticOutputKeys: Record<string, string> = {
    protein_pdb: 'workflow.canvasPresets.semanticOutputs.proteinStructure',
    protein_structure: 'workflow.canvasPresets.semanticOutputs.proteinStructure',
    'protein_structure@1': 'workflow.canvasPresets.semanticOutputs.proteinStructure',
    pocket_pdb: 'workflow.canvasPresets.semanticOutputs.pocketStructure',
    'pocket_structure@1': 'workflow.canvasPresets.semanticOutputs.pocketStructure',
    ligand_sdf: 'workflow.canvasPresets.semanticOutputs.ligandStructure',
    ligand_structure: 'workflow.canvasPresets.semanticOutputs.ligandStructure',
    'ligand_structure@1': 'workflow.canvasPresets.semanticOutputs.ligandStructure',
    molecule_table: 'workflow.canvasPresets.semanticOutputs.moleculeTable',
    'molecule_table@1': 'workflow.canvasPresets.semanticOutputs.moleculeTable',
    admet_table: 'workflow.canvasPresets.semanticOutputs.admetTable'
  }

  const parameterLabelKeys: Record<string, string> = {
    pdb_id: 'workflow.canvasPresets.parameterLabels.pdbId',
    ph: 'workflow.canvasPresets.parameterLabels.ph',
    remove_hs: 'workflow.canvasPresets.parameterLabels.removeHydrogens',
    neutralize: 'workflow.canvasPresets.parameterLabels.neutralize',
    generate_3d: 'workflow.canvasPresets.parameterLabels.generate3d'
  }

  function statusLabel(status: string): string {
    const key = `workflow.runStatus.${status}`
    return te(key) ? t(key) : status
  }

  function resolveNodeTitle(node: WorkflowRunNodeSummary): string {
    const knownTitleKey = node.toolSlug ? toolTitleKeys[node.toolSlug] : undefined
    if (knownTitleKey && te(knownTitleKey)) {
      return t(knownTitleKey)
    }

    if (node.nodeTitle) {
      if (te(node.nodeTitle)) {
        return t(node.nodeTitle)
      }
      if (!node.nodeTitle.includes('-')) {
        return node.nodeTitle
      }
    }

    const fallback = node.nodeTitle || node.toolSlug || t('workflow.canvasNode.titleFallback')
    return fallback
      .replace(/^builtin[-_]/i, '')
      .replace(/[-_]+/g, ' ')
      .replace(/\b\w/g, letter => letter.toUpperCase())
  }

  function resolveSemanticOutputLabel(semanticType: string): string {
    const key = semanticOutputKeys[semanticType]
    if (key && te(key)) {
      return t(key)
    }
    return semanticType
      .replace(/@\d+$/, '')
      .replace(/[-_]+/g, ' ')
      .replace(/\b\w/g, letter => letter.toUpperCase())
  }

  function outputLabels(node: WorkflowRunNodeSummary): string {
    return node.outputSemanticTypes.map(resolveSemanticOutputLabel).join(t('workflow.canvasPresets.valueSeparator'))
  }

  function missingOutputLabels(node: WorkflowRunNodeSummary): string {
    return node.missingOutputs
      .map(item => resolveSemanticOutputLabel(item.semantic_type))
      .join(t('workflow.canvasPresets.valueSeparator'))
  }

  function formatParameterLabel(parameterKey: string): string {
    const key = parameterLabelKeys[parameterKey]
    if (key && te(key)) {
      return t(key)
    }
    return parameterKey
      .replace(/[-_]+/g, ' ')
      .replace(/\b\w/g, letter => letter.toUpperCase())
  }

  function hasNodeSummary(node: WorkflowRunNodeSummary): boolean {
    return Boolean(node.inputCount || node.outputSemanticTypes.length || node.parameters.length)
  }

  function nodeTaskListPath(nodeId: string, nodeStatus: string): string {
    const params = new URLSearchParams({
      workflow_run_id: props.run.id,
      workflow_definition_id: props.run.workflow_definition_id,
      workflow_node_id: nodeId,
    })
    if (nodeStatus === 'failure') {
      params.set('view', 'needs_attention')
    }
    return `/tasks?${params.toString()}`
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-run-status-panel {
    margin: 0 @spacing-md @spacing-lg;
    padding: @spacing-md;
    border: 1px solid @border-color-hover;
    border-radius: @border-radius-lg;
    background: @bg-surface;
    box-shadow: 0 14px 28px rgb(15 23 42 / 5%);
  }

  .run-status-header {
    display: flex;
    justify-content: space-between;
    gap: @spacing-md;
    align-items: flex-start;
    margin-bottom: @spacing-sm;

    @media (max-width: @screen-sm) {
      flex-direction: column;
    }
  }

  .run-status-title {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;

    span {
      color: @text-color-light-secondary;
      font-size: @font-size-sm;
    }

    strong {
      color: @text-color-light;
      overflow-wrap: anywhere;
    }
  }

  .run-status-actions {
    display: flex;
    gap: @spacing-sm;
    align-items: center;
    flex-wrap: wrap;
  }

  .run-status-progress {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: @spacing-sm;
    align-items: center;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;

    @media (max-width: @screen-sm) {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  .run-node-list {
    display: grid;
    gap: @spacing-xs;
    margin-top: @spacing-sm;
  }

  .run-node-row {
    min-width: 0;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: @spacing-sm;
    align-items: start;
    padding: @spacing-sm;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    background: @bg-elevated;
  }

  .run-node-status {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: @spacing-xs;
  }

  .run-node-index {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    background: @bg-light-secondary;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    font-weight: 700;
  }

  .retry-workflow-node {
    align-self: center;
    padding-inline: 0;
  }

  .run-node-main {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;

    strong,
    span,
    a {
      overflow-wrap: anywhere;
    }
  }

  .run-node-heading {
    display: flex;
    align-items: baseline;
    gap: @spacing-sm;
    min-width: 0;
  }

  .run-node-title {
    color: @text-color-light;
    font-size: @font-size-md;
    line-height: 1.35;
  }

  .run-node-version {
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    white-space: nowrap;
  }

  .run-node-summary,
  .run-node-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: @spacing-xs;
  }

  .run-node-chip {
    padding: 3px @spacing-sm;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-sm;
    background: @bg-surface;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: 1.4;
  }

  .run-node-action {
    color: @primary-color;
    font-size: @font-size-xs;
  }

  .run-node-action + .run-node-action::before {
    margin-right: @spacing-xs;
    color: @text-color-light-tertiary;
    content: '·';
  }

  .run-node-error {
    color: @error-color;
    font-size: @font-size-xs;
    line-height: 1.5;
  }

  @media (max-width: @screen-sm) {
    .run-node-row {
      grid-template-columns: auto minmax(0, 1fr);
    }

    .retry-workflow-node {
      grid-column: 2;
      justify-self: start;
    }

    .run-node-version {
      white-space: normal;
    }
  }
</style>
