<template>
  <section class="workflow-preflight-panel">
    <div class="preflight-header">
      <div>
        <span class="preflight-kicker">{{ t('workflow.preflight.title') }}</span>
        <h3>{{ preflight.primaryMessage }}</h3>
      </div>
      <a-space size="small" wrap>
        <a-tag color="green">{{ t('workflow.preflight.readyCount', { count: preflight.runnableCount }) }}</a-tag>
        <a-tag color="orange">{{ t('workflow.preflight.blockedCount', { count: preflight.blockedCount }) }}</a-tag>
        <a-tag color="blue">{{ t('workflow.preflight.completedCount', { count: preflight.completedCount }) }}</a-tag>
        <a-tag v-if="preflight.failedCount" color="red">{{ t('workflow.preflight.failedCount', { count: preflight.failedCount }) }}</a-tag>
      </a-space>
    </div>

    <div class="preflight-body">
      <div class="preflight-summary">
        <strong>{{ t('workflow.preflight.summaryTitle') }}</strong>
        <p>{{ summaryHint }}</p>
      </div>

      <div class="preflight-issues">
        <div v-if="preflight.issues.length === 0" class="preflight-empty">
          {{ t('workflow.preflight.noIssues') }}
        </div>
        <div
          v-for="issue in preflight.issues"
          :key="issue.id"
          class="preflight-issue"
          :class="`is-${issue.severity}`"
        >
          <div class="issue-copy">
            <span class="issue-node">{{ issue.nodeTitle }}</span>
            <strong>{{ issue.title }}</strong>
            <p>{{ issue.detail }}</p>
          </div>
          <a-button size="small" @click="$emit('select-node', issue.nodeId)">
            {{ t('workflow.preflight.viewNode') }}
          </a-button>
        </div>
      </div>
    </div>

    <div class="preflight-actions">
      <a-button
        type="primary"
        :disabled="!preflight.canRun"
        :loading="running"
        @click="$emit('run-ready-nodes')"
      >
        {{ t('workflow.preflight.runReadyNodes') }}
      </a-button>
      <span class="preflight-action-hint">
        {{ t('workflow.preflight.runHint') }}
      </span>
    </div>
  </section>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import type { WorkflowPreflightSummary } from '@/workflow/preflight'

  const props = defineProps<{
    preflight: WorkflowPreflightSummary
    running?: boolean
  }>()

  defineEmits<{
    (event: 'run-ready-nodes'): void
    (event: 'select-node', nodeId: string): void
  }>()
  const { t } = useI18n()

  const summaryHint = computed(() => {
    if (props.preflight.runningCount > 0) {
      return t('workflow.preflight.hintRunning')
    }
    if (props.preflight.runnableCount > 0 && props.preflight.blockedCount > 0) {
      return t('workflow.preflight.hintBlocked')
    }
    if (props.preflight.runnableCount > 0) {
      return t('workflow.preflight.hintReady')
    }
    return t('workflow.preflight.hintEmpty')
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-preflight-panel {
    border: 1px solid rgba(24, 144, 255, 0.12);
    border-radius: @border-radius-md;
    background: rgba(255, 255, 255, 0.96);
    box-shadow: @shadow-sm;
    overflow: hidden;
  }

  .preflight-header,
  .preflight-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    padding: @spacing-md @spacing-lg;
  }

  .preflight-header {
    border-bottom: 1px solid @border-color-light;
  }

  .preflight-kicker {
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: 800;
  }

  .preflight-header h3 {
    margin: 2px 0 0;
    color: @text-color-light-primary;
    font-size: @font-size-lg;
    font-weight: 800;
  }

  .preflight-body {
    display: grid;
    grid-template-columns: minmax(220px, 0.32fr) minmax(0, 1fr);
    gap: @spacing-md;
    padding: @spacing-lg;
  }

  .preflight-summary {
    padding: @spacing-md;
    border-radius: @border-radius-sm;
    background: @bg-light-secondary;
  }

  .preflight-summary strong {
    color: @text-color-light-primary;
    font-size: @font-size-md;
  }

  .preflight-summary p,
  .preflight-action-hint,
  .issue-copy p {
    margin: 4px 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-md;
    line-height: 1.5;
  }

  .preflight-issues {
    display: grid;
    gap: @spacing-sm;
  }

  .preflight-empty,
  .preflight-issue {
    min-height: 68px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    padding: @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-sm;
    background: #fff;
  }

  .preflight-empty {
    justify-content: flex-start;
    color: @success-color;
    font-weight: 700;
  }

  .preflight-issue.is-error {
    border-color: rgba(255, 77, 79, 0.22);
    background: rgba(255, 77, 79, 0.04);
  }

  .preflight-issue.is-warning {
    border-color: rgba(250, 173, 20, 0.28);
    background: rgba(250, 173, 20, 0.06);
  }

  .preflight-issue.is-info {
    border-color: rgba(24, 144, 255, 0.2);
    background: rgba(24, 144, 255, 0.05);
  }

  .issue-copy {
    min-width: 0;
  }

  .issue-node {
    display: block;
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: 700;
  }

  .issue-copy strong {
    color: @text-color-light-primary;
    font-size: @font-size-sm;
  }

  .preflight-actions {
    border-top: 1px solid @border-color-light;
    background: @bg-light-secondary;
  }

  @media (max-width: 960px) {
    .preflight-body {
      grid-template-columns: 1fr;
    }

    .preflight-header,
    .preflight-actions,
    .preflight-issue {
      align-items: flex-start;
      flex-direction: column;
    }
  }
</style>
