<template>
  <div class="admin-tasks">
    <div class="page-header">
      <h2>{{ t('admin.tasks') }}</h2>
      <a-space>
        <a-button @click="handleRefresh">
          <ReloadOutlined /> {{ t('common.refresh') }}
        </a-button>
        <a-button danger @click="handleClearCompleted">
          <DeleteOutlined /> {{ t('admin.clearCompleted') }}
        </a-button>
      </a-space>
    </div>

    <!-- 统计卡片 -->
    <a-row :gutter="16" class="stats-row">
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic
            :title="t('admin.totalTasks')"
            :value="stats.total"
            :value-style="{ color: '#1890ff' }"
          />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic
            :title="t('admin.runningTasks')"
            :value="stats.running"
            :value-style="{ color: '#52c41a' }"
          />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic
            :title="t('admin.pendingTasks')"
            :value="stats.pending"
            :value-style="{ color: '#faad14' }"
          />
        </a-card>
      </a-col>
      <a-col :xs="12" :sm="6">
        <a-card class="stat-card">
          <a-statistic
            :title="t('admin.failedTasks')"
            :value="stats.failed"
            :value-style="{ color: '#ff4d4f' }"
          />
        </a-card>
      </a-col>
    </a-row>

    <!-- 搜索筛选 -->
    <a-card class="filter-card">
      <a-form layout="inline">
        <a-form-item :label="t('admin.keyword')">
          <a-input
            v-model:value="filters.keyword"
            :placeholder="t('admin.searchTaskPlaceholder')"
            style="width: 200px"
            @pressEnter="handleSearch"
          />
        </a-form-item>
        <a-form-item :label="t('admin.tool')">
          <a-select
            v-model:value="filters.tool_id"
            :placeholder="t('common.all')"
            style="width: 150px"
            allowClear
          >
            <a-select-option :value="1">LVPocket</a-select-option>
            <a-select-option :value="2">AlphaFold</a-select-option>
            <a-select-option :value="3">AutoDock</a-select-option>
            <a-select-option :value="4">BLAST</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('common.status')">
          <a-select
            v-model:value="filters.status"
            :placeholder="t('common.all')"
            style="width: 120px"
            allowClear
          >
            <a-select-option value="pending">{{ t('tasks.status.pending') }}</a-select-option>
            <a-select-option value="running">{{ t('tasks.status.running') }}</a-select-option>
            <a-select-option value="success">{{ t('tasks.status.success') }}</a-select-option>
            <a-select-option value="failure">{{ t('tasks.status.failure') }}</a-select-option>
            <a-select-option value="canceled">{{ t('tasks.status.canceled') }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('admin.dateRange')">
          <a-range-picker
            v-model:value="filters.dateRange"
            style="width: 240px"
          />
        </a-form-item>
        <a-form-item>
          <a-space>
            <a-button type="primary" @click="handleSearch">
              <SearchOutlined /> {{ t('common.search') }}
            </a-button>
            <a-button @click="handleReset">
              <ReloadOutlined /> {{ t('common.reset') }}
            </a-button>
          </a-space>
        </a-form-item>
      </a-form>
    </a-card>

    <!-- 任务列表 -->
    <a-card>
      <a-table
        :columns="columns"
        :data-source="filteredTasks"
        :loading="loading"
        :pagination="pagination"
        :row-selection="rowSelection"
        row-key="id"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'task'">
            <div class="task-cell">
              <span class="name">{{ record.name }}</span>
              <span class="id">ID: {{ record.id }}</span>
            </div>
          </template>
          <template v-else-if="column.key === 'user'">
            <div class="user-cell">
              <a-avatar :size="24" :src="record.user?.avatar">
                {{ record.user?.username?.charAt(0).toUpperCase() }}
              </a-avatar>
              <span>{{ record.user?.username }}</span>
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

      <!-- 批量操作 -->
      <div v-if="selectedRowKeys.length > 0" class="batch-actions">
        <span>{{ t('admin.selected', { count: selectedRowKeys.length }) }}</span>
        <a-space>
          <a-button size="small" @click="handleBatchCancel">
            {{ t('admin.batchCancel') }}
          </a-button>
          <a-button size="small" danger @click="handleBatchDelete">
            {{ t('admin.batchDelete') }}
          </a-button>
        </a-space>
      </div>
    </a-card>

    <!-- 任务详情抽屉 -->
    <a-drawer
      v-model:open="showDetailDrawer"
      :title="t('tasks.detail')"
      width="600"
    >
      <template v-if="selectedTask">
        <a-descriptions :column="1" bordered>
          <a-descriptions-item :label="t('common.name')">
            {{ selectedTask.name }}
          </a-descriptions-item>
          <a-descriptions-item label="ID">
            {{ selectedTask.id }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('admin.tool')">
            {{ selectedTask.tool_name }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('admin.user')">
            {{ selectedTask.user?.username }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('common.status')">
            <a-tag :color="getStatusColor(selectedTask.status)">
              {{ t(`tasks.status.${selectedTask.status}`) }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item :label="t('tasks.progress')">
            <a-progress :percent="selectedTask.progress || 0" />
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
        <pre class="json-view">{{ JSON.stringify(selectedTask.params, null, 2) }}</pre>

        <template v-if="selectedTask.error_message">
          <a-divider>{{ t('tasks.errorMessage') }}</a-divider>
          <a-alert type="error" :message="selectedTask.error_message" />
        </template>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ReloadOutlined,
  DeleteOutlined,
  SearchOutlined,
  EyeOutlined,
  StopOutlined,
  RedoOutlined
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import type { Dayjs } from 'dayjs'
import dayjs from 'dayjs'

const { t } = useI18n()

const loading = ref(false)
const showDetailDrawer = ref(false)
const selectedTask = ref<any>(null)
const selectedRowKeys = ref<number[]>([])

const stats = reactive({
  total: 8934,
  running: 7,
  pending: 12,
  failed: 23
})

const filters = reactive({
  keyword: '',
  tool_id: undefined as number | undefined,
  status: undefined as string | undefined,
  dateRange: null as [Dayjs, Dayjs] | null
})

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 200
})

const rowSelection = computed(() => ({
  selectedRowKeys: selectedRowKeys.value,
  onChange: (keys: number[]) => {
    selectedRowKeys.value = keys
  }
}))

// 模拟任务数据
const tasks = ref([
  { id: 1001, name: 'LVPocket预测任务', tool_name: 'LVPocket', tool_id: 1, status: 'running', progress: 65, user: { username: 'researcher1' }, created_at: '2024-01-15T10:30:00', started_at: '2024-01-15T10:31:00', params: { pdb_file: 'protein.pdb', model: 'lv_net_v2' } },
  { id: 1002, name: '蛋白质结构预测', tool_name: 'AlphaFold', tool_id: 2, status: 'success', progress: 100, user: { username: 'scientist2' }, created_at: '2024-01-15T09:20:00', started_at: '2024-01-15T09:21:00', completed_at: '2024-01-15T10:15:00', params: { sequence: 'MKFLILLFNILCLFPVLAADNHGVGP...' } },
  { id: 1003, name: '分子对接模拟', tool_name: 'AutoDock', tool_id: 3, status: 'pending', progress: 0, user: { username: 'chemist3' }, created_at: '2024-01-15T11:00:00', params: { receptor: 'receptor.pdbqt', ligand: 'ligand.mol2' } },
  { id: 1004, name: '序列比对分析', tool_name: 'BLAST', tool_id: 4, status: 'failure', progress: 30, user: { username: 'biologist4' }, created_at: '2024-01-14T16:45:00', started_at: '2024-01-14T16:46:00', error_message: 'Database connection timeout', params: { query: 'sequence.fasta', database: 'nr' } },
  { id: 1005, name: '批量结构预测', tool_name: 'LVPocket', tool_id: 1, status: 'canceled', progress: 45, user: { username: 'analyst5' }, created_at: '2024-01-14T14:30:00', started_at: '2024-01-14T14:31:00', params: { pdb_file: 'batch_proteins.zip' } }
])

// 过滤后的任务列表
const filteredTasks = computed(() => {
  let result = tasks.value

  // 关键词搜索
  if (filters.keyword) {
    const keyword = filters.keyword.toLowerCase()
    result = result.filter(task =>
      task.name.toLowerCase().includes(keyword) ||
      task.tool_name.toLowerCase().includes(keyword) ||
      task.user.username.toLowerCase().includes(keyword)
    )
  }

  // 工具筛选
  if (filters.tool_id) {
    result = result.filter(task => task.tool_id === filters.tool_id)
  }

  // 状态筛选
  if (filters.status) {
    result = result.filter(task => task.status === filters.status)
  }

  // 日期范围筛选
  if (filters.dateRange && filters.dateRange.length === 2) {
    const [start, end] = filters.dateRange
    result = result.filter(task => {
      const taskDate = dayjs(task.created_at)
      return taskDate.isAfter(start.startOf('day')) && taskDate.isBefore(end.endOf('day'))
    })
  }

  return result
})

const columns = computed(() => [
  { title: t('admin.taskInfo'), key: 'task', width: 200 },
  { title: t('admin.tool'), dataIndex: 'tool_name', key: 'tool_name', width: 100 },
  { title: t('admin.user'), key: 'user', width: 120 },
  { title: t('common.status'), key: 'status', width: 100 },
  { title: t('tasks.progress'), key: 'progress', width: 150 },
  { title: t('tasks.createdAt'), key: 'created_at', width: 150 },
  { title: t('common.actions'), key: 'actions', width: 150, fixed: 'right' }
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

const formatDate = (date: string) => {
  return dayjs(date).format('YYYY-MM-DD HH:mm')
}

const handleRefresh = () => {
  loading.value = true
  setTimeout(() => {
    loading.value = false
    message.success(t('common.refreshSuccess'))
  }, 500)
}

const handleClearCompleted = () => {
  Modal.confirm({
    title: t('admin.clearCompletedConfirm'),
    content: t('admin.clearCompletedConfirmContent'),
    onOk: () => {
      tasks.value = tasks.value.filter(t => !['success', 'failure', 'canceled'].includes(t.status))
      message.success(t('common.success'))
    }
  })
}

const handleSearch = () => {
  pagination.current = 1
  pagination.total = filteredTasks.value.length
  message.success(t('common.searchSuccess'))
}

const handleReset = () => {
  filters.keyword = ''
  filters.tool_id = undefined
  filters.status = undefined
  filters.dateRange = null
  handleSearch()
}

const handleTableChange = (pag: any) => {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
}

const handleViewDetail = (record: any) => {
  selectedTask.value = record
  showDetailDrawer.value = true
}

const handleCancel = (record: any) => {
  Modal.confirm({
    title: t('tasks.cancelConfirm'),
    content: t('tasks.cancelConfirmContent'),
    onOk: () => {
      record.status = 'canceled'
      message.success(t('tasks.cancelSuccess'))
    }
  })
}

const handleRetry = (record: any) => {
  record.status = 'pending'
  record.progress = 0
  record.error_message = undefined
  message.success(t('tasks.retrySuccess'))
}

const handleDelete = (record: any) => {
  Modal.confirm({
    title: t('tasks.deleteConfirm'),
    content: t('tasks.deleteConfirmContent'),
    okType: 'danger',
    onOk: () => {
      tasks.value = tasks.value.filter(t => t.id !== record.id)
      message.success(t('tasks.deleteSuccess'))
    }
  })
}

const handleBatchCancel = () => {
  Modal.confirm({
    title: t('admin.batchCancelConfirm'),
    onOk: () => {
      tasks.value.forEach(task => {
        if (selectedRowKeys.value.includes(task.id) && task.status === 'running') {
          task.status = 'canceled'
        }
      })
      selectedRowKeys.value = []
      message.success(t('common.success'))
    }
  })
}

const handleBatchDelete = () => {
  Modal.confirm({
    title: t('admin.batchDeleteConfirm'),
    okType: 'danger',
    onOk: () => {
      tasks.value = tasks.value.filter(t => !selectedRowKeys.value.includes(t.id))
      selectedRowKeys.value = []
      message.success(t('common.success'))
    }
  })
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-tasks {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: @spacing-lg;

    h2 {
      margin: 0;
    }
  }

  .stats-row {
    margin-bottom: @spacing-lg;

    .stat-card {
      text-align: center;
    }
  }

  .filter-card {
    margin-bottom: @spacing-lg;
  }

  .task-cell {
    display: flex;
    flex-direction: column;

    .name {
      font-weight: @font-weight-medium;
    }

    .id {
      font-size: @font-size-sm;
      color: @text-color-light-secondary;
    }
  }

  .user-cell {
    display: flex;
    align-items: center;
    gap: @spacing-xs;
  }

  .batch-actions {
    margin-top: @spacing-md;
    padding: @spacing-sm @spacing-md;
    background: @bg-color-light;
    border-radius: @border-radius-base;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .json-view {
    background: @bg-color-light;
    padding: @spacing-md;
    border-radius: @border-radius-base;
    font-size: @font-size-sm;
    overflow: auto;
    max-height: 200px;
  }
}
</style>
