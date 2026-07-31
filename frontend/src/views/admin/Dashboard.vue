<template>
  <div class="admin-dashboard">
    <AppPageHeader :title="t('admin.dashboard')" :subtitle="t('admin.dashboardSubtitle')">
      <template #actions>
        <a-button type="primary" :loading="loading" @click="fetchDashboard">
          <template #icon><ReloadOutlined /></template>
          {{ t('common.refresh') }}
        </a-button>
      </template>
    </AppPageHeader>

    <a-row :gutter="[16, 16]" class="dashboard-summary">
      <a-col :xs="24" :sm="12" :lg="6">
        <a-card class="stat-card stat-card--users" :loading="loading">
          <a-statistic
            :title="t('admin.stats.totalUsers')"
            :value="userStats?.total_users ?? 0"
            :prefix="h(UserOutlined)"
          />
          <div class="stat-footer">
            <span class="trend up">
              <ArrowUpOutlined /> {{ userStats?.new_users_today ?? 0 }}
            </span>
            {{ t('admin.todayNew') }}
          </div>
          <div class="stat-card__accent" aria-hidden="true" />
        </a-card>
      </a-col>

      <a-col :xs="24" :sm="12" :lg="6">
        <a-card class="stat-card stat-card--tools" :loading="loading">
          <a-statistic
            :title="t('admin.stats.totalTools')"
            :value="systemStats?.total_tools ?? 0"
            :prefix="h(ToolOutlined)"
          />
          <div class="stat-card__accent" aria-hidden="true" />
        </a-card>
      </a-col>

      <a-col :xs="24" :sm="12" :lg="6">
        <a-card class="stat-card stat-card--tasks" :loading="loading">
          <a-statistic
            :title="t('admin.stats.totalTasks')"
            :value="systemStats?.total_tasks ?? 0"
            :prefix="h(CloudServerOutlined)"
          />
          <div class="stat-card__accent" aria-hidden="true" />
        </a-card>
      </a-col>

      <a-col :xs="24" :sm="12" :lg="6">
        <a-card class="stat-card stat-card--running" :loading="loading">
          <a-statistic
            :title="t('admin.runningTasks')"
            :value="systemStats?.running_tasks ?? 0"
            :prefix="h(PlayCircleOutlined)"
          />
          <div class="stat-card__accent" aria-hidden="true" />
        </a-card>
      </a-col>
    </a-row>

    <a-row :gutter="[16, 16]" class="section">
      <a-col :xs="24" :lg="12">
        <a-card class="dashboard-panel" :title="t('admin.recentTasks')">
          <a-table
            :columns="taskColumns"
            :data-source="recentTasks"
            :loading="loading"
            :pagination="false"
            row-key="id"
            size="small"
            :scroll="{ x: 560 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'task'">
                <div class="task-cell">
                  <span class="task-id">#{{ record.id.slice(0, 8) }}</span>
                  <span class="task-tool">{{ record.tool_name || '-' }}</span>
                </div>
              </template>
              <template v-else-if="column.key === 'status'">
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

      <a-col :xs="24" :lg="12">
        <a-card class="dashboard-panel" :title="t('admin.recentUsers')">
          <a-table
            :columns="userColumns"
            :data-source="recentUsers"
            :loading="loading"
            :pagination="false"
            row-key="id"
            size="small"
            :scroll="{ x: 560 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'avatar'">
                <ProtectedAvatar :size="32" :src="record.avatar_url">
                  {{ getUserInitial(record) }}
                </ProtectedAvatar>
              </template>
              <template v-else-if="column.key === 'user'">
                <div class="user-cell">
                  <span class="user-name">{{ getUserDisplayName(record) }}</span>
                  <span class="user-email">{{ record.email }}</span>
                </div>
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
import { computed, h, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ArrowUpOutlined,
  CloudServerOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  ToolOutlined,
  UserOutlined
} from '@ant-design/icons-vue'
import ProtectedAvatar from '@/components/common/ProtectedAvatar.vue'
import dayjs from 'dayjs'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import { adminGetUsers, adminGetUserStats } from '@/api/users'
import { getSystemStats } from '@/api/system'
import { getTaskList } from '@/api/tasks'
import type { AdminUserStats, SystemStats, Task, UserInfo } from '@/types/models'

const { t } = useI18n()

