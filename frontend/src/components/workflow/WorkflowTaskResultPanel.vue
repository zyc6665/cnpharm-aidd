<template>
  <section class="workflow-result-panel">
    <div class="workflow-result-panel__header">
      <div>
        <span class="workflow-result-panel__kicker">{{ t('tasks.result') }}</span>
        <h3 class="workflow-result-panel__title">{{ currentTask?.name || t('workflow.results.title') }}</h3>
        <p class="workflow-result-panel__desc">{{ panelDescription }}</p>
      </div>
      <a-button v-if="currentTask?.id" size="small" @click="openTaskDetail">
        {{ t('workflow.currentTool.viewTask') }}
      </a-button>
    </div>

    <a-spin :spinning="loading">
      <a-empty
        v-if="!currentTask"
        :description="t('workflow.results.empty')"
      />

      <template v-else>
        <div class="workflow-result-status" :class="`is-${taskStatus}`">
          <div class="workflow-result-status__main">
            <a-tag :color="statusColor">{{ statusText }}</a-tag>
            <strong class="workflow-result-status__name">{{ currentTask.name || t('workflow.results.latestTask') }}</strong>
            <span class="workflow-result-status__id">#{{ currentTask.id.slice(0, 8) }}</span>
          </div>
          <span v-if="currentTask.created_at" class="workflow-result-status__time">
            {{ formatTime(currentTask.created_at) }}
          </span>
        </div>

        <div v-if="isRunning" class="workflow-result-block">
          <div class="workflow-result-progress">
            <div class="workflow-result-progress__header">
              <span>{{ t('tasks.progress') }}</span>
              <strong>{{ currentTask.progress }}%</strong>
            </div>
            <a-progress :percent="currentTask.progress" status="active" />
            <p v-if="currentTask.started_at" class="workflow-result-progress__hint">
              {{ t('tasks.runningTime') }}: {{ formatDuration(currentTask.started_at) }}
            </p>
          </div>
          <TaskLogPreview :logs="logs" :max-items="4" :empty-description="t('workflow.results.runningHint')" />
        </div>

        <div v-else-if="isSuccess" class="workflow-result-block">
          <ResultVisualizationPanel v-if="currentTask.output_files?.length" :task="currentTask" />
          <TaskOutputSummary :task="currentTask" />
          <TaskLogPreview :logs="logs" :max-items="4" />
        </div>

        <div v-else-if="isFailure" class="workflow-result-block">
          <a-alert
            type="error"
            show-icon
            :message="currentTask.error_message || t('workflow.results.failureHint')"
          />
          <TaskLogPreview :logs="logs" :max-items="6" />
        </div>

        <div v-else class="workflow-result-block">
          <a-alert
            type="info"
            show-icon
            :message="t('workflow.results.pendingHint')"
          />
          <TaskLogPreview :logs="logs" :max-items="4" :empty-description="t('workflow.results.emptyHint')" />
        </div>
      </template>
    </a-spin>
  </section>
</template>

