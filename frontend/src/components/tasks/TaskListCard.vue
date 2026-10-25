<template>
  <div
    class="task-card"
    :class="{ 'is-running': taskStatus === 'running' }"
    role="button"
    tabindex="0"
    :aria-label="`${taskTitle} ${statusText}`"
    @click="emit('open', task.id)"
    @keydown.enter="emit('open', task.id)"
    @keydown.space.prevent="emit('open', task.id)"
  >
    <div class="task-main">
      <div class="task-info">
        <div class="task-header">
          <div class="tool-icon">
            <span v-if="task.tool?.icon">{{ task.tool.icon }}</span>
            <ToolOutlined v-else />
          </div>
          <div class="task-meta">
            <h3 class="task-title">{{ taskTitle }}</h3>
            <span class="task-id">
              <template v-if="task.name && task.tool?.name">
                {{ task.tool.name }} ·
              </template>
              ID: {{ task.id.slice(0, 8) }}...
            </span>
          </div>
        </div>
        <div class="task-details">
          <div class="detail-item">
            <CalendarOutlined />
            {{ formatTime(task.created_at) }}
          </div>
          <div v-if="task.started_at" class="detail-item">
            <PlayCircleOutlined />
            {{ formatTime(task.started_at) }}
          </div>
          <div v-if="task.completed_at" class="detail-item">
            <CheckCircleOutlined />
            {{ formatTime(task.completed_at) }}
          </div>
          <div v-if="task.project_id" class="detail-item project-detail">
            <ProjectOutlined />
            <span>{{ projectContextLabel }}</span>
            <router-link
              :to="artifactLineagePath"
              class="lineage-link"
              @click.stop
            >
              Artifact 谱系
            </router-link>
          </div>
          <div v-if="task.progress_message" class="detail-item progress-detail">
            <SyncOutlined />
            {{ task.progress_message }}
          </div>
          <div v-if="resourceWait" class="detail-item resource-wait-detail">
            <ClockCircleOutlined />
            {{ resourceWaitText }}
            <span v-if="resourceWait.scope && resourceWait.dimension">
              · {{ resourceWaitScopeText }} / {{ resourceWaitDimensionText }}
            </span>
            <span v-if="resourceWait.next_attempt_at">
              · {{ t('tasks.resourceWait.nextAttempt', { time: formatTime(resourceWait.next_attempt_at) }) }}
            </span>
          </div>
        </div>
      </div>

      <div class="task-status-section">
        <a-tag :color="getTaskStatusColor(taskStatus)" class="status-tag">
          <template #icon>
            <LoadingOutlined v-if="taskStatus === 'running'" spin />
            <ClockCircleOutlined v-else-if="taskStatus === 'pending'" />
            <CheckCircleOutlined v-else-if="taskStatus === 'success'" />
            <CloseCircleOutlined v-else-if="taskStatus === 'failure'" />
            <StopOutlined v-else-if="taskStatus === 'canceled'" />
          </template>
          {{ statusText }}
        </a-tag>

        <div v-if="taskStatus === 'running'" class="progress-section">
          <a-progress
            type="circle"
            :percent="task.progress"
            :width="60"
            :stroke-color="getTaskProgressColor(taskStatus)"
          />
        </div>
      </div>
    </div>

    <div class="task-actions" @click.stop>
      <a-space class="task-action-space" wrap>
        <a-tooltip :title="t('tasks.viewDetail')">
          <a-button data-testid="task-list-open" type="link" @click="emit('open', task.id)">
            <EyeOutlined />
          </a-button>
        </a-tooltip>
        <a-tooltip v-if="canCancel" :title="t('tasks.cancel')">
          <a-popconfirm :title="t('tasks.cancelConfirm')" @confirm="emit('cancel', task.id)">
            <a-button data-testid="task-list-cancel" type="link" danger>
              <StopOutlined />
            </a-button>
          </a-popconfirm>
        </a-tooltip>
        <a-tooltip v-if="canRetry" :title="t('tasks.retry')">
          <a-button data-testid="task-list-retry" type="link" @click="emit('retry', task.id)">
            <RedoOutlined />
          </a-button>
        </a-tooltip>
        <a-tooltip v-if="canDelete" :title="t('tasks.delete')">
          <a-popconfirm :title="t('tasks.deleteConfirm')" @confirm="emit('delete', task.id)">
            <a-button data-testid="task-list-delete" type="link" danger>
              <DeleteOutlined />
            </a-button>
          </a-popconfirm>
        </a-tooltip>
      </a-space>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import {
    CalendarOutlined,
    CheckCircleOutlined,
    ClockCircleOutlined,
    CloseCircleOutlined,
    DeleteOutlined,
    EyeOutlined,
    LoadingOutlined,
    PlayCircleOutlined,
    ProjectOutlined,
    RedoOutlined,
    StopOutlined,
    SyncOutlined,
    ToolOutlined,
  } from '@ant-design/icons-vue'
  import type { Task, TaskStatus } from '@/types/models'
  import {
    canCancelTask,
    canDeleteTask,
    canRetryTask,
    formatTaskDetailTime,
    getTaskArtifactLineagePath,
    getTaskProgressColor,
    getTaskProjectContextLabel,
    getTaskStatusColor,
    getTaskStatusTextKey,
    normalizeTaskStatus,
    type TaskActor,
  } from '@/domain/tasks'

  const props = defineProps<{
    task: Task
    actor: TaskActor
    currentProjectId?: string
    currentProjectName?: string
  }>()

  const emit = defineEmits<{
    open: [id: string]
    cancel: [id: string]
    retry: [id: string]
    delete: [id: string]
  }>()

  const { t } = useI18n()

  const taskStatus = computed<TaskStatus>(() => normalizeTaskStatus(props.task.status))
  const taskTitle = computed(() => props.task.name || props.task.tool?.name || t('tasks.unknownTool'))
  const statusText = computed(() => t(getTaskStatusTextKey(taskStatus.value)))
  const canCancel = computed(() => canCancelTask({ ...props.task, status: taskStatus.value }, props.actor))
  const canRetry = computed(() => canRetryTask({ ...props.task, status: taskStatus.value }, props.actor))
  const canDelete = computed(() => canDeleteTask({ ...props.task, status: taskStatus.value }, props.actor))
  const projectContextLabel = computed(() => getTaskProjectContextLabel(props.task, {
    currentProjectId: props.currentProjectId,
    currentProjectName: props.currentProjectName,
  }))
  const artifactLineagePath = computed(() => getTaskArtifactLineagePath(props.task))
  const resourceWait = computed(() => {
    const wait = props.task.resource_wait
    return taskStatus.value === 'pending' && wait ? wait : null
  })
  const resourceWaitText = computed(() => {
    if (!resourceWait.value) return ''
    if (resourceWait.value.category === 'quota') {
      return t('tasks.resourceWait.quotaExceeded')
    }
    if (resourceWait.value.category === 'worker_capacity') {
      return t('tasks.resourceWait.workerCapacity')
    }
    if (resourceWait.value.reason === 'gpu_unavailable') {
      return t('tasks.resourceWait.gpuUnavailable')
    }
    if (resourceWait.value.category === 'scheduler') {
      return t('tasks.resourceWait.schedulerBusy')
    }
    return t('tasks.resourceWait.title')
  })
  const resourceWaitScopeText = computed(() => {
    if (resourceWait.value?.scope === 'user') return t('tasks.resourceWait.userScope')
    if (resourceWait.value?.scope === 'project') return t('tasks.resourceWait.projectScope')
    return resourceWait.value?.scope || ''
  })
  const resourceWaitDimensionText = computed(() => {
    const dimension = resourceWait.value?.dimension
    if (!dimension) return ''
    return t('tasks.resourceWait.dimensions.' + dimension)
  })

  const formatTime = formatTaskDetailTime
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .task-card {
    .card();
    display: flex;
    justify-content: space-between;
    align-items: center;
    cursor: pointer;

    &:hover,
    &:focus-visible {
      transform: translateX(4px);
    }

    &:focus-visible {
      outline: 3px solid @accent-color-border;
      outline-offset: 3px;
    }

    &.is-running {
      border-left: 3px solid @accent-color;
      background: linear-gradient(90deg, @accent-color-light 0%, @bg-elevated 10%);
    }
  }

  .task-main {
    display: flex;
    align-items: center;
    gap: @spacing-xl;
    flex: 1;
  }

  .task-info {
    flex: 1;
  }

  .task-header {
    display: flex;
    align-items: center;
    gap: @spacing-md;
    margin-bottom: @spacing-sm;
  }

  .tool-icon {
    width: 40px;
    height: 40px;
    border-radius: @border-radius-md;
    background: @accent-color-light;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    color: @accent-color;
  }

  .task-meta {
    min-width: 0;
  }

  .task-title {
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
    margin: 0 0 @spacing-xs 0;
    word-break: break-word;
  }

  .task-id {
    color: @text-color-light-tertiary;
    font-size: @font-size-sm;
    font-family: monospace;
  }

  .task-details {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-lg;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .detail-item {
    display: flex;
    align-items: center;
    gap: @spacing-xs;
  }

  .recovery-detail {
    color: @warning-color;
    font-weight: @font-weight-medium;
  }

  .project-detail,
  .progress-detail {
    min-width: 0;
    flex-wrap: wrap;
  }

  .lineage-link {
    color: @accent-color;
    font-weight: @font-weight-medium;
  }

  .task-status-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: @spacing-sm;
    min-width: 120px;
  }

  .status-tag {
    font-size: @font-size-sm;
  }

  .task-actions {
    border-left: 1px solid @border-color-light;
    padding-left: @spacing-md;
    margin-left: @spacing-md;
  }

  .task-action-space {
    justify-content: flex-end;
  }

  @media (max-width: @breakpoint-md) {
    .task-card {
      flex-direction: column;
      align-items: flex-start;
      gap: @spacing-md;
    }

    .task-main {
      flex-direction: column;
      align-items: flex-start;
      width: 100%;
    }

    .task-status-section {
      flex-direction: row;
      width: 100%;
      justify-content: flex-start;
    }

    .task-actions {
      border-left: none;
      border-top: 1px solid @border-color-light;
      padding-left: 0;
      padding-top: @spacing-md;
      margin-left: 0;
      width: 100%;
    }

    .task-action-space {
      justify-content: flex-start;
    }
  }
</style>