const loading = ref(false)
const userStats = ref<AdminUserStats | null>(null)
const systemStats = ref<SystemStats | null>(null)
const recentUsers = ref<UserInfo[]>([])
const recentTasks = ref<Task[]>([])

const taskColumns = computed(() => [
  { title: t('admin.taskInfo'), key: 'task' },
  { title: t('common.status'), key: 'status', width: 120 },
  { title: t('common.time'), key: 'created_at', width: 140 }
])

const userColumns = computed(() => [
  { title: '', key: 'avatar', width: 56 },
  { title: t('admin.userInfo'), key: 'user' },
  { title: t('admin.role'), key: 'role', width: 120 },
  { title: t('admin.registerTime'), key: 'created_at', width: 140 }
])

const getUserDisplayName = (user: UserInfo) => {
  return user.display_name || user.email.split('@')[0]
}

const getUserInitial = (user: UserInfo) => {
  const displayName = getUserDisplayName(user)
  return displayName ? displayName.charAt(0).toUpperCase() : 'U'
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
    user: 'blue'
  }
  return colors[role] || 'default'
}

const formatTime = (time: string) => dayjs(time).format('MM-DD HH:mm')

const fetchDashboard = async () => {
  loading.value = true
  try {
    const [userStatsRes, userListRes, taskListRes, systemStatsRes] = await Promise.all([
      adminGetUserStats(),
      adminGetUsers({ page: 1, page_size: 5 }),
      getTaskList({ page: 1, page_size: 5 }),
      getSystemStats()
    ])

    userStats.value = userStatsRes.data
    recentUsers.value = userListRes.data.items
    recentTasks.value = taskListRes.data.items
    systemStats.value = systemStatsRes.data
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void fetchDashboard()
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-dashboard {
  .dashboard-summary {
    margin-bottom: @spacing-lg;
  }

  .stat-card {
    position: relative;
    overflow: hidden;
    height: 100%;
    border: 1px solid @border-color;
    border-radius: @border-radius-lg;
    box-shadow: @shadow-sm;

    :deep(.ant-card-body) {
      position: relative;
      z-index: 1;
      min-height: 130px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }

    :deep(.ant-statistic-title) {
      margin-bottom: @spacing-sm;
      color: @text-color-light-secondary;
      font-weight: @font-weight-medium;
    }

    :deep(.ant-statistic-content) {
      color: @text-color-light-primary;
      font-weight: @font-weight-bold;
    }
  }

  .stat-card__accent {
    position: absolute;
    right: -34px;
    bottom: -46px;
    width: 118px;
    height: 118px;
    border-radius: @border-radius-round;
    opacity: 0.14;
  }

  .stat-card--users .stat-card__accent {
    background: @primary-color;
  }

  .stat-card--tools .stat-card__accent {
    background: @accent-color;
  }

  .stat-card--tasks .stat-card__accent {
    background: @success-color;
  }

  .stat-card--running .stat-card__accent {
    background: @warning-color;
  }

  .stat-footer {
    margin-top: @spacing-sm;
    color: @text-color-light-secondary;

    .trend {
      margin-right: @spacing-xs;
      font-weight: @font-weight-semibold;
    }

    .up {
      color: @success-color;
    }
  }

  .section {
    margin-top: 0;
  }

  .dashboard-panel {
    height: 100%;
    border: 1px solid @border-color;
    border-radius: @border-radius-lg;
    box-shadow: @shadow-sm;

    :deep(.ant-card-head) {
      min-height: 52px;
      border-bottom-color: @border-color;
    }

    :deep(.ant-card-head-title) {
      color: @text-color-light-primary;
      font-weight: @font-weight-semibold;
    }

    :deep(.ant-table-thead > tr > th) {
      color: @text-color-light-secondary;
      font-size: @font-size-xs;
      font-weight: @font-weight-semibold;
      background: @bg-color-light;
    }
  }

  .task-cell,
  .user-cell {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .task-id,
  .user-name {
    font-weight: @font-weight-medium;
  }

  .task-tool,
  .user-email {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  @media (max-width: @screen-md) {
    .stat-card :deep(.ant-card-body),
    .dashboard-panel :deep(.ant-card-body) {
      padding: @spacing-md;
    }

    .task-id,
    .task-tool,
    .user-name,
    .user-email {
      word-break: break-word;
    }
  }
}
</style>
