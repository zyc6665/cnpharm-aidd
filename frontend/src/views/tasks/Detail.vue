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

      <a-spin :spinning="loading">
          <div v-if="task" class="detail-content">
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
                    v-if="['success', 'failure', 'canceled'].includes(taskStatus)"
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
              <div v-if="taskStatus === 'failure' && task.error_message" class="info-card error">
                <h3 class="card-title">
                  <CloseCircleOutlined />
                  {{ t('tasks.errorMessage') }}
                </h3>
                <a-alert
                  type="error"
                  show-icon
                  :message="task.error_message"
                />
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
                <a-empty v-else :description="t('tasks.toolNotFound')" />
              </div>

              <!-- 相关任务 -->
              <div v-if="relatedTasks.length > 0" class="info-card">
                <h3 class="card-title">
                  <HistoryOutlined />
                  {{ t('tasks.relatedTasks') }}
                </h3>
                <div class="related-tasks">
                  <div
                    v-for="related in relatedTasks"
                    :key="related.id"
                    class="related-task-item"
                    @click="goToTask(related.id)"
                  >
                    <a-tag :color="getStatusColor(related.status)" size="small">
                      {{ getStatusText(related.status) }}
                    </a-tag>
                    <span class="task-time">{{ formatTime(related.created_at) }}</span>
                  </div>
                </div>
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
      </a-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
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
  PlayCircleOutlined,
  HistoryOutlined
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import dayjs from 'dayjs'
import { useTasksStore } from '@/stores'
import { useWebSocket } from '@/composables/useWebSocket'
import { getTaskLogs } from '@/api/tasks'
import type { WSMessage, TaskStatus, TaskLog, Task } from '@/types/models'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import ResultVisualizationPanel from '@/components/tasks/ResultVisualizationPanel.vue'
import TaskLogPreview from '@/components/tasks/TaskLogPreview.vue'
import TaskOutputSummary from '@/components/tasks/TaskOutputSummary.vue'
import { normalizeTaskStatus } from '@/components/tasks/result-visualization'
import { extractTaskLogs } from './logs'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const tasksStore = useTasksStore()

const taskId = computed(() => route.params.id as string)

// 状态
const logs = ref<TaskLog[]>([])
const logsLoading = ref(false)
const relatedTasks = ref<Task[]>([])

// WebSocket
const { connect, disconnect, onMessage } = useWebSocket()

const normalizeLogLevel = (level?: string): 'info' | 'warning' | 'error' => {
  const normalized = level?.toLowerCase()
  if (normalized === 'warning' || normalized === 'error') {
    return normalized
  }
  return 'info'
}

// 计算属性
const loading = computed(() => tasksStore.loading)
const task = computed(() => tasksStore.currentTask)
const taskStatus = computed<TaskStatus>(() => normalizeTaskStatus(task.value?.status))
const detailTitle = computed(() => task.value?.name || task.value?.tool?.name || t('tasks.taskDetail'))
const detailSubtitle = computed(() => {
  if (!task.value) {
    return t('tasks.detail')
  }

  return `${getStatusText(taskStatus.value)} · ${formatTime(task.value.created_at)}`
})

// 方法
const getStatusColor = (status: TaskStatus) => {
  const colors: Record<TaskStatus, string> = {
    pending: 'orange',
    running: 'processing',
    success: 'success',
    failure: 'error',
    canceled: 'default'
  }
  return colors[status]
}

const getStatusText = (status: TaskStatus) => {
  const texts: Record<TaskStatus, string> = {
    pending: t('tasks.statusPending'),
    running: t('tasks.statusRunning'),
    success: t('tasks.statusSuccess'),
    failure: t('tasks.statusFailure'),
    canceled: t('tasks.statusCanceled')
  }
  return texts[status]
}

const getCompletedTitle = (status: TaskStatus) => {
  const titles: Record<string, string> = {
    success: t('tasks.completed'),
    failure: t('tasks.failed'),
    canceled: t('tasks.canceled')
  }
  return titles[status] || t('tasks.completed')
}

const formatTime = (time: string) => {
  return dayjs(time).format('YYYY-MM-DD HH:mm:ss')
}

const formatFileSize = (bytes?: number) => {
  if (!bytes || bytes === 0) {
    return '0 B'
  }

  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
}

const copyTaskId = async () => {
  if (task.value) {
    await navigator.clipboard.writeText(task.value.id)
    message.success(t('common.copySuccess'))
  }
}

const fetchTaskDetail = async () => {
  await tasksStore.fetchTaskDetail(taskId.value)
}

const fetchLogs = async () => {
  logsLoading.value = true
  try {
    const res = await getTaskLogs(taskId.value)
    logs.value = extractTaskLogs(res.data)
  } catch {
    // 错误已处理
  } finally {
    logsLoading.value = false
  }
}

const handleCancel = () => {
  Modal.confirm({
    title: t('tasks.cancelConfirm'),
    content: t('tasks.cancelConfirmContent'),
    okText: t('common.confirm'),
    cancelText: t('common.cancel'),
    onOk: async () => {
      await tasksStore.cancelTask(taskId.value)
      message.success(t('tasks.cancelSuccess'))
    }
  })
}

