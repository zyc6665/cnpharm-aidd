<template>
  <div class="task-result-detail" data-testid="pocket-task-result">
    <AppPageHeader
      :title="t('tasks.resultPage.pocketTitle')"
      :subtitle="t('tasks.resultPage.pocketSubtitle')"
    />
    <TaskContextBar
      :task-id="taskId"
      :task="task"
      active="result"
      :fetch-task="false"
    />

    <a-row :gutter="16" class="task-result-detail__stats">
      <a-col :xs="24" :sm="12" :lg="8">
        <a-card :bordered="false">
          <a-statistic :title="t('tasks.resultPage.pocketCount')" :value="pocketCount" />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="8">
        <a-card :bordered="false">
          <a-statistic :title="t('tasks.resultPage.duration')" :value="duration" suffix="s" />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="8">
        <a-card :bordered="false">
          <a-statistic :title="t('tasks.resultPage.selectedModel')" :value="selectedModel" />
        </a-card>
      </a-col>
    </a-row>

    <PocketComplexViewer :task="task" />

    <a-card
      v-if="pocketRows.length"
      :bordered="false"
      class="task-result-detail__pockets"
      :title="t('tasks.resultPage.pocketList')"
    >
      <a-table
        data-testid="pocket-result-table"
        :data-source="pocketRows"
        :columns="pocketColumns"
        :pagination="false"
        size="small"
        row-key="id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'id'">#{{ record.id }}</template>
          <template v-else-if="column.key === 'files'">
            <span>{{ [record.atomPdb, record.residuePdb].filter(Boolean).join(' · ') || '-' }}</span>
          </template>
        </template>
      </a-table>
    </a-card>

    <TaskOutputSummary v-if="hasOutput" :task="task" />
    <AppEmptyState v-else :title="t('tasks.resultPage.noOutput')" />
  </div>
  <ResultDisclaimer />
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import AppEmptyState from '@/components/common/AppEmptyState.vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import TaskContextBar from '@/components/tasks/TaskContextBar.vue'
  import TaskOutputSummary from '@/components/tasks/TaskOutputSummary.vue'
  import PocketComplexViewer from '@/views/tasks/PocketComplexViewer.vue'
  import {
    getPocketCount,
    getPocketResultRows,
    getTaskResultArtifacts,
    getTaskResultMetrics,
  } from '@/domain/tasks/result'
  import type { Task } from '@/types/models'
  import ResultDisclaimer from '@/components/common/ResultDisclaimer.vue'

  const props = defineProps<{ task: Task; taskId: string }>()
  const { t } = useI18n()

  const metrics = computed(() => getTaskResultMetrics(props.task))
  const pocketRows = computed(() => getPocketResultRows(props.task))
  const pocketCount = computed(() => getPocketCount(props.task))
  const artifactCount = computed(() => Object.keys(getTaskResultArtifacts(props.task)).length)
  const duration = computed(() => {
    const raw = props.task.execution_time_sec ?? metrics.value.duration_sec
    return typeof raw === 'number' ? Math.round(raw * 10) / 10 : 0
  })
  const selectedModel = computed(
    () =>
      props.task.tool?.name ||
      props.task.tool_name ||
      String(metrics.value.selected_model ?? '-')
  )
  const hasOutput = computed(
    () => pocketRows.value.length > 0 || artifactCount.value > 0 || (props.task.output_files?.length ?? 0) > 0
  )

  const pocketColumns = computed(() => [
    { title: t('tasks.resultPage.pocketId'), key: 'id', width: 140 },
    { title: t('tasks.resultPage.pocketFiles'), key: 'files' },
  ])
</script>

<style scoped lang="less">
  .task-result-detail {
    &__stats {
      margin-bottom: @spacing-lg;
    }

    &__pockets {
      margin-bottom: @spacing-lg;
    }
  }
</style>