<script setup lang="ts">
  import { computed, onBeforeUnmount, ref, watch } from 'vue'
  import { useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { getTaskDetail, getTaskLogs, isTaskTerminalStatus } from '@/api/tasks'
  import ResultVisualizationPanel from '@/components/tasks/ResultVisualizationPanel.vue'
  import TaskLogPreview from '@/components/tasks/TaskLogPreview.vue'
  import TaskOutputSummary from '@/components/tasks/TaskOutputSummary.vue'
  import type { Task, TaskLog, TaskStatus } from '@/types/models'
  import type { WorkflowTaskRef } from '@/workflow/artifact-types'
  import { normalizeTaskSummary } from '@/utils/task-normalization'
  import {
    extractTaskLogs,
    formatTaskDetailTime,
    formatTaskRunningDuration,
    getTaskStatusColor,
    getTaskStatusTextKey,
    normalizeTaskStatus
  } from '@/domain/tasks'

  const props = defineProps<{
    taskId?: string | null
    taskSummary?: WorkflowTaskRef | null
  }>()

  const { t } = useI18n()
  const router = useRouter()

  const loading = ref(false)
  const logs = ref<TaskLog[]>([])
  const taskDetail = ref<Task | null>(null)
  let pollTimer: number | null = null

  const summaryTask = computed<Task | null>(() => {
    if (!props.taskSummary || props.taskSummary.id !== props.taskId) {
      return null
    }

    return normalizeTaskSummary(props.taskSummary as Task)
  })

  const currentTask = computed<Task | null>(() => {
    if (!taskDetail.value) {
      return summaryTask.value
    }

    if (!summaryTask.value || summaryTask.value.id !== taskDetail.value.id) {
      return taskDetail.value
    }

    return {
      ...taskDetail.value,
      name: summaryTask.value.name || taskDetail.value.name,
      status: summaryTask.value.status || taskDetail.value.status,
      progress: typeof summaryTask.value.progress === 'number' ? summaryTask.value.progress : taskDetail.value.progress,
      progress_message: summaryTask.value.progress_message || taskDetail.value.progress_message,
      error_message: summaryTask.value.error_message || taskDetail.value.error_message,
      tool_name: taskDetail.value.tool_name || summaryTask.value.tool_name,
      tool_slug: taskDetail.value.tool_slug || summaryTask.value.tool_slug,
      tool: taskDetail.value.tool || summaryTask.value.tool,
      output_data: taskDetail.value.output_data ?? summaryTask.value.output_data,
      output_files: taskDetail.value.output_files ?? summaryTask.value.output_files
    }
  })

  const taskStatus = computed<TaskStatus>(() => normalizeTaskStatus(currentTask.value?.status))
  const isRunning = computed(() => ['pending', 'running'].includes(taskStatus.value))
  const isSuccess = computed(() => taskStatus.value === 'success')
  const isFailure = computed(() => ['failure', 'canceled'].includes(taskStatus.value))

  const statusColor = computed(() => {
    return getTaskStatusColor(taskStatus.value)
  })

  const statusText = computed(() => t(getTaskStatusTextKey(taskStatus.value)))

  const panelDescription = computed(() => {
    if (!currentTask.value) {
      return t('workflow.results.emptyHint')
    }

    if (isRunning.value) {
      return t('workflow.results.runningHint')
    }

    if (isSuccess.value) {
      return t('workflow.results.successHint')
    }

    if (isFailure.value) {
      return t('workflow.results.failureHint')
    }

    return t('workflow.results.pendingHint')
  })

  function formatTime(time: string) {
    return formatTaskDetailTime(time)
  }

  function formatDuration(startTime: string) {
    return formatTaskRunningDuration(startTime)
  }

  async function fetchTaskResultDetail(taskId: string) {
    loading.value = true
    try {
      const response = await getTaskDetail(taskId)
      taskDetail.value = normalizeTaskSummary(response.data)
    } finally {
      loading.value = false
    }
  }

  async function fetchLogs(taskId: string) {
    const response = await getTaskLogs(taskId)
    logs.value = extractTaskLogs(response.data)
  }

  function stopPolling() {
    if (pollTimer !== null) {
      window.clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  function startPolling(taskId: string) {
    stopPolling()

    const poll = async () => {
      await Promise.allSettled([
        fetchTaskResultDetail(taskId),
        fetchLogs(taskId)
      ])

      if (!currentTask.value || isTaskTerminalStatus(taskStatus.value)) {
        stopPolling()
        return
      }

      pollTimer = window.setTimeout(poll, 5000)
    }

    pollTimer = window.setTimeout(poll, 5000)
  }

  function openTaskDetail() {
    if (!currentTask.value?.id) {
      return
    }

    router.push(`/tasks/${currentTask.value.id}`)
  }

  watch(
    () => props.taskId,
    async (taskId) => {
      stopPolling()
      taskDetail.value = summaryTask.value
      logs.value = []

      if (!taskId) {
        return
      }

      await Promise.allSettled([
        fetchTaskResultDetail(taskId),
        fetchLogs(taskId)
      ])

      if (currentTask.value && isRunning.value) {
        startPolling(taskId)
      }
    },
    { immediate: true }
  )

  watch(
    () => taskStatus.value,
    (status, previousStatus) => {
      if (!props.taskId) {
        return
      }

      if (['pending', 'running'].includes(status)) {
        startPolling(props.taskId)
        return
      }

      stopPolling()

      if (!isTaskTerminalStatus(previousStatus) && isTaskTerminalStatus(status)) {
        void Promise.allSettled([
          fetchTaskResultDetail(props.taskId),
          fetchLogs(props.taskId)
        ])
      }
    }
  )

  onBeforeUnmount(() => {
    stopPolling()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-result-panel {
    display: flex;
    flex-direction: column;
    gap: @spacing-md;
    padding: @spacing-lg;
    border: 1px solid @border-color;
    border-radius: @border-radius-lg;
    background: @bg-elevated;
    box-shadow: 0 16px 30px rgb(15 23 42 / 4%);
  }

  .workflow-result-panel__header {
    display: flex;
    justify-content: space-between;
    gap: @spacing-md;
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .workflow-result-panel__kicker {
    display: inline-block;
    margin-bottom: @spacing-xs;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .workflow-result-panel__title {
    margin: 0;
    font-size: @font-size-lg;
    font-weight: @font-weight-semibold;
    color: @text-color-light-primary;
  }

  .workflow-result-panel__desc {
    margin: @spacing-xs 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
  }

  .workflow-result-status {
    display: flex;
    justify-content: space-between;
    gap: @spacing-md;
    align-items: flex-start;
    flex-wrap: wrap;
    padding: @spacing-md;
    border-radius: @border-radius-md;
    background: @bg-hover;
    border: 1px solid @border-color;

    &.is-success {
      border-color: rgba(34, 197, 94, 0.25);
      background: rgba(34, 197, 94, 0.12);
    }

    &.is-failure,
    &.is-canceled {
      border-color: rgba(239, 68, 68, 0.25);
      background: rgba(239, 68, 68, 0.12);
    }

    &.is-running,
    &.is-pending {
      border-color: rgba(59, 130, 246, 0.25);
      background: rgba(59, 130, 246, 0.12);
    }
  }

  .workflow-result-status__main {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    flex-wrap: wrap;
  }

  .workflow-result-status__name {
    color: @text-color-light-primary;
    font-size: @font-size-md;
  }

  .workflow-result-status__id,
  .workflow-result-status__time {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    white-space: nowrap;
  }

  .workflow-result-block {
    display: flex;
    flex-direction: column;
    gap: @spacing-md;
  }

  .workflow-result-progress {
    padding: @spacing-md;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    background: @bg-elevated;
  }

  .workflow-result-progress__header {
    display: flex;
    justify-content: space-between;
    gap: @spacing-sm;
    align-items: center;
    margin-bottom: @spacing-sm;
    color: @text-color-light-primary;
  }

  .workflow-result-progress__hint {
    margin: @spacing-sm 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }
</style>
