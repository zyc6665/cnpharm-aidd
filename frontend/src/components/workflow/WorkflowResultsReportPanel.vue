<template>
  <section class="workflow-results-report-panel">
    <div class="report-header">
      <div>
        <span class="report-kicker">{{ t('workflow.resultsReport.kicker') }}</span>
        <h3>{{ workflowName || t('workflow.resultsReport.workflowNameFallback') }}</h3>
        <p><strong>{{ t('workflow.resultsReport.decisionSummary') }}</strong>: {{ decisionSummary }}</p>
      </div>
      <a-button type="primary" ghost :disabled="rows.length === 0" @click="exportWorkflowReportMarkdown">
        {{ t('workflow.resultsReport.export') }}
      </a-button>
    </div>

    <div class="report-metrics">
      <div class="report-metric">
        <span>{{ t('workflow.resultsReport.nodeResults') }}</span>
        <strong>{{ rows.length }}</strong>
      </div>
      <div class="report-metric">
        <span>{{ t('workflow.resultsReport.successNodes') }}</span>
        <strong>{{ successCount }}</strong>
      </div>
      <div class="report-metric">
        <span>{{ t('workflow.resultsReport.failedNodes') }}</span>
        <strong>{{ failedCount }}</strong>
      </div>
      <div class="report-metric">
        <span>{{ t('workflow.resultsReport.artifactSummary') }}</span>
        <strong>{{ artifactCount }}</strong>
      </div>
    </div>

    <a-table
      size="small"
      :pagination="false"
      :data-source="rows"
      :columns="columns"
      row-key="nodeId"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'status'">
          <a-tag :color="statusColor(record.status)">{{ record.statusLabel || record.status }}</a-tag>
        </template>
        <template v-else-if="column.key === 'artifacts'">
          <span v-if="record.artifacts.length === 0" class="muted-text">{{ t('workflow.resultsReport.noArtifacts') }}</span>
          <a-space v-else size="small" wrap>
            <a v-for="artifact in record.artifacts.slice(0, 2)" :key="artifact.id" :href="artifact.url" target="_blank">
              {{ artifact.filename }}
            </a>
            <a-tag v-if="record.artifacts.length > 2">+{{ record.artifacts.length - 2 }}</a-tag>
          </a-space>
        </template>
      </template>
    </a-table>
  </section>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { buildWorkflowReportMarkdown, type WorkflowReportRow } from '@/workflow/report'

  const props = defineProps<{
    workflowName: string
    rows: WorkflowReportRow[]
  }>()

  const { t } = useI18n()

  const columns = computed(() => [
    { title: t('workflow.resultsReport.table.node'), dataIndex: 'nodeTitle', key: 'nodeTitle' },
    { title: t('workflow.resultsReport.table.status'), dataIndex: 'status', key: 'status' },
    { title: t('workflow.resultsReport.table.task'), dataIndex: 'taskId', key: 'taskId' },
    { title: t('workflow.resultsReport.table.artifacts'), dataIndex: 'artifacts', key: 'artifacts' }
  ])

  const rows = computed(() => props.rows)
  const successCount = computed(() => rows.value.filter(row => row.status === 'completed').length)
  const failedCount = computed(() => rows.value.filter(row => row.status === 'failed').length)
  const artifactCount = computed(() => rows.value.reduce((count, row) => count + row.artifacts.length, 0))

  const decisionSummary = computed(() => {
    if (failedCount.value > 0) {
      return t('workflow.resultsReport.summary.failed')
    }
    if (successCount.value > 0 && artifactCount.value > 0) {
      return t('workflow.resultsReport.summary.ready')
    }
    return t('workflow.resultsReport.summary.empty')
  })

  const reportLabels = computed(() => ({
    workflowNameFallback: t('workflow.resultsReport.workflowNameFallback'),
    reportTitleSuffix: t('workflow.resultsReport.reportTitleSuffix'),
    decisionSummaryTitle: t('workflow.resultsReport.decisionSummary'),
    nodeResultsTitle: t('workflow.resultsReport.nodeResults'),
    artifactSummaryTitle: t('workflow.resultsReport.artifactSummary'),
    tableNode: t('workflow.resultsReport.table.node'),
    tableStatus: t('workflow.resultsReport.table.status'),
    tableTask: t('workflow.resultsReport.table.task'),
    tableArtifacts: t('workflow.resultsReport.table.artifacts'),
    noArtifacts: t('workflow.resultsReport.noArtifacts'),
    artifactSummaryLine: (count: number) => t('workflow.resultsReport.artifactSummaryLine', { count })
  }))

  function statusColor(status: string): string {
    const colors: Record<string, string> = {
      ready: 'blue',
      running: 'processing',
      completed: 'green',
      failed: 'red',
      idle: 'default',
      needs_tool_selection: 'gold'
    }

    return colors[status] ?? 'default'
  }

  function exportWorkflowReportMarkdown() {
    const report = buildWorkflowReportMarkdown({
      workflowName: props.workflowName,
      rows: rows.value,
      decisionSummary: decisionSummary.value,
      labels: reportLabels.value
    })
    const blob = new Blob([report], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = t('workflow.resultsReport.downloadFilename')
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    URL.revokeObjectURL(url)
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-results-report-panel {
    margin-top: @spacing-md;
    padding: @spacing-lg;
    border: 1px solid @border-color-hover;
    border-radius: @border-radius-md;
    background: @bg-surface;
    box-shadow: @shadow-sm;
  }

  .report-header {
    display: flex;
    justify-content: space-between;
    gap: @spacing-md;
    align-items: flex-start;
    margin-bottom: @spacing-md;
  }

  .report-header h3 {
    margin: 2px 0 @spacing-xs;
    color: @text-color-light-primary;
    font-size: @font-size-lg;
    font-weight: 800;
  }

  .report-header p {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .report-kicker {
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: 800;
    letter-spacing: 0;
  }

  .report-metrics {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: @spacing-sm;
    margin-bottom: @spacing-md;
  }

  .report-metric {
    display: flex;
    justify-content: space-between;
    gap: @spacing-sm;
    padding: @spacing-sm;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-sm;
    background: @bg-light-secondary;
  }

  .report-metric span {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .report-metric strong {
    color: @text-color-light-primary;
  }

  .muted-text {
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
  }

  @media (max-width: @screen-md) {
    .report-header {
      flex-direction: column;
    }

    .report-metrics {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
