<template>
  <div class="tasks-page">
    <div class="container">
      <div class="page-header">
        <h1 class="page-title">{{ t('tasks.title') }}</h1>
        <p class="page-subtitle">{{ t('tasks.subtitle') }}</p>
      </div>

      <!-- 三标签页切换 -->
      <div class="view-tabs">
        <a-tabs v-model:activeKey="currentTab" @change="handleTabChange">
          <a-tab-pane key="all">
            <template #tab>
              <span class="tab-label">
                <UnorderedListOutlined />
                {{ t('tasks.allTasks') }}
                <a-badge v-if="total > 0" :count="total" :overflow-count="999" class="tab-badge" />
              </span>
            </template>
          </a-tab-pane>
          <a-tab-pane key="running">
            <template #tab>
              <span class="tab-label">
                <LoadingOutlined v-if="runningCount > 0" spin />
                <SyncOutlined v-else />
                {{ t('tasks.runningTasks') }}
                <a-badge
                  v-if="runningCount > 0"
                  :count="runningCount"
                  :overflow-count="99"
                  class="tab-badge running"
                />
              </span>
            </template>
          </a-tab-pane>
          <a-tab-pane key="history">
            <template #tab>
              <span class="tab-label">
                <HistoryOutlined />
                {{ t('tasks.historyTasks') }}
                <a-badge v-if="historyCount > 0" :count="historyCount" :overflow-count="999" class="tab-badge" />
              </span>
            </template>
          </a-tab-pane>
        </a-tabs>
      </div>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <a-input-search
          v-model:value="searchKeyword"
          :placeholder="t('tasks.searchPlaceholder')"
          size="large"
          style="max-width: 300px"
          allow-clear
          @search="handleSearch"
        />
        <a-select
          v-model:value="selectedTool"
          :placeholder="t('tasks.filterByTool')"
          size="large"
          style="width: 200px"
          allow-clear
          @change="handleToolChange"
        >
          <a-select-option v-for="tool in toolOptions" :key="tool.id" :value="tool.id">
            {{ tool.name }}
          </a-select-option>
        </a-select>
        <a-range-picker
          v-if="currentTab === 'history'"
          v-model:value="dateRange"
          size="large"
          :placeholder="[t('tasks.startDate'), t('tasks.endDate')]"
          @change="handleDateChange"
        />
        <a-button
          v-if="currentTab === 'running'"
          type="primary"
          :loading="refreshing"
          @click="handleRefresh"
        >
          <template #icon><ReloadOutlined /></template>
          {{ t('common.refresh') }}
        </a-button>
      </div>

      <!-- 实时监控面板（运行中标签页显示） -->
      <div v-if="currentTab === 'running' && runningTasks.length > 0" class="monitor-panel">
        <div class="monitor-header">
          <h3>
            <DashboardOutlined />
            {{ t('tasks.realTimeMonitor') }}
          </h3>
          <a-switch
            v-model:checked="autoRefresh"
            :checked-children="t('tasks.autoRefreshOn')"
            :un-checked-children="t('tasks.autoRefreshOff')"
          />
        </div>
        <div class="monitor-cards">
          <div
            v-for="task in runningTasks.slice(0, 4)"
            :key="task.id"
            class="monitor-card"
            @click="goToDetail(task.id)"
          >
            <div class="monitor-card-header">
              <span class="tool-name">{{ task.tool?.name || t('tasks.unknownTool') }}</span>
              <a-tag :color="getStatusColor(task.status)">
                {{ getStatusText(task.status) }}
              </a-tag>
            </div>
            <div class="monitor-card-body">
              <a-progress
                :percent="task.progress"
                :status="getProgressStatus(task.status)"
                :stroke-color="getProgressColor(task.status)"
              />
              <div class="task-time">
                <ClockCircleOutlined />
                {{ formatDuration(task.started_at) }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 任务列表 -->
      <a-spin :spinning="loading">
        <div v-if="displayTasks.length" class="tasks-list">
          <div
            v-for="task in displayTasks"
            :key="task.id"
            class="task-card"
            :class="{ 'is-running': task.status === 'running' }"
            @click="goToDetail(task.id)"
          >
            <div class="task-main">
              <div class="task-info">
                <div class="task-header">
                  <div class="tool-icon">
                    <span v-if="task.tool?.icon">{{ task.tool.icon }}</span>
                    <ToolOutlined v-else />
                  </div>
                  <div class="task-meta">
                    <h3 class="task-title">{{ task.tool?.name || t('tasks.unknownTool') }}</h3>
                    <span class="task-id">ID: {{ task.id.slice(0, 8) }}...</span>
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
                </div>
              </div>

              <div class="task-status-section">
                <a-tag :color="getStatusColor(task.status)" class="status-tag">
                  <template #icon>
                    <LoadingOutlined v-if="task.status === 'running'" spin />
                    <ClockCircleOutlined v-else-if="task.status === 'pending'" />
                    <CheckCircleOutlined v-else-if="task.status === 'success'" />
                    <CloseCircleOutlined v-else-if="task.status === 'failure'" />
                    <StopOutlined v-else-if="task.status === 'canceled'" />
                  </template>
                  {{ getStatusText(task.status) }}
                </a-tag>

                <div v-if="task.status === 'running'" class="progress-section">
                  <a-progress
                    type="circle"
                    :percent="task.progress"
                    :width="60"
                    :stroke-color="getProgressColor(task.status)"
                  />
                </div>

                <div v-if="task.status === 'success' && task.completed_at && task.started_at" class="duration">
                  <FieldTimeOutlined />
                  {{ calculateDuration(task.started_at, task.completed_at) }}
                </div>
              </div>
            </div>

            <div class="task-actions" @click.stop>
              <a-space>
                <a-tooltip :title="t('tasks.viewDetail')">
                  <a-button type="link" @click="goToDetail(task.id)">
                    <EyeOutlined />
                  </a-button>
                </a-tooltip>
                <a-tooltip v-if="task.status === 'running' || task.status === 'pending'" :title="t('tasks.cancel')">
                  <a-popconfirm
                    :title="t('tasks.cancelConfirm')"
                    @confirm="handleCancel(task.id)"
                  >
                    <a-button type="link" danger>
                      <StopOutlined />
                    </a-button>
                  </a-popconfirm>
                </a-tooltip>
                <a-tooltip v-if="task.status === 'failure'" :title="t('tasks.retry')">
                  <a-button type="link" @click="handleRetry(task.id)">
                    <RedoOutlined />
                  </a-button>
                </a-tooltip>
                <a-tooltip v-if="task.status === 'success' || task.status === 'failure' || task.status === 'canceled'" :title="t('tasks.delete')">
                  <a-popconfirm
                    :title="t('tasks.deleteConfirm')"
                    @confirm="handleDelete(task.id)"
                  >
                    <a-button type="link" danger>
                      <DeleteOutlined />
                    </a-button>
                  </a-popconfirm>
                </a-tooltip>
              </a-space>
            </div>
          </div>
        </div>

        <a-empty v-else :description="emptyText">
          <template #extra>
            <a-button type="primary" @click="goToTools">
              {{ t('tasks.goToTools') }}
            </a-button>
          </template>
        </a-empty>
      </a-spin>

      <!-- 分页 -->
      <div v-if="currentTotal > pageSize" class="pagination">
        <a-pagination
          v-model:current="currentPage"
          :total="currentTotal"
          :page-size="pageSize"
          :show-total="(total: number) => t('common.totalItems', { total })"
          show-quick-jumper
          show-size-changer
          :page-size-options="['10', '20', '50']"
          @change="handlePageChange"
          @show-size-change="handlePageSizeChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  UnorderedListOutlined,
  SyncOutlined,
  LoadingOutlined,
  HistoryOutlined,
  ReloadOutlined,
  DashboardOutlined,
  ClockCircleOutlined,
  ToolOutlined,
  CalendarOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  StopOutlined,
  FieldTimeOutlined,
  EyeOutlined,
  RedoOutlined,
  DeleteOutlined
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { Dayjs } from 'dayjs'
import dayjs from 'dayjs'
import { useTasksStore, useToolsStore } from '@/stores'
import type { TaskStatus } from '@/types/models'

type TabKey = 'all' | 'running' | 'history'

const router = useRouter()
const { t } = useI18n()
const tasksStore = useTasksStore()
const toolsStore = useToolsStore()

// 状态
const currentTab = ref<TabKey>('all')
const searchKeyword = ref('')
const selectedTool = ref<number | undefined>()
const dateRange = ref<[Dayjs, Dayjs] | null>(null)
const currentPage = ref(1)
const pageSize = ref(10)
const refreshing = ref(false)
const autoRefresh = ref(true)

// 计算属性
const loading = computed(() => tasksStore.loading)
const tasks = computed(() => tasksStore.tasks)
const total = computed(() => tasksStore.total)

const runningTasks = computed(() =>
  tasks.value.filter(t => t.status === 'running' || t.status === 'pending')
)
const runningCount = computed(() => runningTasks.value.length)

const historyTasks = computed(() =>
  tasks.value.filter(t => ['success', 'failure', 'canceled'].includes(t.status))
)
const historyCount = computed(() => historyTasks.value.length)

const displayTasks = computed(() => {
  let filtered = tasks.value

  // 根据标签页筛选
  if (currentTab.value === 'running') {
    filtered = filtered.filter(t => t.status === 'running' || t.status === 'pending')
  } else if (currentTab.value === 'history') {
    filtered = filtered.filter(t => ['success', 'failure', 'canceled'].includes(t.status))
  }

  // 关键词搜索
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    filtered = filtered.filter(t =>
      t.tool?.name?.toLowerCase().includes(keyword) ||
      t.id.toLowerCase().includes(keyword)
    )
  }

  return filtered
})

