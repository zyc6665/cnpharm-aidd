<template>
  <div class="admin-dashboard">
    <a-row :gutter="[16, 16]">
      <!-- 统计卡片 -->
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card class="stat-card">
          <a-statistic
            :title="t('admin.stats.totalUsers')"
            :value="stats.totalUsers"
            :prefix="h(UserOutlined)"
          />
          <div class="stat-footer">
            <span class="trend up">
              <ArrowUpOutlined /> {{ stats.newUsersToday }}
            </span>
            {{ t('admin.todayNew') }}
          </div>
        </a-card>
      </a-col>

      <a-col :xs="24" :sm="12" :lg="6">
        <a-card class="stat-card">
          <a-statistic
            :title="t('admin.stats.totalTools')"
            :value="stats.totalTools"
            :prefix="h(ToolOutlined)"
          />
          <div class="stat-footer">
            <span>{{ stats.activeTools }}</span>
            {{ t('admin.activeCount') }}
          </div>
        </a-card>
      </a-col>

      <a-col :xs="24" :sm="12" :lg="6">
        <a-card class="stat-card">
          <a-statistic
            :title="t('admin.stats.totalTasks')"
            :value="stats.totalTasks"
            :prefix="h(CloudServerOutlined)"
          />
          <div class="stat-footer">
            <span class="trend">{{ stats.runningTasks }}</span>
            {{ t('admin.runningNow') }}
          </div>
        </a-card>
      </a-col>

    </a-row>

    <a-row :gutter="[16, 16]" class="section">
      <!-- 任务趋势图 -->
      <a-col :xs="24" :lg="16">
        <a-card :title="t('admin.taskTrend')">
          <div ref="chartRef" class="chart-container"></div>
        </a-card>
      </a-col>

      <!-- 系统状态 -->
      <a-col :xs="24" :lg="8">
        <a-card :title="t('admin.systemStatus')">
          <div class="status-list">
            <div class="status-item">
              <span class="label">{{ t('admin.cpuUsage') }}</span>
              <a-progress
                :percent="systemStatus.cpu"
                :stroke-color="getProgressColor(systemStatus.cpu)"
                size="small"
              />
            </div>
            <div class="status-item">
              <span class="label">{{ t('admin.memoryUsage') }}</span>
              <a-progress
                :percent="systemStatus.memory"
                :stroke-color="getProgressColor(systemStatus.memory)"
                size="small"
              />
            </div>
            <div class="status-item">
              <span class="label">{{ t('admin.diskUsage') }}</span>
              <a-progress
                :percent="systemStatus.disk"
                :stroke-color="getProgressColor(systemStatus.disk)"
                size="small"
              />
            </div>
          </div>

          <a-divider />

          <div class="service-status">
            <h4>{{ t('admin.serviceStatus') }}</h4>
            <a-space direction="vertical" :size="8" style="width: 100%">
              <div class="service-item">
                <span>API Server</span>
                <a-tag color="success">{{ t('admin.running') }}</a-tag>
              </div>
              <div class="service-item">
                <span>Task Worker</span>
                <a-tag color="success">{{ t('admin.running') }}</a-tag>
              </div>
              <div class="service-item">
                <span>Redis</span>
                <a-tag color="success">{{ t('admin.running') }}</a-tag>
              </div>
              <div class="service-item">
                <span>Database</span>
                <a-tag color="success">{{ t('admin.running') }}</a-tag>
              </div>
            </a-space>
          </div>
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="[16, 16]" class="section">
      <!-- 最近任务 -->
      <a-col :xs="24" :lg="12">
        <a-card :title="t('admin.recentTasks')">
          <a-table
            :columns="taskColumns"
            :data-source="recentTasks"
            :pagination="false"
            size="small"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'status'">
                <a-tag :color="getStatusColor(record.status)">
                  {{ t(`tasks.status.${record.status}`) }}
                </a-tag>
              </template>
              <template v-else-if="column.key === 'created_at'">
                {{ formatTime(record.created_at) }}
              </template>
            </template>
          </a-table>
        </a-card>
      </a-col>

      <!-- 最近用户 -->
      <a-col :xs="24" :lg="12">
        <a-card :title="t('admin.recentUsers')">
          <a-table
            :columns="userColumns"
            :data-source="recentUsers"
            :pagination="false"
            size="small"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'avatar'">
                <a-avatar :size="32" :src="record.avatar">
                  {{ record.username?.charAt(0).toUpperCase() }}
                </a-avatar>
              </template>
              <template v-else-if="column.key === 'role'">
                <a-tag :color="getRoleColor(record.role)">
                  {{ t(`user.role.${record.role}`) }}
                </a-tag>
              </template>
              <template v-else-if="column.key === 'created_at'">
                {{ formatTime(record.created_at) }}
              </template>
            </template>
          </a-table>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, h } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  UserOutlined,
  ToolOutlined,
  CloudServerOutlined,
  ArrowUpOutlined
} from '@ant-design/icons-vue'
import dayjs from 'dayjs'
import * as echarts from 'echarts'

