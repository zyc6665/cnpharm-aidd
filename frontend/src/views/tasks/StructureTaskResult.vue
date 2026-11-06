<template>
  <div class="task-result-detail" data-testid="structure-task-result">
    <AppPageHeader
      :title="t('tasks.resultPage.structureTitle')"
      :subtitle="t('tasks.resultPage.structureSubtitle')"
    />
    <TaskContextBar
      :task-id="taskId"
      :task="task"
      active="result"
      :fetch-task="false"
    />

    <a-row :gutter="16" class="task-result-detail__stats">
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :bordered="false">
          <a-statistic :title="t('tasks.resultPage.duration')" :value="duration" suffix="s" />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :bordered="false">
          <a-statistic :title="t('tasks.resultPage.fileCount')" :value="fileCount" />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :bordered="false">
          <a-statistic :title="t('tasks.resultPage.artifactCount')" :value="artifactCount" />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card :bordered="false">
          <a-statistic :title="t('tasks.resultPage.model')" :value="modelName" />
        </a-card>
      </a-col>
    </a-row>

    <ResultVisualizationPanel v-if="hasOutput" :task="task" />
    <TaskOutputSummary v-if="hasOutput" :task="task" />
    <AppEmptyState v-else :title="t('tasks.resultPage.noOutput')" />
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import AppEmptyState from '@/components/common/AppEmptyState.vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import ResultVisualizationPanel from '@/components/tasks/ResultVisualizationPanel.vue'
  import TaskContextBar from '@/components/tasks/TaskContextBar.vue'
  import TaskOutputSummary from '@/components/tasks/TaskOutputSummary.vue'
  import { getTaskResultArtifacts, getTaskResultMetrics } from '@/domain/tasks/result'
  import type { Task } from '@/types/models'

  const props = defineProps<{ task: Task; taskId: string }>()
  const { t } = useI18n()

  const metrics = computed(() => getTaskResultMetrics(props.task))
  const artifactCount = computed(() => Object.keys(getTaskResultArtifacts(props.task)).length)
  const fileCount = computed(() => props.task.output_files?.length ?? 0)
  const duration = computed(() => {
    const raw = props.task.execution_time_sec ?? metrics.value.duration_sec
    return typeof raw === 'number' ? Math.round(raw * 10) / 10 : 0
  })
  const modelName = computed(
    () => props.task.tool?.name || props.task.tool_name || String(metrics.value.selected_model ?? '-')
  )
  const hasOutput = computed(() => fileCount.value > 0 || artifactCount.value > 0)
</script>

<style scoped lang="less">
  .task-result-detail {
    &__stats {
      margin-bottom: @spacing-lg;
    }
  }
</style>