const handleRetry = async () => {
  await tasksStore.retryTask(taskId.value)
  message.success(t('tasks.retrySuccess'))
}

const handleDelete = () => {
  Modal.confirm({
    title: t('tasks.deleteConfirm'),
    content: t('tasks.deleteConfirmContent'),
    okText: t('common.confirm'),
    okType: 'danger',
    cancelText: t('common.cancel'),
    onOk: async () => {
      await tasksStore.deleteTask(taskId.value)
      message.success(t('tasks.deleteSuccess'))
      router.push('/tasks')
    }
  })
}

const goToTool = () => {
  if (task.value?.tool_id) {
    router.push(`/tools/${task.value.tool_id}`)
  }
}

const goToTask = (id: string) => {
  router.push(`/tasks/${id}`)
}

const goBack = () => {
  router.push('/tasks')
}

// WebSocket 消息处理
const handleWSMessage = (msg: WSMessage) => {
  if (msg.task_id !== taskId.value) return

  if (msg.type === 'task_progress') {
    const nextStatus = msg.status ? normalizeTaskStatus(msg.status) : undefined
    const progress = typeof msg.progress_percent === 'number'
      ? msg.progress_percent
      : Math.round((msg.progress ?? 0) * 100)
    tasksStore.updateTaskProgress(msg.task_id!, progress, nextStatus)
  } else if (msg.type === 'task_log' && msg.log) {
    logs.value.push({
      id: Date.now(),
      task_id: msg.task_id!,
      level: normalizeLogLevel(msg.level),
      message: msg.log,
      timestamp: new Date().toISOString()
    })
  } else if (msg.type === 'task_status' && msg.status) {
    const nextStatus = normalizeTaskStatus(msg.status)
    tasksStore.updateTaskProgress(taskId.value, task.value?.progress ?? 0, nextStatus)
    if (['success', 'failure', 'canceled'].includes(nextStatus)) {
      void fetchTaskDetail()
      void fetchLogs()
    }
  } else if (msg.type === 'task_complete') {
    tasksStore.updateTaskProgress(taskId.value, 100, 'success')
    void fetchTaskDetail()
    void fetchLogs()
  } else if (msg.type === 'task_error') {
    tasksStore.updateTaskProgress(taskId.value, task.value?.progress ?? 0, 'failure')
    if (msg.error) {
      logs.value.push({
        id: Date.now(),
        task_id: msg.task_id!,
        level: 'error',
        message: msg.error,
        timestamp: new Date().toISOString()
      })
    }
    void fetchTaskDetail()
    void fetchLogs()
  }
}

// 定时刷新
let refreshTimer: ReturnType<typeof setInterval> | null = null

const startRefresh = () => {
  if (refreshTimer) return
  refreshTimer = setInterval(() => {
    if (taskStatus.value === 'running') {
      fetchTaskDetail()
    }
  }, 5000)
}

const stopRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

// 监听任务状态变化
watch(taskStatus, status => {
  if (status === 'running') {
    startRefresh()
    return
  }

  stopRefresh()

  if (['success', 'failure', 'canceled'].includes(status)) {
    void fetchLogs()
  }
})

// 生命周期
onMounted(async () => {
  await fetchTaskDetail()
  await fetchLogs()

  // 连接 WebSocket
  connect(`/api/v1/ws/tasks/${taskId.value}`)
  onMessage(handleWSMessage)

  // 如果任务正在运行，启动定时刷新
  if (taskStatus.value === 'running') {
    startRefresh()
  }
})

onUnmounted(() => {
  disconnect()
  stopRefresh()
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
    background: linear-gradient(90deg, @primary-color-light 0%, #fff 20%);
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

  &.downloadable:hover {
    background: @primary-color-light;
  }
}

.download-all-btn {
  margin-top: @spacing-md;
}

// 日志容器
.logs-container {
  max-height: 400px;
  overflow-y: auto;
  background: #1e1e1e;
  border-radius: @border-radius-md;
  padding: @spacing-md;
}

.logs-list {
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 12px;
}

.log-item {
  display: flex;
  align-items: flex-start;
  gap: @spacing-sm;
  padding: @spacing-xs 0;
  color: #d4d4d4;

  &.log-error {
    color: #f48771;
  }

  &.log-warning {
    color: #cca700;
  }

  .log-time {
    color: #808080;
    min-width: 90px;
  }

  .log-message {
    flex: 1;
    word-break: break-all;
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

// 相关任务
.related-tasks {
  display: flex;
  flex-direction: column;
  gap: @spacing-xs;
}

.related-task-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: @spacing-sm;
  background: @bg-color-light;
  border-radius: @border-radius-sm;
  cursor: pointer;
  transition: all @transition-duration;

  &:hover {
    background: @primary-color-light;
  }

  .task-time {
    color: @text-color-light-tertiary;
    font-size: @font-size-sm;
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