const { t } = useI18n()

const chartRef = ref<HTMLElement>()
let chartInstance: echarts.ECharts | null = null

// 统计数据
const stats = reactive({
  totalUsers: 1256,
  newUsersToday: 23,
  totalTools: 15,
  activeTools: 12,
  totalTasks: 8934,
  runningTasks: 7
})

// 系统状态
const systemStatus = reactive({
  cpu: 45,
  memory: 62,
  disk: 38
})

// 最近任务
const recentTasks = ref([
  { id: 1, name: 'LVPocket预测任务', tool_name: 'LVPocket', status: 'running', created_at: '2024-01-15T10:30:00' },
  { id: 2, name: '蛋白质结构预测', tool_name: 'AlphaFold', status: 'success', created_at: '2024-01-15T09:20:00' },
  { id: 3, name: '分子对接模拟', tool_name: 'AutoDock', status: 'success', created_at: '2024-01-15T08:15:00' },
  { id: 4, name: '序列比对分析', tool_name: 'BLAST', status: 'failure', created_at: '2024-01-14T16:45:00' },
  { id: 5, name: '结构可视化', tool_name: 'PyMOL', status: 'pending', created_at: '2024-01-14T14:30:00' }
])

// 最近用户
const recentUsers = ref([
  { id: 1, username: 'researcher1', email: 'researcher1@example.com', role: 'vip', created_at: '2024-01-15T11:00:00' },
  { id: 2, username: 'scientist2', email: 'scientist2@example.com', role: 'user', created_at: '2024-01-15T10:30:00' },
  { id: 3, username: 'biologist3', email: 'biologist3@example.com', role: 'user', created_at: '2024-01-15T09:45:00' },
  { id: 4, username: 'chemist4', email: 'chemist4@example.com', role: 'vip', created_at: '2024-01-14T16:20:00' },
  { id: 5, username: 'analyst5', email: 'analyst5@example.com', role: 'user', created_at: '2024-01-14T14:10:00' }
])

const taskColumns = [
  { title: t('common.name'), dataIndex: 'name', key: 'name', ellipsis: true },
  { title: t('admin.toolName'), dataIndex: 'tool_name', key: 'tool_name' },
  { title: t('common.status'), key: 'status' },
  { title: t('common.time'), key: 'created_at' }
]

const userColumns = [
  { title: '', key: 'avatar', width: 50 },
  { title: t('auth.username'), dataIndex: 'username', key: 'username' },
  { title: t('admin.role'), key: 'role' },
  { title: t('admin.registerTime'), key: 'created_at' }
]

const getProgressColor = (percent: number) => {
  if (percent >= 80) return '#ff4d4f'
  if (percent >= 60) return '#faad14'
  return '#52c41a'
}

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

const getRoleColor = (role: string) => {
  const colors: Record<string, string> = {
    admin: 'red',
    vip: 'gold',
    user: 'blue',
    guest: 'default'
  }
  return colors[role] || 'default'
}

const formatTime = (time: string) => {
  return dayjs(time).format('MM-DD HH:mm')
}

const initChart = () => {
  if (!chartRef.value) return

  chartInstance = echarts.init(chartRef.value)

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    legend: {
      data: [t('admin.taskCount'), t('admin.successRate')],
      bottom: 0
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      top: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    },
    yAxis: [
      {
        type: 'value',
        name: t('admin.taskCount'),
        position: 'left'
      },
      {
        type: 'value',
        name: t('admin.successRate'),
        position: 'right',
        max: 100,
        axisLabel: {
          formatter: '{value}%'
        }
      }
    ],
    series: [
      {
        name: t('admin.taskCount'),
        type: 'bar',
        data: [120, 200, 150, 80, 70, 110, 130],
        itemStyle: {
          color: '#1890ff'
        }
      },
      {
        name: t('admin.successRate'),
        type: 'line',
        yAxisIndex: 1,
        data: [92, 88, 95, 90, 85, 93, 91],
        itemStyle: {
          color: '#52c41a'
        }
      }
    ]
  }

  chartInstance.setOption(option)
}

const handleResize = () => {
  chartInstance?.resize()
}

onMounted(() => {
  initChart()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-dashboard {
  .stat-card {
    .stat-footer {
      margin-top: @spacing-md;
      font-size: @font-size-sm;
      color: @text-color-light-secondary;

      .trend {
        margin-right: @spacing-xs;

        &.up {
          color: @success-color;
        }

        &.down {
          color: @error-color;
        }
      }
    }
  }

  .section {
    margin-top: @spacing-lg;
  }

  .chart-container {
    height: 300px;
  }

  .status-list {
    .status-item {
      margin-bottom: @spacing-md;

      .label {
        display: block;
        margin-bottom: @spacing-xs;
        color: @text-color-light-secondary;
        font-size: @font-size-sm;
      }
    }
  }

  .service-status {
    h4 {
      margin: 0 0 @spacing-md 0;
      font-weight: @font-weight-medium;
    }

    .service-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
  }
}
</style>
