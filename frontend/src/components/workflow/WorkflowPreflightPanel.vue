<template>
  <section class="workflow-preflight-panel">
    <div class="preflight-hero">
      <div class="preflight-title-block">
        <span class="preflight-kicker">{{ t('workflow.preflight.title') }}</span>
        <h3>{{ preflight.primaryMessage }}</h3>
        <p>{{ summaryHint }}</p>
      </div>
      <a-button
        class="preflight-hero-action"
        type="primary"
        :disabled="!preflight.canRun"
        :loading="running"
        @click="$emit('run-ready-nodes')"
      >
        {{ t('workflow.preflight.runReadyNodes') }}
      </a-button>
    </div>

    <div class="preflight-metrics" aria-label="workflow preflight metrics">
      <div
        v-for="metric in preflightMetrics"
        :key="metric.id"
        class="preflight-metric"
        :class="`is-${metric.tone}`"
      >
        <strong>{{ metric.value }}</strong>
        <span>{{ metric.label }}</span>
      </div>
    </div>

    <div class="preflight-content">
      <section class="preflight-section preflight-guidance">
        <div class="preflight-section-header">
          <strong>{{ t('workflow.preflight.summaryTitle') }}</strong>
        </div>
        <p>{{ summaryHint }}</p>
      </section>

      <section class="preflight-section">
        <div class="preflight-section-header">
          <strong>{{ t('workflow.preflight.resourceTitle') }}</strong>
          <a-tag v-if="resourceSummaries.length" color="blue">
            {{ resourceSummaries.length }}
          </a-tag>
        </div>
        <div v-if="resourceSummaries.length" class="preflight-resource-list">
          <div
            v-for="resource in resourceSummaries"
            :key="resource.id"
            class="preflight-resource"
          >
            <div class="resource-copy">
              <span class="resource-node">{{ resource.nodeTitle }}</span>
              <strong>{{ resource.toolName }}</strong>
              <p>{{ resource.label }}</p>
            </div>
            <a-tag v-if="resource.executorType" color="blue">
              {{ resource.executorType }}
            </a-tag>
          </div>
        </div>
        <div v-else class="preflight-empty is-muted">
          {{ t('workflow.preflight.resourceEmpty') }}
        </div>
      </section>

      <section class="preflight-section">
        <div class="preflight-section-header">
          <strong>{{ t('workflow.preflight.issueTitle') }}</strong>
          <a-tag v-if="preflight.issues.length" color="orange">
            {{ preflight.issues.length }}
          </a-tag>
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
      </section>
    </div>

    <div class="preflight-footer">
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

  const resourceSummaries = computed(() => props.preflight.resourceSummaries)

  const preflightMetrics = computed(() => [
    {
      id: 'ready',
      value: props.preflight.runnableCount,
      label: t('workflow.preflight.metricReady'),
      tone: 'ready',
    },
    {
      id: 'blocked',
      value: props.preflight.blockedCount,
      label: t('workflow.preflight.metricBlocked'),
      tone: 'blocked',
    },
    {
      id: 'completed',
      value: props.preflight.completedCount,
      label: t('workflow.preflight.metricCompleted'),
      tone: 'completed',
    },
    {
      id: 'failed',
      value: props.preflight.failedCount,
      label: t('workflow.preflight.metricFailed'),
      tone: 'failed',
    },
  ])
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-preflight-panel {
    border: 1px solid @border-color-hover;
    border-radius: @border-radius-md;
    background: @bg-surface;
    box-shadow: @shadow-sm;
    overflow: hidden;
  }

  .preflight-hero {
    display: grid;
    gap: @spacing-md;
    padding: @spacing-md @spacing-lg;
    border-bottom: 1px solid @border-color-light;
    background: linear-gradient(135deg, @accent-color-light, transparent 72%);
  }

  .preflight-title-block {
    min-width: 0;
  }

  .preflight-kicker {
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: 800;
  }

  .preflight-title-block h3 {
    margin: 2px 0 0;
    color: @text-color-light-primary;
    font-size: @font-size-lg;
    font-weight: 800;
    line-height: @line-height-tight;
  }

  .preflight-title-block p {
    margin: @spacing-xs 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
  }

  .preflight-hero-action {
    width: 100%;
  }

  .preflight-metrics {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(76px, 1fr));
    gap: @spacing-sm;
    padding: @spacing-md @spacing-lg;
    border-bottom: 1px solid @border-color-light;
  }

  .preflight-metric {
    min-width: 0;
    display: grid;
    gap: 2px;
    padding: @spacing-sm;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-sm;
    background: @bg-elevated;
  }

  .preflight-metric strong {
    color: @text-color-light-primary;
    font-size: @font-size-xl;
    font-weight: 800;
    line-height: @line-height-tight;
  }

  .preflight-metric span {
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: 700;
  }

  .preflight-metric.is-ready strong {
    color: @success-color;
  }

  .preflight-metric.is-blocked strong {
    color: @warning-color;
  }

  .preflight-metric.is-completed strong {
    color: @accent-color;
  }

  .preflight-metric.is-failed strong {
    color: @error-color;
  }

  .preflight-content {
    display: grid;
    gap: @spacing-md;
    padding: @spacing-md @spacing-lg;
  }

  .preflight-section {
    border: 1px solid @border-color-light;
    border-radius: @border-radius-sm;
    background: @bg-elevated;
    overflow: hidden;
  }

  .preflight-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-sm;
    min-height: 40px;
    padding: @spacing-sm @spacing-md;
    border-bottom: 1px solid @border-color-light;
    background: @bg-hover;
  }

  .preflight-section-header strong {
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    font-weight: 800;
  }

  .preflight-guidance p {
    margin: 0;
    padding: @spacing-md;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
  }

  .preflight-resource-list,
  .preflight-issues {
    display: grid;
  }

  .preflight-resource {
    min-width: 0;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: @spacing-sm;
    padding: @spacing-md;
  }

  .preflight-resource + .preflight-resource,
  .preflight-issue + .preflight-issue {
    border-top: 1px solid @border-color-light;
  }

  .resource-copy {
    min-width: 0;
  }

  .resource-node {
    display: block;
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: 700;
  }

  .resource-copy strong,
  .issue-copy strong {
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    font-weight: 800;
  }

  .preflight-action-hint,
  .resource-copy p,
  .issue-copy p {
    margin: 4px 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
  }

  .preflight-empty,
  .preflight-issue {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    padding: @spacing-md;
  }

  .preflight-empty {
    justify-content: flex-start;
    color: @success-color;
    font-weight: 700;
  }

  .preflight-empty.is-muted {
    color: @text-color-light-tertiary;
  }

  .preflight-issue.is-error {
    background: @error-color-light;
  }

  .preflight-issue.is-warning {
    background: @warning-color-light;
  }

  .preflight-issue.is-info {
    background: @accent-color-light;
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

  .preflight-footer {
    padding: 0 @spacing-lg @spacing-md;
  }

  .preflight-action-hint {
    display: block;
    padding: @spacing-sm @spacing-md;
    border-top: 1px solid @border-color-light;
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
  }

  @media (max-width: 960px) {
    .preflight-resource,
    .preflight-issue {
      align-items: flex-start;
      flex-direction: column;
    }
  }
</style>
