<template>
  <div class="task-detail-page">
    <div class="container">
      <!-- 面包屑导航 -->
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/">{{ t('common.home') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <router-link to="/tasks">{{ t('tasks.title') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>{{ task?.name || task?.tool?.name || t('tasks.taskDetail') }}</a-breadcrumb-item>
      </a-breadcrumb>

      <SkeletonDetail v-if="loading" />
          <div v-else-if="task" class="detail-content">
            <AppPageHeader :title="detailTitle" :subtitle="detailSubtitle">
              <template #actions>
                <a-space class="task-detail-actions" wrap>
                  <a-button
                    v-if="taskStatus === 'running' || taskStatus === 'pending'"
                    danger
                    @click="handleCancel"
                  >
                    <template #icon><StopOutlined /></template>
                    {{ t('tasks.cancel') }}
                  </a-button>
                  <a-button
                    v-if="taskStatus === 'failure'"
                    type="primary"
                    @click="handleRetry"
                  >
                    <template #icon><RedoOutlined /></template>
                    {{ t('tasks.retry') }}
                  </a-button>
                  <a-button
                    v-if="canDeleteTask"
                    danger
                    @click="handleDelete"
                  >
                    <template #icon><DeleteOutlined /></template>
                    {{ t('tasks.delete') }}
                  </a-button>
                  <a-button @click="goBack">
                    <template #icon><ArrowLeftOutlined /></template>
                    {{ t('common.back') }}
                  </a-button>
                </a-space>
              </template>
            </AppPageHeader>

            <!-- 任务状态卡片 -->
            <div class="status-card" :class="[`status-${taskStatus}`]">
              <div class="status-main">
                <div class="status-icon">
                  <LoadingOutlined v-if="taskStatus === 'running'" spin />
                  <ClockCircleOutlined v-else-if="taskStatus === 'pending'" />
                  <CheckCircleOutlined v-else-if="taskStatus === 'success'" />
                  <CloseCircleOutlined v-else-if="taskStatus === 'failure'" />
                  <StopOutlined v-else-if="taskStatus === 'canceled'" />
                </div>
              <div class="status-info">
                <span class="status-label">{{ t('common.status') }}</span>
                <div class="status-line">
                  <span class="task-id">
                    <CopyOutlined @click.stop="copyTaskId" />
                    ID: {{ task.id }}
                  </span>
                  <a-tag :color="getStatusColor(taskStatus)" size="large">
                    {{ getStatusText(taskStatus) }}
                  </a-tag>
                </div>
              </div>
            </div>
          </div>

          <!-- 进度条（运行中显示） -->
          <div v-if="taskStatus === 'running'" class="progress-section">
            <div class="progress-header">
              <span>{{ t('tasks.progress') }}</span>
              <span class="progress-percent">{{ task.progress }}%</span>
            </div>
            <a-progress
              :percent="task.progress"
              status="active"
              :stroke-color="{
                '0%': '#108ee9',
                '100%': '#87d068',
              }"
            />
            <div v-if="task.progress_message" class="progress-info">
              {{ task.progress_message }}
            </div>
          </div>

          <div v-if="resourceWait" class="resource-wait-notice">
            <a-alert type="info" show-icon>
              <template #message>{{ t('tasks.resourceWait.title') }}</template>
              <template #description>
                <div>{{ resourceWaitText }}</div>
                <div v-if="resourceWait.scope && resourceWait.dimension">
                  {{ t('tasks.resourceWait.scopeDimension', {
                    scope: resourceWaitScopeText,
                    dimension: resourceWaitDimensionText
                  }) }}
                </div>
                <div v-if="resourceWait.category === 'quota'" class="resource-wait-code">
                  <a-typography-text code>{{ resourceWait.reason }}</a-typography-text>
                </div>
                <div>{{ t('tasks.resourceWait.retryCount', { count: resourceWait.retry_count }) }}</div>
                <div v-if="resourceWait.next_attempt_at">
                  {{ t('tasks.resourceWait.nextAttempt', { time: formatTime(resourceWait.next_attempt_at) }) }}
                </div>
              </template>
            </a-alert>
          </div>

          <div v-if="resourceReservation" class="reservation-notice">
            <a-alert :type="resourceReservationAlertType" show-icon>
              <template #message>{{ t('tasks.resourceReservation.title') }}</template>
              <template #description>
                <div>{{ t('tasks.resourceReservation.status', { status: resourceReservationStatusText }) }}</div>
                <div v-if="resourceReservation.worker_id">
                  {{ t('tasks.resourceReservation.worker', { worker: resourceReservation.worker_id }) }}
                </div>
                <div v-if="task.dispatch?.queue">
                  {{ t('tasks.resourceReservation.queue', { queue: task.dispatch.queue }) }}
                </div>
                <div v-if="resourceReservation.release_reason">
                  {{ t('tasks.resourceReservation.releaseReason', { reason: resourceReservation.release_reason }) }}
                </div>
                <div v-if="resourceReservation.release_error">
                  {{ t('tasks.resourceReservation.releaseError', { error: resourceReservation.release_error }) }}
                </div>
              </template>
            </a-alert>
          </div>

          <!-- 主体内容 -->
          <a-row :gutter="24">
            <!-- 左侧：任务信息 -->
            <a-col :xs="24" :lg="16">
              <!-- 时间轴 -->
              <div class="info-card">
                <h3 class="card-title">
                  <FieldTimeOutlined />
                  {{ t('tasks.timeline') }}
                </h3>
                <a-timeline>
                  <a-timeline-item color="blue">
                    <p class="timeline-title">{{ t('tasks.created') }}</p>
                    <p class="timeline-time">{{ formatTime(task.created_at) }}</p>
                  </a-timeline-item>
                  <a-timeline-item v-if="task.started_at" color="blue">
                    <p class="timeline-title">{{ t('tasks.started') }}</p>
                    <p class="timeline-time">{{ formatTime(task.started_at) }}</p>
                  </a-timeline-item>
                  <a-timeline-item
                    v-if="task.completed_at"
                    :color="taskStatus === 'success' ? 'green' : taskStatus === 'failure' ? 'red' : 'gray'"
                  >
                    <p class="timeline-title">{{ getCompletedTitle(taskStatus) }}</p>
                    <p class="timeline-time">{{ formatTime(task.completed_at) }}</p>
                  </a-timeline-item>
                </a-timeline>
              </div>

              <!-- 输入参数 -->
              <div class="info-card">
                <h3 class="card-title">
                  <SettingOutlined />
                  {{ t('tasks.inputParams') }}
                </h3>
                <a-descriptions :column="1" bordered size="small">
                  <a-descriptions-item
                    v-for="(value, key) in task.inputs?.params"
                    :key="key"
                    :label="String(key)"
                  >
                    <template v-if="typeof value === 'object'">
                      <pre class="json-display">{{ JSON.stringify(value, null, 2) }}</pre>
                    </template>
                    <template v-else>
                      {{ value }}
                    </template>
                  </a-descriptions-item>
                </a-descriptions>

                <!-- 输入文件 -->
                <div v-if="task.input_files?.length" class="files-section">
                  <h4>{{ t('tasks.inputFiles') }}</h4>
                  <div class="file-list">
                    <div v-for="file in task.input_files" :key="file.id" class="file-item">
                      <FileOutlined />
                      <span class="file-name">{{ file.original_name }}</span>
                      <span class="file-size">{{ formatFileSize(file.size) }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 输出结果 -->
              <div v-if="taskStatus === 'success'" class="info-card">
                <h3 class="card-title">
                  <CheckCircleOutlined />
                  {{ t('tasks.outputResults') }}
                </h3>

                <ResultVisualizationPanel :task="task" />
                <TaskOutputSummary :task="task" />
              </div>

              <!-- 错误信息 -->
              <div v-if="taskStatus === 'failure' && failureDiagnostics.hasDetails" class="info-card error">
                <h3 class="card-title">
                  <CloseCircleOutlined />
                  {{ t('tasks.errorMessage') }}
                </h3>
                <a-alert
                  v-if="failureDiagnostics.errorMessage"
                  type="error"
                  show-icon
                  :message="failureDiagnostics.errorMessage"
                />

                <div
                  v-if="failureDiagnostics.standardArtifactMessage || failureDiagnostics.stderr || failureDiagnostics.stdout"
                  class="task-failure-diagnostics"
                  data-testid="task-failure-diagnostics"
                >
                  <a-alert
                    v-if="failureDiagnostics.standardArtifactMessage"
                    type="warning"
                    show-icon
                    :message="t('tasks.standardArtifactsMissing')"
                    :description="failureDiagnostics.standardArtifactMessage"
                  />

                  <div v-if="failureDiagnostics.stderr" class="failure-stream">
                    <h4>{{ t('tasks.failureStderr') }}</h4>
                    <pre data-testid="task-stderr">{{ failureDiagnostics.stderr }}</pre>
                  </div>

                  <div v-if="failureDiagnostics.stdout" class="failure-stream">
                    <h4>{{ t('tasks.failureStdout') }}</h4>
                    <pre data-testid="task-stdout">{{ failureDiagnostics.stdout }}</pre>
                  </div>
                </div>
              </div>

              <!-- 运行日志 -->
              <div class="info-card">
                <h3 class="card-title">
                  <FileTextOutlined />
                  {{ t('tasks.logs') }}
                  <a-button
                    type="link"
                    size="small"
                    :loading="logsLoading"
                    @click="fetchLogs"
                  >
                    <ReloadOutlined />
                  </a-button>
                </h3>
                <TaskLogPreview :logs="logs" :max-items="0" />
              </div>
            </a-col>

            <!-- 右侧：工具信息 -->
            <a-col :xs="24" :lg="8">
              <div class="info-card tool-card">
                <h3 class="card-title">
                  <ToolOutlined />
                  {{ t('tasks.toolInfo') }}
                </h3>
                <div v-if="task.tool" class="tool-info">
                  <div class="tool-header">
                    <div class="tool-icon">
                      <span v-if="task.tool.icon">{{ task.tool.icon }}</span>
                      <ToolOutlined v-else />
                    </div>
                    <div class="tool-meta">
                      <h4 class="tool-name">{{ task.tool.name }}</h4>
                      <span class="tool-version">v{{ task.tool.version }}</span>
                    </div>
                  </div>
                  <p class="tool-desc">{{ task.tool.description }}</p>
                  <div class="tool-stats">
                    <div class="stat-item">
                      <PlayCircleOutlined />
                      <span>{{ task.tool.run_count }} {{ t('tools.runs') }}</span>
                    </div>
                  </div>
                  <a-button type="primary" block @click="goToTool">
                    {{ t('tasks.viewTool') }}
                  </a-button>
                </div>
                <AppEmptyState
                  v-else
                  size="compact"
                  :title="t('tasks.toolNotFound')"
                  :description="t('tasks.toolNotFoundHint')"
                />
              </div>

            </a-col>
          </a-row>
        </div>

        <a-result
          v-else-if="!loading"
          status="404"
          :title="t('tasks.notFound')"
          :sub-title="t('tasks.notFoundDesc')"
        >
          <template #extra>
            <a-button type="primary" @click="goBack">
              {{ t('common.back') }}
            </a-button>
          </template>
        </a-result>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  LoadingOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  StopOutlined,
  CopyOutlined,
  RedoOutlined,
  DeleteOutlined,
  ArrowLeftOutlined,
  FieldTimeOutlined,
  SettingOutlined,
  FileOutlined,
  FileTextOutlined,
  ReloadOutlined,
  ToolOutlined,
  PlayCircleOutlined
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { useTasksStore, useUserStore } from '@/stores'
import { useTaskDetailLiveUpdates } from '@/composables/useTaskDetailLiveUpdates'
import type { TaskStatus } from '@/types/models'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppEmptyState from '@/components/common/AppEmptyState.vue'
import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
import ResultVisualizationPanel from '@/components/tasks/ResultVisualizationPanel.vue'
import TaskLogPreview from '@/components/tasks/TaskLogPreview.vue'
import TaskOutputSummary from '@/components/tasks/TaskOutputSummary.vue'
import {
  canDeleteTask as canDeleteTaskForActor,
  formatTaskDetailTime,
  formatTaskFileSize,
  buildTaskFailureDiagnostics,
  getTaskCompletedTitleKey,
  getTaskStatusColor,
  getTaskStatusTextKey,
  normalizeTaskStatus,
} from '@/domain/tasks'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const tasksStore = useTasksStore()
const userStore = useUserStore()

const taskId = computed(() => route.params.id as string)

// 计算属性
const loading = computed(() => tasksStore.loading)
const task = computed(() => tasksStore.currentTask)
const taskStatus = computed<TaskStatus>(() => normalizeTaskStatus(task.value?.status))
const detailTitle = computed(() =>
  task.value?.name || task.value?.tool?.name || t('tasks.taskDetail')
)
const canDeleteTask = computed(() =>
  task.value
    ? canDeleteTaskForActor(
        { ...task.value, status: taskStatus.value },
        { isAdmin: userStore.isAdmin }
      )
    : false
)
const detailSubtitle = computed(() => {
  if (!task.value) {
    return t('tasks.detail')
  }

  return `${getStatusText(taskStatus.value)} · ${formatTime(task.value.created_at)}`
})
const failureDiagnostics = computed(() => buildTaskFailureDiagnostics(task.value))
const resourceWait = computed(() => {
  const wait = task.value?.resource_wait
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
const resourceReservation = computed(() => task.value?.dispatch?.resource_reservation ?? null)
const resourceReservationStatus = computed(() => resourceReservation.value?.status || 'reserved')
const resourceReservationStatusText = computed(() => {
  const status = resourceReservationStatus.value
  const statusKeys: Record<string, string> = {
    reserved: 'reserved',
    claimed: 'claimed',
    released: 'released',
    release_failed: 'releaseFailed',
    not_found: 'notFound'
  }
  return t(`tasks.resourceReservation.statuses.${statusKeys[status] || 'reserved'}`)
})
const resourceReservationAlertType = computed(() => {
  if (resourceReservationStatus.value === 'release_failed') return 'warning'
  if (['claimed', 'released'].includes(resourceReservationStatus.value)) return 'success'
  return 'info'
})

// 方法
const getStatusColor = getTaskStatusColor

const getStatusText = (status: TaskStatus) => t(getTaskStatusTextKey(status))

const getCompletedTitle = (status: TaskStatus) => {
  return t(getTaskCompletedTitleKey(status))
}

const formatTime = formatTaskDetailTime
const formatFileSize = formatTaskFileSize

const copyTaskId = async () => {
  if (task.value) {
    await navigator.clipboard.writeText(task.value.id)
    message.success(t('common.copySuccess'))
  }
}

const fetchTaskDetail = async () => {
  await tasksStore.fetchTaskDetail(taskId.value)
}

const {
  logs,
  logsLoading,
  fetchLogs,
  start: startLiveUpdates,
  stop: stopLiveUpdates
} = useTaskDetailLiveUpdates({
  taskId,
  task,
  fetchTaskDetail,
  updateTaskProgress: tasksStore.updateTaskProgress
})

const handleCancel = () => {
  Modal.confirm({
    title: t('tasks.cancelConfirm'),
    content: t('tasks.cancelConfirmContent'),
    okText: t('common.confirm'),
    cancelText: t('common.cancel'),
    onOk: async () => {
      try {
        await tasksStore.cancelTask(taskId.value)
        message.success(t('tasks.cancelSuccess'))
      } catch {
        // 请求层已经展示具体错误，避免失败时误报成功。
      }
    }
  })
}

const handleRetry = async () => {
  try {
    await tasksStore.retryTask(taskId.value)
    message.success(t('tasks.retrySuccess'))
  } catch {
    // 请求层已经展示具体错误，避免失败时误报成功。
  }
}

const handleDelete = () => {
  Modal.confirm({
    title: t('tasks.deleteConfirm'),
    content: t('tasks.deleteConfirmContent'),
    okText: t('common.confirm'),
    okType: 'danger',
    cancelText: t('common.cancel'),
    onOk: async () => {
      try {
        await tasksStore.deleteTask(taskId.value)
        message.success(t('tasks.deleteSuccess'))
        router.push('/tasks')
      } catch {
        // 请求层已经展示具体错误，删除失败时保留当前任务详情。
      }
    }
  })
}

const goToTool = () => {
  if (task.value?.tool_id) {
    router.push(`/tools/${task.value.tool_id}`)
  }
}

const goBack = () => {
  router.push('/tasks')
}

// 生命周期
onMounted(async () => {
  await startLiveUpdates()
})

onUnmounted(() => {
  stopLiveUpdates()
  tasksStore.clearCurrentTask()
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.task-detail-page {
  padding: @spacing-xl 0;
  min-height: calc(100vh - @header-height - @footer-height);
}

.breadcrumb {
  margin-bottom: @spacing-lg;
}

.task-detail-actions {
  justify-content: flex-end;
}

// 状态卡片
.status-card {
  .card();
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: @spacing-lg;
  margin-bottom: @spacing-xl;

  &.status-running {
    border-left: 4px solid @primary-color;
    background: linear-gradient(90deg, @primary-color-light 0%, @bg-elevated 20%);
  }

  &.status-success {
    border-left: 4px solid @success-color;
  }

  &.status-failure {
    border-left: 4px solid @error-color;
  }

  &.status-pending {
    border-left: 4px solid @warning-color;
  }

  &.status-canceled {
    border-left: 4px solid @text-color-light-tertiary;
  }

  .status-main {
    display: flex;
    align-items: center;
    gap: @spacing-lg;
  }

  .status-icon {
    font-size: 48px;

    .anticon-loading { color: @primary-color; }
    .anticon-clock-circle { color: @warning-color; }
    .anticon-check-circle { color: @success-color; }
    .anticon-close-circle { color: @error-color; }
    .anticon-stop { color: @text-color-light-tertiary; }
  }

  .status-info {
    min-width: 0;

    .status-label {
      display: block;
      margin-bottom: @spacing-xs;
      color: @text-color-light-secondary;
      font-size: @font-size-sm;
      font-weight: @font-weight-medium;
    }

    .status-line {
      display: flex;
      align-items: center;
      gap: @spacing-md;
      flex-wrap: wrap;

      .task-id {
        display: flex;
        align-items: center;
        gap: @spacing-xs;
        color: @text-color-light-tertiary;
        font-family: monospace;
        font-size: @font-size-sm;
        word-break: break-all;
        cursor: pointer;

        &:hover {
          color: @primary-color;
        }
      }
    }
  }
}

// 进度条
.progress-section {
  .card();
  margin-bottom: @spacing-xl;

  .progress-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: @spacing-sm;
    font-weight: @font-weight-medium;

    .progress-percent {
      color: @primary-color;
      font-size: @font-size-lg;
    }
  }

  .progress-info {
    margin-top: @spacing-sm;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;

    .anticon {
      margin-right: @spacing-xs;
    }
  }
}

.recovery-notice {
  margin-bottom: @spacing-xl;
}

.reservation-notice {
  margin-bottom: @spacing-xl;
}

// 信息卡片
.info-card {
  .card();
  margin-bottom: @spacing-lg;

  &.error {
    border-left: 4px solid @error-color;
  }

  .card-title {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    font-size: @font-size-lg;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-lg;
    padding-bottom: @spacing-sm;
    border-bottom: 1px solid @border-color-light;

    .anticon {
      color: @primary-color;
    }
  }
}

.task-failure-diagnostics {
  display: flex;
  flex-direction: column;
  gap: @spacing-md;
  margin-top: @spacing-md;
}

.failure-stream {
  display: flex;
  flex-direction: column;
  gap: @spacing-xs;

  h4 {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    font-weight: @font-weight-semibold;
  }

  pre {
    margin: 0;
    padding: @spacing-sm;
    overflow-x: auto;
    border-radius: @border-radius-sm;
    // 日志块刻意保留深底而不是 @bg-body：正文区在浅色主题下是白的，
    // 白底等宽日志读起来像代码嵌入了一篇文章。这里固定成终端观感，
    // 与 JsonResultRenderer 的代码块保持同一口径。
    background: #1e1e1e;
    color: #f8f8f2;
    font-size: @font-size-sm;
    white-space: pre-wrap;
  }
}

// 时间轴
.timeline-title {
  font-weight: @font-weight-medium;
  margin: 0;
}

.timeline-time {
  color: @text-color-light-secondary;
  font-size: @font-size-sm;
  margin: @spacing-xs 0;
}

// JSON 显示
.json-display {
  background: @bg-color-light;
  padding: @spacing-sm;
  border-radius: @border-radius-sm;
  font-size: @font-size-sm;
  overflow-x: auto;
  margin: 0;
}

// 文件列表
.files-section {
  margin-top: @spacing-lg;

  h4 {
    margin-bottom: @spacing-sm;
    color: @text-color-light-secondary;
  }
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: @spacing-xs;
}

.file-item {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  padding: @spacing-sm;
  background: @bg-color-light;
  border-radius: @border-radius-sm;

  .file-name {
    flex: 1;
    .text-ellipsis();
  }

  .file-size {
    color: @text-color-light-tertiary;
    font-size: @font-size-sm;
  }

}

// 工具卡片
.tool-card {
  @media (min-width: @screen-lg) {
    position: sticky;
    top: @spacing-lg;
  }

  .tool-info {
    .tool-header {
      display: flex;
      align-items: center;
      gap: @spacing-md;
      margin-bottom: @spacing-md;
    }

    .tool-icon {
      width: 48px;
      height: 48px;
      border-radius: @border-radius-md;
      background: @accent-color-light;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 24px;
      color: @accent-color;
    }

    .tool-meta {
      .tool-name {
        margin: 0 0 @spacing-xs 0;
        font-size: @font-size-md;
      }

      .tool-version {
        color: @text-color-light-tertiary;
        font-size: @font-size-sm;
      }
    }

    .tool-desc {
      color: @text-color-light-secondary;
      font-size: @font-size-sm;
      margin-bottom: @spacing-md;
    }

    .tool-stats {
      display: flex;
      gap: @spacing-lg;
      margin-bottom: @spacing-lg;

      .stat-item {
        display: flex;
        align-items: center;
        gap: @spacing-xs;
        color: @text-color-light-secondary;
        font-size: @font-size-sm;
      }
    }
  }
}

// 响应式
@media (max-width: @breakpoint-md) {
  .task-detail-actions {
    justify-content: flex-start;
    width: 100%;
  }

  .status-card {
    flex-direction: column;
    align-items: flex-start;

    .status-main {
      width: 100%;
      align-items: flex-start;
    }

    .status-icon {
      font-size: 36px;
    }

    .status-line {
      align-items: flex-start;
      flex-direction: column;
      gap: @spacing-sm;
    }
  }
}
</style>
