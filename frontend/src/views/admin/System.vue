<template>
  <div class="admin-system">
    <div class="page-header">
      <h2>{{ t('admin.system') }}</h2>
      <a-button @click="refreshSystemData">
        <ReloadOutlined /> {{ t('common.refresh') }}
      </a-button>
    </div>

    <a-row :gutter="[16, 16]">
      <a-col :xs="24" :xl="14">
        <a-card :title="t('admin.systemInfo')" :loading="loading">
          <a-descriptions v-if="systemInfo" :column="2" bordered size="small">
            <a-descriptions-item :label="t('admin.siteName')">{{ systemInfo.app_name }}</a-descriptions-item>
            <a-descriptions-item :label="t('admin.version')">{{ systemInfo.app_version }}</a-descriptions-item>
            <a-descriptions-item :label="t('admin.environment')">{{ systemInfo.environment }}</a-descriptions-item>
            <a-descriptions-item :label="t('admin.debugMode')">{{ systemInfo.debug ? 'ON' : 'OFF' }}</a-descriptions-item>
            <a-descriptions-item :label="t('admin.pythonVersion')">{{ systemInfo.python_version }}</a-descriptions-item>
            <a-descriptions-item :label="t('admin.os')">{{ systemInfo.platform }}</a-descriptions-item>
            <a-descriptions-item :label="t('admin.hostname')">{{ systemInfo.hostname }}</a-descriptions-item>
            <a-descriptions-item :label="t('admin.cpuCount')">{{ systemInfo.cpu_count }}</a-descriptions-item>
            <a-descriptions-item :label="t('admin.database')">{{ systemInfo.database_type }}</a-descriptions-item>
            <a-descriptions-item :label="t('admin.cacheBackend')">{{ systemInfo.cache_backend }}</a-descriptions-item>
            <a-descriptions-item :label="t('admin.storageBackend')">{{ systemInfo.storage_backend }}</a-descriptions-item>
            <a-descriptions-item :label="t('admin.taskQueue')">{{ systemInfo.task_queue }}</a-descriptions-item>
            <a-descriptions-item :label="t('admin.memoryTotal')">{{ systemInfo.memory_total_gb }} GB</a-descriptions-item>
            <a-descriptions-item :label="t('admin.memoryAvailable')">{{ systemInfo.memory_available_gb }} GB</a-descriptions-item>
            <a-descriptions-item :label="t('admin.diskTotal')">{{ systemInfo.disk_total_gb }} GB</a-descriptions-item>
            <a-descriptions-item :label="t('admin.diskFree')">{{ systemInfo.disk_free_gb }} GB</a-descriptions-item>
          </a-descriptions>
        </a-card>
      </a-col>

      <a-col :xs="24" :xl="10">
        <a-card :title="t('admin.runtimeStats')" :loading="loading">
          <a-row :gutter="[12, 12]">
            <a-col :span="12">
              <a-statistic :title="t('admin.totalTasks')" :value="systemStats?.total_tasks ?? 0" />
            </a-col>
            <a-col :span="12">
              <a-statistic :title="t('admin.totalFiles')" :value="systemStats?.total_files ?? 0" />
            </a-col>
            <a-col :span="12">
              <a-statistic :title="t('admin.runningTasks')" :value="systemStats?.running_tasks ?? 0" />
            </a-col>
            <a-col :span="12">
              <a-statistic :title="t('admin.pendingTasks')" :value="systemStats?.pending_tasks ?? 0" />
            </a-col>
            <a-col :span="12">
              <a-statistic :title="t('admin.failedTasks')" :value="systemStats?.failed_tasks ?? 0" />
            </a-col>
            <a-col :span="12">
              <a-statistic :title="t('admin.activeConnections')" :value="systemStats?.active_connections ?? 0" />
            </a-col>
          </a-row>
        </a-card>
      </a-col>
    </a-row>

    <a-card class="config-card" :title="t('admin.configSnapshot')" :loading="loading">
      <pre class="json-view">{{ formattedConfig }}</pre>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { ReloadOutlined } from '@ant-design/icons-vue'
import { getSystemConfig, getSystemInfo, getSystemStats } from '@/api/system'
import type { SystemConfig, SystemInfo, SystemStats } from '@/types/models'

const { t } = useI18n()

const loading = ref(false)
const systemInfo = ref<SystemInfo | null>(null)
const systemStats = ref<SystemStats | null>(null)
const systemConfig = ref<SystemConfig | null>(null)

const formattedConfig = computed(() => {
  return JSON.stringify(systemConfig.value ?? {}, null, 2)
})

const fetchSystemData = async () => {
  loading.value = true
  try {
    const [infoRes, statsRes, configRes] = await Promise.all([
      getSystemInfo(),
      getSystemStats(),
      getSystemConfig()
    ])
    systemInfo.value = infoRes.data
    systemStats.value = statsRes.data
    systemConfig.value = configRes.data
  } finally {
    loading.value = false
  }
}

const refreshSystemData = async () => {
  await fetchSystemData()
  message.success(t('common.refreshSuccess'))
}

onMounted(() => {
  void fetchSystemData()
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-system {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: @spacing-lg;

    h2 {
      margin: 0;
    }
  }

  .config-card {
    margin-top: @spacing-lg;
  }

  .json-view {
    background: @bg-color-light;
    padding: @spacing-md;
    border-radius: @border-radius-base;
    font-size: @font-size-sm;
    overflow: auto;
    max-height: 480px;
    margin: 0;
  }
}
</style>
