<template>
  <div class="task-result-detail" data-testid="generic-task-result">
    <AppPageHeader
      :title="t('tasks.resultPage.genericTitle')"
      :subtitle="t('tasks.resultPage.genericSubtitle')"
    />
    <TaskContextBar
      :task-id="taskId"
      :task="task"
      active="result"
      :fetch-task="false"
    />

    <ResultVisualizationPanel v-if="hasOutput" :task="task" />
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
  import ResultVisualizationPanel from '@/components/tasks/ResultVisualizationPanel.vue'
  import TaskContextBar from '@/components/tasks/TaskContextBar.vue'
  import TaskOutputSummary from '@/components/tasks/TaskOutputSummary.vue'
  import { getTaskResultArtifacts } from '@/domain/tasks/result'
  import type { Task } from '@/types/models'
  import ResultDisclaimer from '@/components/common/ResultDisclaimer.vue'

  const props = defineProps<{ task: Task; taskId: string }>()
  const { t } = useI18n()

  const hasOutput = computed(
    () =>
      Object.keys(getTaskResultArtifacts(props.task)).length > 0 ||
      (props.task.output_files?.length ?? 0) > 0 ||
      Boolean(props.task.output_data)
  )
</script>