const currentTotal = computed(() => {
  switch (currentTab.value) {
    case 'running':
      return runningCount.value
    case 'history':
      return historyCount.value
    default:
      return total.value
  }
})

const toolOptions = computed(() => toolsStore.tools || [])

const emptyText = computed(() => {
  switch (currentTab.value) {
    case 'running':
      return t('tasks.noRunningTasks')
    case 'history':
      return t('tasks.noHistoryTasks')
    default:
      return t('tasks.noTasks')
  }
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

const getProgressStatus = (status: TaskStatus) => {
  if (status === 'running') return 'active'
  if (status === 'failure') return 'exception'
  if (status === 'success') return 'success'
  return 'normal'
}

const getProgressColor = (status: TaskStatus) => {
  if (status === 'running') return '#1890ff'
  if (status === 'failure') return '#ff4d4f'
  return '#52c41a'
}

const formatTime = (time: string) => {
  return dayjs(time).format('YYYY-MM-DD HH:mm:ss')
}

const formatDuration = (startTime?: string) => {
  if (!startTime) return '--'
  const start = dayjs(startTime)
  const now = dayjs()
  const diff = now.diff(start, 'second')

  if (diff < 60) return `${diff}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ${diff % 60}s`
  return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`
}

const calculateDuration = (start: string, end: string) => {
  const diff = dayjs(end).diff(dayjs(start), 'second')
  if (diff < 60) return `${diff}s`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ${diff % 60}s`
  return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`
}

const fetchTasks = async () => {
  const params: Record<string, unknown> = {
    page: currentPage.value,
    page_size: pageSize.value
  }

  if (selectedTool.value) {
    params.tool_id = selectedTool.value
  }

  if (currentTab.value === 'running') {
    params.status = 'running'
  } else if (currentTab.value === 'history') {
    // 历史任务包含成功、失败、取消状态
  }

  await tasksStore.fetchTasks(params)
}

const handleTabChange = (_key: string) => {
  currentPage.value = 1
  fetchTasks()
}

const handleSearch = () => {
  currentPage.value = 1
  fetchTasks()
}

const handleToolChange = () => {
  currentPage.value = 1
  fetchTasks()
}

const handleDateChange = () => {
  currentPage.value = 1
  fetchTasks()
}

const handleRefresh = async () => {
  refreshing.value = true
  try {
    await fetchTasks()
    message.success(t('common.refreshSuccess'))
  } finally {
    refreshing.value = false
  }
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  fetchTasks()
}

const handlePageSizeChange = (_current: number, size: number) => {
  pageSize.value = size
  currentPage.value = 1
  fetchTasks()
}

const handleCancel = async (id: string) => {
  await tasksStore.cancelTask(id)
  message.success(t('tasks.cancelSuccess'))
}

const handleRetry = async (id: string) => {
  await tasksStore.retryTask(id)
  message.success(t('tasks.retrySuccess'))
}

const handleDelete = async (id: string) => {
  await tasksStore.deleteTask(id)
  message.success(t('tasks.deleteSuccess'))
}

const goToDetail = (id: string) => {
  router.push(`/tasks/${id}`)
}

const goToTools = () => {
  router.push('/tools')
}

// 自动刷新定时器
let refreshTimer: ReturnType<typeof setInterval> | null = null

const startAutoRefresh = () => {
  if (refreshTimer) return
  refreshTimer = setInterval(() => {
    if (autoRefresh.value && currentTab.value === 'running') {
      fetchTasks()
    }
  }, 10000) // 每10秒刷新
}

const stopAutoRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

// 监听自动刷新开关
watch(autoRefresh, (val) => {
  if (val) {
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
})

// 生命周期
onMounted(async () => {
  await Promise.all([
    fetchTasks(),
    toolsStore.fetchTools({ page: 1, page_size: 100 })
  ])

  startAutoRefresh()
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.tasks-page {
  padding: @spacing-xl 0;
  min-height: calc(100vh - @header-height - @footer-height);
}

.page-header {
  text-align: center;
  margin-bottom: @spacing-xl;
}

.page-title {
  font-size: @font-size-xxxl;
  font-weight: @font-weight-bold;
  margin-bottom: @spacing-sm;
}

.page-subtitle {
  color: @text-color-light-secondary;
  font-size: @font-size-lg;
}

// 视图切换标签
.view-tabs {
  margin-bottom: @spacing-lg;

  :deep(.ant-tabs-nav) {
    margin-bottom: 0;

    &::before {
      border-bottom: none;
    }
  }

  .tab-label {
    display: flex;
    align-items: center;
    gap: @spacing-xs;

    .anticon {
      font-size: 16px;
    }
  }

  .tab-badge {
    margin-left: @spacing-xs;

    :deep(.ant-badge-count) {
      background: @accent-color;
      font-size: 10px;
      height: 16px;
      min-width: 16px;
      line-height: 16px;
    }

    &.running :deep(.ant-badge-count) {
      background: @primary-color;
      animation: pulse 1.5s infinite;
    }
  }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.filter-bar {
  display: flex;
  gap: @spacing-md;
  margin-bottom: @spacing-xl;
  flex-wrap: wrap;
}

// 实时监控面板
.monitor-panel {
  .card();
  margin-bottom: @spacing-xl;
  background: linear-gradient(135deg, @primary-color-light 0%, #fff 100%);

  .monitor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: @spacing-lg;

    h3 {
      display: flex;
      align-items: center;
      gap: @spacing-sm;
      margin: 0;
      font-size: @font-size-lg;
      color: @primary-color;
    }
  }

  .monitor-cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: @spacing-md;
  }

  .monitor-card {
    background: #fff;
    border-radius: @border-radius-md;
    padding: @spacing-md;
    cursor: pointer;
    transition: all @transition-duration;
    border: 1px solid @border-color-light;

    &:hover {
      transform: translateY(-2px);
      box-shadow: @shadow-md;
    }

    .monitor-card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: @spacing-sm;

      .tool-name {
        font-weight: @font-weight-medium;
        .text-ellipsis();
        max-width: 150px;
      }
    }

    .monitor-card-body {
      .task-time {
        display: flex;
        align-items: center;
        gap: @spacing-xs;
        color: @text-color-light-tertiary;
        font-size: @font-size-sm;
        margin-top: @spacing-xs;
      }
    }
  }
}

// 任务列表
.tasks-list {
  display: flex;
  flex-direction: column;
  gap: @spacing-md;
}

.task-card {
  .card();
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;

  &:hover {
    transform: translateX(4px);
  }

  &.is-running {
    border-left: 3px solid @primary-color;
    background: linear-gradient(90deg, @primary-color-light 0%, #fff 10%);
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
    .task-title {
      font-size: @font-size-md;
      font-weight: @font-weight-semibold;
      margin: 0 0 @spacing-xs 0;
    }

    .task-id {
      color: @text-color-light-tertiary;
      font-size: @font-size-sm;
      font-family: monospace;
    }
  }

  .task-details {
    display: flex;
    gap: @spacing-lg;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;

    .detail-item {
      display: flex;
      align-items: center;
      gap: @spacing-xs;
    }
  }

  .task-status-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: @spacing-sm;
    min-width: 120px;

    .status-tag {
      font-size: @font-size-sm;
    }

    .duration {
      display: flex;
      align-items: center;
      gap: @spacing-xs;
      color: @text-color-light-tertiary;
      font-size: @font-size-sm;
    }
  }

  .task-actions {
    border-left: 1px solid @border-color-light;
    padding-left: @spacing-md;
    margin-left: @spacing-md;
  }
}

.pagination {
  display: flex;
  justify-content: center;
  margin-top: @spacing-xl;
}

// 响应式
@media (max-width: @breakpoint-md) {
  .task-card {
    flex-direction: column;
    align-items: flex-start;
    gap: @spacing-md;

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
  }

  .monitor-cards {
    grid-template-columns: 1fr !important;
  }
}
</style>
