<template>
  <div class="tasks-page">
    <div class="container">
      <AppPageHeader :title="t('tasks.title')" :subtitle="t('tasks.subtitle')" />
      <ProjectWorkspaceNav v-if="projectId" :project-id="projectId" />
      <a-alert
        v-if="workflowScopeText"
        class="task-scope-alert"
        type="info"
        show-icon
        :message="workflowScopeText"
      />

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
          <a-tab-pane key="needs_attention">
            <template #tab>
              <span class="tab-label">
                <CloseCircleOutlined />
                {{ t('tasks.attentionTasks') }}
                <a-badge
                  v-if="attentionCount > 0"
                  :count="attentionCount"
                  :overflow-count="99"
                  class="tab-badge attention"
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
          <TaskListCard
            v-for="task in displayTasks"
            :key="task.id"
            :task="task"
            :actor="taskActor"
            :current-project-id="projectId"
            :current-project-name="project?.name"
            :project-names="projectNames"
            @open="goToDetail"
            @cancel="handleCancel"
            @retry="handleRetry"
            @delete="handleDelete"
          />
        </section>
      </div>

      <!-- 原来这里是 `<a-empty>` + `<template #extra>`。antd 的 Empty 只有
           `description`/`image`/默认插槽三个位置，没有 `extra`——那个「去工具页」
           按钮其实从来没有渲染出来过。换成自绘空状态后按钮走默认插槽，真的能点了。 -->
      <AppEmptyState
        v-else
        :title="emptyText"
        description="任务按工具版本执行；提交后进入队列、分配算力、产出结果，全过程可追溯。"
      >
        <a-button type="primary" @click="goToTools">
          {{ t('tasks.goToTools') }}
        </a-button>
      </AppEmptyState>

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
  import AppEmptyState from '@/components/common/AppEmptyState.vue'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import SkeletonList from '@/components/common/SkeletonList.vue'
  import TaskListCard from '@/components/tasks/TaskListCard.vue'
  import {
    UnorderedListOutlined,
    SyncOutlined,
    LoadingOutlined,
    HistoryOutlined,
    ReloadOutlined,
    DashboardOutlined,
    ClockCircleOutlined,
    CloseCircleOutlined,
  } from '@ant-design/icons-vue'
  import { message } from 'ant-design-vue'
  import { resolvePaginationChange } from '@/utils/pagination'
  import type { Dayjs } from 'dayjs'
  import { useTasksStore, useToolsStore, useUserStore } from '@/stores'
  import type { TaskListParams } from '@/api/tasks'
  import { getProjectOverview, listProjects } from '@/api/projects'
  import {
    buildTaskListViewModel,
    buildTaskCountQueryParams,
    buildTaskListQueryParams,
    buildTaskWorkflowScopeParts,
    formatTaskRunningDuration,
    getTaskListEmptyTextKey,
    getTaskProgressColor,
    getTaskProgressStatus,
    getTaskStatusColor,
    getTaskStatusTextKey,
    taskListTabFromQueryParam,
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
  const routeTab = computed<TabKey>(() => taskListTabFromQueryParam(route.query.view))
  const currentTab = ref<TabKey>(routeTab.value)
  const searchKeyword = ref('')
  const selectedTool = ref<string | undefined>()
  const dateRange = ref<[Dayjs, Dayjs] | null>(null)
  const currentPage = ref(1)
  const pageSize = ref(10)
  const refreshing = ref(false)
  const autoRefresh = ref(true)
  const project = ref<ResearchProject | null>(null)
  const projectNames = ref<Record<string, string>>({})
  const projectId = computed(() => stringQueryParam(route.query.project_id))
  const workflowRunId = computed(() => stringQueryParam(route.query.workflow_run_id))
  const workflowDefinitionId = computed(() => stringQueryParam(route.query.workflow_definition_id))
  const workflowNodeId = computed(() => stringQueryParam(route.query.workflow_node_id))
  const workflowScopeParts = computed(() => buildTaskWorkflowScopeParts({
    workflowRunId: workflowRunId.value,
    workflowDefinitionId: workflowDefinitionId.value,
    workflowNodeId: workflowNodeId.value,
  }))
  const projectMembershipRole = computed<ProjectRole | undefined>(
    () => project.value?.membership?.role
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
  const taskViewCounts = computed(() => tasksStore.viewCounts)
  const taskListViewModel = computed(() => buildTaskListViewModel({
    tasks: tasks.value,
    tab: currentTab.value,
    keyword: searchKeyword.value,
    counts: taskViewCounts.value,
  }))

  const runningTasks = computed(() => taskListViewModel.value.runningTasks)
  const allCount = computed(() => taskListViewModel.value.counts.all)
  const runningCount = computed(() => taskListViewModel.value.counts.running)
  const attentionCount = computed(() => taskListViewModel.value.counts.attention)
  const historyCount = computed(() => taskListViewModel.value.counts.history)
  const displayTasks = computed<Task[]>(() => taskListViewModel.value.displayTasks)
  const hasDisplayItems = computed(() => taskListViewModel.value.hasDisplayItems)
  const currentTotal = computed(() => total.value)

  const toolOptions = computed(() => toolsStore.tools || [])

  const emptyText = computed(() => t(getTaskListEmptyTextKey(currentTab.value)))

  const workflowScopeText = computed(() => {
    if (workflowScopeParts.value.length === 0) {
      return ''
    }
    const scope = workflowScopeParts.value
      .map(part => t(`tasks.workflowScope.${part.key}`, { id: part.value }))
      .join(' · ')
    return t('tasks.workflowScope.active', { scope })
  })

  // 方法
  const getStatusColor = getTaskStatusColor

  const getStatusText = (status: TaskStatus) => t(getTaskStatusTextKey(status))

  const getProgressStatus = getTaskProgressStatus
  const getProgressColor = getTaskProgressColor

  const formatDuration = (startTime?: string) => {
    if (!startTime) return '--'
    return formatTaskRunningDuration(startTime)
  }

  const fetchTasks = async () => {
    const params: TaskListParams = buildTaskListQueryParams(buildTaskQueryInput())

    await tasksStore.fetchTasks(params)
  }

  const fetchTaskCounts = async () => {
    await tasksStore.fetchTaskCounts(buildTaskCountQueryParams(buildTaskQueryInput()))
  }

  const buildTaskQueryInput = () => ({
    tab: currentTab.value,
    page: currentPage.value,
    pageSize: pageSize.value,
    projectId: projectId.value,
    toolId: selectedTool.value,
    keyword: searchKeyword.value,
    createdFrom: dateRange.value?.[0].startOf('day').toISOString(),
    createdTo: dateRange.value?.[1].endOf('day').toISOString(),
    workflowRunId: workflowRunId.value,
    workflowDefinitionId: workflowDefinitionId.value,
    workflowNodeId: workflowNodeId.value,
  })

  const fetchTasksSafely = async () => {
    try {
      await fetchTasks()
    } catch (error) {
      console.warn('[TaskCenter] Failed to load tasks', error)
    }
  }

  const fetchTaskCountsSafely = async () => {
    try {
      await fetchTaskCounts()
    } catch (error) {
      console.warn('[TaskCenter] Failed to load task counts', error)
    }
  }

  const fetchTasksAndCountsSafely = async () => {
    await Promise.allSettled([fetchTasksSafely(), fetchTaskCountsSafely()])
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
      try {
        const response = await listProjects()
        projectNames.value = Object.fromEntries(
          (response.data.items ?? []).map((item) => [item.id, item.name])
        )
      } catch (error) {
        projectNames.value = {}
        console.warn('[TaskCenter] Failed to load project names', error)
      }
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

  const handleTabChange = (_key: string) => {
    currentPage.value = 1
    void fetchTasksAndCountsSafely()
  }

  const handleSearch = () => {
    currentPage.value = 1
    void fetchTasksAndCountsSafely()
  }

  const handleToolChange = () => {
    currentPage.value = 1
    void fetchTasksAndCountsSafely()
  }

  const handleDateChange = () => {
    currentPage.value = 1
    void fetchTasksAndCountsSafely()
  }

  const handleRefresh = async () => {
    refreshing.value = true
    try {
      const [taskResult] = await Promise.allSettled([fetchTasks(), fetchTaskCounts()])
      if (taskResult.status === 'fulfilled') {
        message.success(t('common.refreshSuccess'))
      } else {
        message.error(t('common.error'))
      }
    } finally {
      refreshing.value = false
    }
  }

  // 只绑 `@change`（不绑 `@show-size-change`）：antd 改页大小时会连发两个事件，
  // 第二个事件的页码是旧页码，双绑会打两次请求并把「回第 1 页」覆盖掉。
  const handlePageChange = (page: number, size?: number) => {
    const change = resolvePaginationChange({
      nextPage: page,
      nextSize: size,
      currentSize: pageSize.value,
    })
    if (change.size !== null) {
      pageSize.value = change.size
    }
    currentPage.value = change.page
    void fetchTasksSafely()
  }

  const handleCancel = async (id: string) => {
    try {
      await tasksStore.cancelTask(id)
      message.success(t('tasks.cancelSuccess'))
      await fetchTasksAndCountsSafely()
    } catch {
      // 请求层已经展示具体错误，避免失败时误报成功。
    }
  }

  const handleRetry = async (id: string) => {
    try {
      await tasksStore.retryTask(id)
      message.success(t('tasks.retrySuccess'))
      await fetchTasksAndCountsSafely()
    } catch {
      // 请求层已经展示具体错误，避免失败时误报成功。
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await tasksStore.deleteTask(id)
      message.success(t('tasks.deleteSuccess'))
      await fetchTasksAndCountsSafely()
    } catch {
      // 请求层已经展示具体错误，避免失败时误报成功。
    }
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
        void fetchTasksAndCountsSafely()
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

  watch([routeTab, projectId, workflowRunId, workflowDefinitionId, workflowNodeId], ([tab]) => {
    currentTab.value = tab
    currentPage.value = 1
    void fetchTasksAndCountsSafely()
    void fetchProjectContextSafely()
  })

  function stringQueryParam(value: unknown): string | undefined {
    return typeof value === 'string' && value.trim() ? value : undefined
  }

  // 生命周期
  onMounted(async () => {
    await Promise.allSettled([
      fetchTasksAndCountsSafely(),
      fetchToolsSafely(),
      fetchProjectContextSafely()
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

  .task-scope-alert {
    margin-bottom: @spacing-md;
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

      &.attention :deep(.ant-badge-count) {
        background: @error-color;
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

  .pagination {
    display: flex;
    justify-content: center;
    margin-top: @spacing-xl;
  }

  // 响应式
  @media (max-width: @breakpoint-md) {
    .monitor-cards {
      grid-template-columns: 1fr !important;
    }
  }
</style>
