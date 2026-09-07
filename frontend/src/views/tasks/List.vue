<template>
  <div class="tasks-page">
    <div class="container">
      <AppPageHeader :title="t('tasks.title')" :subtitle="t('tasks.subtitle')" />
      <ProjectWorkspaceNav v-if="projectId" :project-id="projectId" />

      <!-- 三标签页切换 -->
      <div class="view-tabs">
        <a-tabs v-model:activeKey="currentTab" @change="handleTabChange">
          <a-tab-pane key="all">
            <template #tab>
              <span class="tab-label">
                <UnorderedListOutlined />
                {{ t('tasks.allTasks') }}
                <a-badge v-if="allCount > 0" :count="allCount" :overflow-count="999" class="tab-badge" />
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
                <a-badge
                  v-if="historyCount > 0"
                  :count="historyCount"
                  :overflow-count="999"
                  class="tab-badge"
                />
              </span>
            </template>
          </a-tab-pane>
        </a-tabs>
      </div>

      <!-- 筛选栏 -->
      <AppFilterBar>
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
      </AppFilterBar>

      <!-- 实时监控面板（运行中标签页显示） -->
      <div
        v-if="currentTab === 'running' && runningTasks.length > 0"
        class="monitor-panel"
      >
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
              <span class="tool-name">{{
                task.name || task.tool?.name || t('tasks.unknownTool')
              }}</span>
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
              <div v-if="task.progress_message" class="progress-message">
                {{ task.progress_message }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 任务列表 -->
      <SkeletonList v-if="loading" :count="5" />
      <div v-else-if="hasDisplayItems" class="tasks-list">
        <section v-if="displayTasks.length > 0" class="task-section standalone-task-section">
          <div
            v-for="task in displayTasks"
            :key="task.id"
            class="task-card"
            :class="{ 'is-running': task.status === 'running' }"
            role="button"
            tabindex="0"
            :aria-label="`${task.name || task.tool?.name || t('tasks.unknownTool')} ${getStatusText(task.status)}`"
            @click="goToDetail(task.id)"
            @keydown.enter="goToDetail(task.id)"
            @keydown.space.prevent="goToDetail(task.id)"
          >
            <div class="task-main">
              <div class="task-info">
                <div class="task-header">
                  <div class="tool-icon">
                    <span v-if="task.tool?.icon">{{ task.tool.icon }}</span>
                    <ToolOutlined v-else />
                  </div>
                  <div class="task-meta">
                    <h3 class="task-title">
                      {{ task.name || task.tool?.name || t('tasks.unknownTool') }}
                    </h3>
                    <span class="task-id">
                      <template v-if="task.name && task.tool?.name"
                        >{{ task.tool.name }} ·
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
                    <span>{{ projectContextLabel(task) }}</span>
                    <router-link
                      :to="artifactLineagePath(task)"
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
              </div>
            </div>

            <div class="task-actions" @click.stop>
              <a-space class="task-action-space" wrap>
                <a-tooltip :title="t('tasks.viewDetail')">
                  <a-button type="link" @click="goToDetail(task.id)">
                    <EyeOutlined />
                  </a-button>
                </a-tooltip>
                <a-tooltip
                  v-if="canCancelTask(task)"
                  :title="t('tasks.cancel')"
                >
                  <a-popconfirm :title="t('tasks.cancelConfirm')" @confirm="handleCancel(task.id)">
                    <a-button type="link" danger>
                      <StopOutlined />
                    </a-button>
                  </a-popconfirm>
                </a-tooltip>
                <a-tooltip v-if="canRetryTask(task)" :title="t('tasks.retry')">
                  <a-button type="link" @click="handleRetry(task.id)">
                    <RedoOutlined />
                  </a-button>
                </a-tooltip>
                <a-tooltip
                  v-if="canDeleteTask(task)"
                  :title="t('tasks.delete')"
                >
                  <a-popconfirm :title="t('tasks.deleteConfirm')" @confirm="handleDelete(task.id)">
                    <a-button type="link" danger>
                      <DeleteOutlined />
                    </a-button>
                  </a-popconfirm>
                </a-tooltip>
              </a-space>
            </div>
          </div>
        </section>
      </div>

      <a-empty v-else :description="emptyText">
        <template #extra>
          <a-button type="primary" @click="goToTools">
            {{ t('tasks.goToTools') }}
          </a-button>
        </template>
      </a-empty>

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
  import { useRoute, useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import AppFilterBar from '@/components/common/AppFilterBar.vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import SkeletonList from '@/components/common/SkeletonList.vue'
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
    EyeOutlined,
    RedoOutlined,
    DeleteOutlined,
    ProjectOutlined
  } from '@ant-design/icons-vue'
  import { message } from 'ant-design-vue'
  import type { Dayjs } from 'dayjs'
  import dayjs from 'dayjs'
  import { useTasksStore, useToolsStore, useUserStore } from '@/stores'
  import type { TaskListParams } from '@/api/tasks'
  import { getProjectOverview } from '@/api/projects'
  import {
    buildTaskListQueryParams,
    canCancelTask as canCancelTaskForActor,
    canDeleteTask as canDeleteTaskForActor,
    canRetryTask as canRetryTaskForActor,
    getTaskArtifactLineagePath,
    getTaskProgressColor,
    getTaskProgressStatus,
    getTaskProjectContextLabel,
    getTaskStatusColor,
    isRunningTask,
    type TaskActor,
    type TaskListTab
  } from '@/domain/tasks'
  import type { Task, TaskStatus } from '@/types/models'
  import type { ProjectRole, ResearchProject } from '@/types/projects'

  type TabKey = TaskListTab

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()
  const tasksStore = useTasksStore()
  const toolsStore = useToolsStore()
  const userStore = useUserStore()

  // 状态
  const currentTab = ref<TabKey>('all')
  const searchKeyword = ref('')
  const selectedTool = ref<string | undefined>()
  const dateRange = ref<[Dayjs, Dayjs] | null>(null)
  const currentPage = ref(1)
  const pageSize = ref(10)
  const refreshing = ref(false)
  const autoRefresh = ref(true)
  const project = ref<ResearchProject | null>(null)
  const projectId = computed(() => {
    const value = route.query.project_id
    return typeof value === 'string' && value.trim() ? value : undefined
  })
  const projectMembershipRole = computed<ProjectRole | undefined>(
    () => project.value?.membership.role
  )
  const taskActor = computed<TaskActor>(() => ({
    isAdmin: userStore.isAdmin,
    userId: userStore.user?.id,
    currentProjectId: projectId.value,
    projectRole: projectMembershipRole.value
  }))

  // 计算属性
  const loading = computed(() => tasksStore.loading)
  const tasks = computed(() => tasksStore.tasks)
  const total = computed(() => tasksStore.total)

  const runningTasks = computed(() => displayTasks.value.filter(isRunningTask))
  const allCount = computed(() => currentTab.value === 'all' ? total.value : 0)
  const runningCount = computed(() => currentTab.value === 'running' ? total.value : 0)
  const historyCount = computed(() => currentTab.value === 'history' ? total.value : 0)

  const displayTasks = computed<Task[]>(() => tasks.value)

  const hasDisplayItems = computed(() => displayTasks.value.length > 0)
  const currentTotal = computed(() => total.value)

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
  const getStatusColor = getTaskStatusColor

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

  const getProgressStatus = getTaskProgressStatus
  const getProgressColor = getTaskProgressColor

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

  const fetchTasks = async () => {
    const params: TaskListParams = buildTaskListQueryParams({
      tab: currentTab.value,
      page: currentPage.value,
      pageSize: pageSize.value,
      projectId: projectId.value,
      toolId: selectedTool.value,
      keyword: searchKeyword.value,
      createdFrom: dateRange.value?.[0].startOf('day').toISOString(),
      createdTo: dateRange.value?.[1].endOf('day').toISOString(),
    })

    await tasksStore.fetchTasks(params)
  }

  const fetchTasksSafely = async () => {
    try {
      await fetchTasks()
    } catch (error) {
      console.warn('[TaskCenter] Failed to load tasks', error)
    }
  }

  const fetchToolsSafely = async () => {
    try {
      await toolsStore.fetchTools({ page: 1, page_size: 100 })
    } catch (error) {
      console.warn('[TaskCenter] Failed to load tool filter options', error)
    }
  }

  const fetchProjectContextSafely = async () => {
    if (!projectId.value) {
      project.value = null
      return
    }

    try {
      const response = await getProjectOverview(projectId.value)
      project.value = response.data.project
    } catch (error) {
      project.value = null
      console.warn('[TaskCenter] Failed to load project context', error)
    }
  }

  const canCancelTask = (task: Task) => canCancelTaskForActor(task, taskActor.value)
  const canRetryTask = (task: Task) => canRetryTaskForActor(task, taskActor.value)
  const canDeleteTask = (task: Task) => canDeleteTaskForActor(task, taskActor.value)

  const projectContextLabel = (task: Task) =>
    getTaskProjectContextLabel(task, {
      currentProjectId: projectId.value,
      currentProjectName: project.value?.name
    })

  const artifactLineagePath = getTaskArtifactLineagePath

  const handleTabChange = (_key: string) => {
    currentPage.value = 1
    void fetchTasksSafely()
  }

  const handleSearch = () => {
    currentPage.value = 1
    void fetchTasksSafely()
  }

  const handleToolChange = () => {
    currentPage.value = 1
    void fetchTasksSafely()
  }

  const handleDateChange = () => {
    currentPage.value = 1
    void fetchTasksSafely()
  }

  const handleRefresh = async () => {
    refreshing.value = true
    try {
      const [taskResult] = await Promise.allSettled([fetchTasks()])
      if (taskResult.status === 'fulfilled') {
        message.success(t('common.refreshSuccess'))
      } else {
        message.error(t('common.error'))
      }
    } finally {
      refreshing.value = false
    }
  }

  const handlePageChange = (page: number) => {
    currentPage.value = page
    void fetchTasksSafely()
  }

  const handlePageSizeChange = (_current: number, size: number) => {
    pageSize.value = size
    currentPage.value = 1
    void fetchTasksSafely()
  }

  const handleCancel = async (id: string) => {
    await tasksStore.cancelTask(id)
    message.success(t('tasks.cancelSuccess'))
    await fetchTasksSafely()
  }

  const handleRetry = async (id: string) => {
    await tasksStore.retryTask(id)
    message.success(t('tasks.retrySuccess'))
    await fetchTasksSafely()
  }

  const handleDelete = async (id: string) => {
    await tasksStore.deleteTask(id)
    message.success(t('tasks.deleteSuccess'))
    await fetchTasksSafely()
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
        void fetchTasksSafely()
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
  watch(autoRefresh, val => {
    if (val) {
      startAutoRefresh()
    } else {
      stopAutoRefresh()
    }
  })

  watch(projectId, () => {
    currentPage.value = 1
    void fetchTasksSafely()
    void fetchProjectContextSafely()
  })

  // 生命周期
  onMounted(async () => {
    await Promise.allSettled([fetchTasksSafely(), fetchToolsSafely(), fetchProjectContextSafely()])

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
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.6;
    }
  }

  // 实时监控面板
  .monitor-panel {
    .card();
    margin-bottom: @spacing-xl;
    background: linear-gradient(135deg, @accent-color-light 0%, @bg-elevated 100%);

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
      background: @bg-elevated;
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

        .progress-message {
          margin-top: @spacing-xs;
          color: @text-color-light-secondary;
          font-size: @font-size-xs;
          line-height: @line-height-base;
          word-break: break-word;
        }
      }
    }
  }

  // 任务列表
  .tasks-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-lg;
  }

  .task-section {
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
    }

    .task-details {
      display: flex;
      flex-wrap: wrap;
      gap: @spacing-lg;
      color: @text-color-light-secondary;
      font-size: @font-size-sm;

      .detail-item {
        display: flex;
        align-items: center;
        gap: @spacing-xs;
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
    }

    .task-actions {
      border-left: 1px solid @border-color-light;
      padding-left: @spacing-md;
      margin-left: @spacing-md;

      .task-action-space {
        justify-content: flex-end;
      }
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

        .task-action-space {
          justify-content: flex-start;
        }
      }
    }

    .monitor-cards {
      grid-template-columns: 1fr !important;
    }
  }
</style>
