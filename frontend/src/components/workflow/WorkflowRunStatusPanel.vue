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
          @click="$emit('sync')"
        >
          <template #icon><SyncOutlined /></template>
          {{ t('workflow.canvasPresets.syncRun') }}
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
      <div v-for="node in summary.nodes" :key="node.id" class="run-node-row">
        <a-tag :color="getWorkflowRunStatusTone(node.status)">
          {{ t(`workflow.runStatus.${node.status}`) }}
        </a-tag>
        <div class="run-node-main">
          <strong>{{ node.toolSlug || node.id }}</strong>
          <span v-if="node.toolVersionId" class="run-node-meta">
            {{ t('workflow.canvasPresets.toolVersion', { id: node.toolVersionId }) }}
          </span>
          <span v-if="node.taskId">{{ t('workflow.canvasPresets.taskId', { id: node.taskId }) }}</span>
          <span v-if="node.inputFileIds.length" class="run-node-meta">
            {{ t('workflow.canvasPresets.inputFileIds', { ids: node.inputFileIds.join(', ') }) }}
          </span>
          <span v-if="node.outputSemanticTypes.length" class="run-node-meta">
            {{ t('workflow.canvasPresets.outputSemanticTypes', { types: node.outputSemanticTypes.join(', ') }) }}
          </span>
          <span v-if="node.paramsText" class="run-node-meta">{{ node.paramsText }}</span>
          <span v-if="node.missingOutputs.length" class="run-node-error">
            {{ t('workflow.canvasPresets.missingSemanticOutputs', { types: node.missingOutputs.map(item => item.semantic_type).join(', ') }) }}
          </span>
          <span v-if="node.errorMessage" class="run-node-error">{{ node.errorMessage }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { SyncOutlined } from '@ant-design/icons-vue'
  import type { WorkflowRun } from '@/types/models'
  import {
    buildWorkflowRunSummary,
    getWorkflowRunStatusTone,
    isWorkflowRunTerminal
  } from '@/workflow/workflow-runs'

  const props = defineProps<{
    run: WorkflowRun
    syncing?: boolean
  }>()

  defineEmits<{
    sync: []
  }>()

  const { t } = useI18n()
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
    grid-template-columns: auto minmax(0, 1fr);
    gap: @spacing-sm;
    align-items: start;
    padding: @spacing-xs @spacing-sm;
    border-radius: @border-radius-base;
    background: @bg-elevated;
  }

  .run-node-main {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;

    strong,
    span {
      overflow-wrap: anywhere;
    }

    span {
      color: @text-color-light-secondary;
      font-size: @font-size-sm;
    }
  }

  .run-node-error {
    color: @error-color;
  }

  .run-node-meta {
    color: @text-color-light-secondary;
  }
</style>
