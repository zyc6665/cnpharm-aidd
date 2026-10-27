<template>
  <div class="admin-tasks">
    <AppPageHeader :title="t('admin.tasks')">
      <template #actions>
        <a-button @click="handleRefresh"> <ReloadOutlined /> {{ t('common.refresh') }} </a-button>
      </template>
    </AppPageHeader>

    <a-row :gutter="16" class="stats-row">
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card" :loading="loading">
          <a-statistic :title="t('admin.totalTasks')" :value="systemStats?.total_tasks ?? 0" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card" :loading="loading">
          <a-statistic :title="t('admin.runningTasks')" :value="systemStats?.running_tasks ?? 0" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card" :loading="loading">
          <a-statistic :title="t('admin.pendingTasks')" :value="systemStats?.pending_tasks ?? 0" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card" :loading="loading">
          <a-statistic :title="t('admin.failedTasks')" :value="systemStats?.failed_tasks ?? 0" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card" :loading="loading">
          <a-statistic :title="t('admin.resourceWaitTasks')" :value="resourceWaitStats?.total ?? 0" />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card" :loading="loading">
          <a-statistic
            :title="t('admin.quotaWaitTasks')"
            :value="resourceWaitStats?.by_category.quota ?? 0"
          />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card" :loading="loading">
          <a-statistic
            :title="t('admin.workerWaitTasks')"
            :value="resourceWaitStats?.by_category.worker_capacity ?? 0"
          />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card" :loading="loading">
          <a-statistic
            :title="t('admin.gpuWaitTasks')"
            :value="resourceWaitStats?.by_category.gpu ?? 0"
          />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card" :loading="loading">
          <a-statistic
            :title="t('admin.externalCapacityWaitTasks')"
            :value="resourceWaitStats?.by_category.external_capacity ?? 0"
          />
        </a-card>
      </a-col>
    </a-row>

    <AppFilterBar>
      <a-form layout="inline">
        <a-form-item :label="t('admin.keyword')">
          <a-input
            v-model:value="filters.keyword"
            :placeholder="t('admin.searchTaskPlaceholder')"
            style="width: 220px"
            @pressEnter="handleSearch"
          />
        </a-form-item>
        <a-form-item :label="t('admin.tool')">
          <a-select
            v-model:value="filters.tool_id"
            :placeholder="t('common.all')"
            style="width: 180px"
            allowClear
            show-search
            :filter-option="false"
            :loading="toolOptionsLoading"
            @search="searchToolOptions"
          >
            <a-select-option v-for="tool in toolOptions" :key="tool.id" :value="tool.id">
              {{ tool.name }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('common.status')">
          <a-select
            v-model:value="filters.status"
            :placeholder="t('common.all')"
            style="width: 140px"
            allowClear
          >
            <a-select-option value="pending">{{ t('tasks.status.pending') }}</a-select-option>
            <a-select-option value="running">{{ t('tasks.status.running') }}</a-select-option>
            <a-select-option value="success">{{ t('tasks.status.success') }}</a-select-option>
            <a-select-option value="failure">{{ t('tasks.status.failure') }}</a-select-option>
            <a-select-option value="canceled">{{ t('tasks.status.canceled') }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('admin.resourceWaitCategory')">
          <a-select
            v-model:value="filters.resource_wait_category"
            :placeholder="t('admin.resourceWaitAll')"
            style="width: 190px"
            allowClear
          >
            <a-select-option value="quota">{{ t('admin.resourceWaitQuota') }}</a-select-option>
            <a-select-option value="worker_capacity">
              {{ t('admin.resourceWaitWorkerCapacity') }}
            </a-select-option>
            <a-select-option value="gpu">{{ t('admin.resourceWaitGpu') }}</a-select-option>
            <a-select-option value="scheduler">{{ t('admin.resourceWaitScheduler') }}</a-select-option>
            <a-select-option value="external_capacity">
              {{ t('admin.resourceWaitExternalCapacity') }}
            </a-select-option>
            <a-select-option value="resource">{{ t('admin.resourceWaitResource') }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item>
          <a-space>
            <a-button type="primary" @click="handleSearch">
              <SearchOutlined /> {{ t('common.search') }}
            </a-button>
            <a-button @click="handleReset"> <ReloadOutlined /> {{ t('common.reset') }} </a-button>
          </a-space>
        </a-form-item>
      </a-form>
    </AppFilterBar>

    <a-card>
      <a-table
        :scroll="{ x: 'max-content' }"
        :columns="columns"
        :data-source="tasks"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'task'">
            <div class="task-cell">
              <span class="name">{{ formatTaskTitle(record) }}</span>
              <span class="id">ID: {{ record.id }}</span>
              <span v-if="record.resource_wait" class="resource-wait-status">
                {{ resourceWaitLabel(record.resource_wait) }}
              </span>
            </div>
          </template>
          <template v-else-if="column.key === 'user'">
            <div class="user-cell">
              <span>{{ record.user_name || '-' }}</span>
              <span v-if="record.user_email" class="user-email">{{ record.user_email }}</span>
            </div>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="getStatusColor(record.status)">
              {{ t(`tasks.status.${record.status}`) }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'progress'">
            <a-progress
              :percent="record.progress || 0"
              size="small"
              :status="getProgressStatus(record.status)"
            />
          </template>
          <template v-else-if="column.key === 'created_at'">
            {{ formatDate(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-tooltip :title="t('tasks.viewDetail')">
                <a-button type="link" size="small" @click="handleViewDetail(record)">
                  <EyeOutlined />
                </a-button>
              </a-tooltip>
              <a-tooltip v-if="record.status === 'running'" :title="t('tasks.cancel')">
                <a-button type="link" size="small" danger @click="handleCancel(record)">
                  <StopOutlined />
                </a-button>
              </a-tooltip>
              <a-tooltip v-if="record.status === 'failure'" :title="t('tasks.retry')">
                <a-button type="link" size="small" @click="handleRetry(record)">
                  <RedoOutlined />
                </a-button>
              </a-tooltip>
              <a-tooltip :title="t('common.delete')">
                <a-button type="link" size="small" danger @click="handleDelete(record)">
                  <DeleteOutlined />
                </a-button>
              </a-tooltip>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <a-drawer v-model:open="showDetailDrawer" :title="t('tasks.detail')" width="600">
      <SkeletonCard v-if="detailLoading" />
      <template v-else-if="selectedTask">
        <a-descriptions :column="1" bordered>
          <a-descriptions-item :label="t('common.name')">
            {{ formatTaskTitle(selectedTask) }}
          </a-descriptions-item>
          <a-descriptions-item label="ID">
            {{ selectedTask.id }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('admin.tool')">
            {{ selectedTask.tool_name || '-' }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('admin.user')">
            {{ selectedTask.user_name || selectedTask.user_email || selectedTask.user_id || '-' }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('common.status')">
            <a-tag :color="getStatusColor(selectedTask.status)">
              {{ t(`tasks.status.${selectedTask.status}`) }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item :label="t('tasks.progress')">
            <a-progress :percent="selectedTask.progress || 0" />
          </a-descriptions-item>
          <a-descriptions-item
            v-if="selectedTask.resource_wait"
            :label="t('admin.resourceWaitReason')"
          >
            <a-alert type="info" show-icon>
              <template #message>{{ resourceWaitLabel(selectedTask.resource_wait) }}</template>
              <template #description>
                <div>{{ selectedTask.resource_wait.reason }}</div>
                <div v-if="selectedTask.resource_wait.next_attempt_at">
                  {{ t('tasks.resourceWait.nextAttempt', { time: formatDate(selectedTask.resource_wait.next_attempt_at) }) }}
                </div>
              </template>
            </a-alert>
          </a-descriptions-item>
          <a-descriptions-item :label="t('tasks.createdAt')">
            {{ formatDate(selectedTask.created_at) }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('tasks.startedAt')">
            {{ selectedTask.started_at ? formatDate(selectedTask.started_at) : '-' }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('tasks.completedAt')">
            {{ selectedTask.completed_at ? formatDate(selectedTask.completed_at) : '-' }}
          </a-descriptions-item>
        </a-descriptions>

        <a-divider>{{ t('tasks.inputParams') }}</a-divider>
        <pre class="json-view">{{
          JSON.stringify(selectedTask.inputs?.params ?? {}, null, 2)
        }}</pre>

        <template v-if="selectedTask.output_data">
          <a-divider>{{ t('tasks.result') }}</a-divider>
          <pre class="json-view">{{ JSON.stringify(selectedTask.output_data, null, 2) }}</pre>
        </template>

        <template v-if="selectedTask.error_message">
          <a-divider>{{ t('tasks.errorMessage') }}</a-divider>
          <a-alert type="error" :message="selectedTask.error_message" />
        </template>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, reactive, ref } from 'vue'
  import { useI18n } from 'vue-i18n'
  import {
    DeleteOutlined,
    EyeOutlined,
    RedoOutlined,
    ReloadOutlined,
    SearchOutlined,
    StopOutlined
  } from '@ant-design/icons-vue'
  import { message, Modal } from 'ant-design-vue'
  import { formatDateTimeMinutes } from '@/utils/datetime'
  import AppFilterBar from '@/components/common/AppFilterBar.vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import SkeletonCard from '@/components/common/SkeletonCard.vue'
  import { useRemoteToolOptions } from '@/composables/useRemoteToolOptions'
  import {
    getTaskList,
    getTaskDetail,
    getResourceWaitStats,
    cancelTask,
    retryTask,
    deleteTask
  } from '@/api/tasks'
  import { getSystemStats } from '@/api/system'
  import type {
    SystemStats,
    Task,
    TaskResourceWaitStats,
    TaskResourceWaitStatus,
    TaskStatus
  } from '@/types/models'

  const { t } = useI18n()

  const loading = ref(false)
  const detailLoading = ref(false)
  const showDetailDrawer = ref(false)
  const selectedTask = ref<Task | null>(null)
  const tasks = ref<Task[]>([])
  const systemStats = ref<SystemStats | null>(null)
  const resourceWaitStats = ref<TaskResourceWaitStats | null>(null)
  const { fetchToolOptions, searchToolOptions, toolOptions, toolOptionsLoading } =
    useRemoteToolOptions()

  const filters = reactive({
    keyword: '',
    tool_id: undefined as string | undefined,
    status: undefined as TaskStatus | undefined,
    resource_wait_category: undefined as string | undefined
  })

  const pagination = reactive({
    current: 1,
    pageSize: 10,
    total: 0,
    showSizeChanger: true
  })

  const columns = computed(() => [
    { title: t('admin.taskInfo'), key: 'task', width: 220 },
    { title: t('admin.tool'), dataIndex: 'tool_name', key: 'tool_name', width: 160 },
    { title: t('admin.user'), key: 'user', width: 180 },
    { title: t('common.status'), key: 'status', width: 120 },
    { title: t('tasks.progress'), key: 'progress', width: 160 },
    { title: t('tasks.createdAt'), key: 'created_at', width: 180 },
    { title: t('common.actions'), key: 'actions', width: 160 }
  ])

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      pending: 'default',
      running: 'processing',
      success: 'success',
      failure: 'error',
      canceled: 'warning'
    }
    return colors[status] || 'default'
  }

  const getProgressStatus = (status: string) => {
    if (status === 'failure') return 'exception'
    if (status === 'success') return 'success'
    return 'active'
  }

  const formatDate = (date: string) => formatDateTimeMinutes(date)

  const formatTaskTitle = (task: Task) => {
    if (task.tool_name) {
      return `${task.tool_name} #${task.id.slice(0, 8)}`
    }
    return task.id
  }

  const resourceWaitLabel = (wait: TaskResourceWaitStatus) => {
    if (wait.category === 'quota') return t('admin.resourceWaitQuota')
    if (wait.category === 'worker_capacity') return t('admin.resourceWaitWorkerCapacity')
    if (wait.category === 'gpu') return t('admin.resourceWaitGpu')
    if (wait.category === 'scheduler') return t('admin.resourceWaitScheduler')
    if (wait.category === 'external_capacity') return t('admin.resourceWaitExternalCapacity')
    if (wait.category === 'resource') return t('admin.resourceWaitResource')
    return wait.reason
  }

  const fetchTaskStats = async () => {
    const [systemRes, resourceRes] = await Promise.all([
      getSystemStats(),
      getResourceWaitStats()
    ])
    systemStats.value = systemRes.data
    resourceWaitStats.value = resourceRes.data
  }

  const fetchTasks = async () => {
    loading.value = true
    try {
      const res = await getTaskList({
        page: pagination.current,
        page_size: pagination.pageSize,
        keyword: filters.keyword || undefined,
        tool_id: filters.tool_id,
        status: filters.status,
        resource_wait_category: filters.resource_wait_category
      })
      tasks.value = res.data.items
      pagination.total = res.data.total
    } finally {
      loading.value = false
    }
  }

  const handleRefresh = async () => {
    await Promise.all([fetchTaskStats(), fetchTasks()])
    message.success(t('common.refreshSuccess'))
  }

  const handleSearch = async () => {
    pagination.current = 1
    await fetchTasks()
  }

  const handleReset = async () => {
    filters.keyword = ''
    filters.tool_id = undefined
    filters.status = undefined
    filters.resource_wait_category = undefined
    pagination.current = 1
    await fetchTasks()
  }

  const handleTableChange = async (pag: { current?: number; pageSize?: number }) => {
    pagination.current = pag.current || 1
    pagination.pageSize = pag.pageSize || 10
    await fetchTasks()
  }

  const handleViewDetail = async (record: Task) => {
    showDetailDrawer.value = true
    selectedTask.value = { ...record }
    detailLoading.value = true
    try {
      const res = await getTaskDetail(record.id)
      selectedTask.value = {
        ...record,
        ...res.data,
        user_name: record.user_name,
        user_email: record.user_email
      }
    } finally {
      detailLoading.value = false
    }
  }

  const handleCancel = (record: Task) => {
    Modal.confirm({
      title: t('tasks.cancelConfirm'),
      content: t('tasks.cancelConfirmContent'),
      onOk: async () => {
        await cancelTask(record.id)
        message.success(t('tasks.cancelSuccess'))
        await Promise.all([fetchTasks(), fetchTaskStats()])
        if (selectedTask.value?.id === record.id) {
          await handleViewDetail(record)
        }
      }
    })
  }

  const handleRetry = async (record: Task) => {
    await retryTask(record.id)
    message.success(t('tasks.retrySuccess'))
    await Promise.all([fetchTasks(), fetchTaskStats()])
    if (selectedTask.value?.id === record.id) {
      await handleViewDetail(record)
    }
  }

  const handleDelete = (record: Task) => {
    Modal.confirm({
      title: t('tasks.deleteConfirm'),
      content: t('tasks.deleteConfirmContent'),
      okType: 'danger',
      onOk: async () => {
        await deleteTask(record.id)
        message.success(t('tasks.deleteSuccess'))
        await Promise.all([fetchTasks(), fetchTaskStats()])
        if (selectedTask.value?.id === record.id) {
          showDetailDrawer.value = false
          selectedTask.value = null
        }
      }
    })
  }

  onMounted(async () => {
    await Promise.all([fetchTaskStats(), fetchToolOptions(), fetchTasks()])
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .admin-tasks {
    .stats-row {
      margin-bottom: @spacing-lg;
    }

    .stat-card {
      text-align: center;
    }

    .task-cell,
    .user-cell {
      display: flex;
      flex-direction: column;
    }

    .name {
      font-weight: @font-weight-medium;
    }

    .id,
    .user-email {
      font-size: @font-size-sm;
      color: @text-color-light-secondary;
    }

    .recovery-status {
      color: @warning-color;
      font-size: @font-size-sm;
      font-weight: @font-weight-medium;
    }

    .resource-wait-status {
      color: @warning-color;
      font-size: @font-size-sm;
    }

    .json-view {
      background: @bg-color-light;
      padding: @spacing-md;
      border-radius: @border-radius-base;
      font-size: @font-size-sm;
      overflow: auto;
      max-height: 240px;
    }
  }
</style>
