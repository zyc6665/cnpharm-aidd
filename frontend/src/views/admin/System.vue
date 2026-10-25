<template>
  <div class="admin-system">
    <AppPageHeader :title="t('admin.system')" :subtitle="t('admin.systemSubtitle')">
      <template #actions>
        <a-button @click="refreshSystemData">
          <ReloadOutlined /> {{ t('common.refresh') }}
        </a-button>
      </template>
    </AppPageHeader>

    <a-tabs v-model:activeKey="activeTab" class="system-tabs">
      <a-tab-pane key="overview" :tab="t('admin.systemOverview')">
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

        <a-card class="health-card" title="运行健康" :loading="loading">
          <div v-if="systemHealth" class="health-panel">
            <div class="health-overall">
              <a-tag :color="healthStatusColor(systemHealth.status)">
                {{ healthStatusText(systemHealth.status) }}
              </a-tag>
              <span>{{ systemHealth.environment }} · v{{ systemHealth.version }}</span>
              <time :datetime="systemHealth.timestamp">
                {{ formatDateTime(systemHealth.timestamp) }}
              </time>
            </div>

            <div class="health-services">
              <article
                v-for="service in healthServices"
                :key="service.name"
                class="health-service"
              >
                <div class="health-service-head">
                  <strong>{{ healthServiceLabel(service.name) }}</strong>
                  <a-tag :color="healthStatusColor(service.status)">
                    {{ healthStatusText(service.status) }}
                  </a-tag>
                </div>
                <p>{{ service.message || '-' }}</p>
                <small v-if="service.latency_ms != null">{{ service.latency_ms }} ms</small>
              </article>
            </div>
          </div>
          <a-empty v-else description="暂无健康检查数据" />
        </a-card>
      </a-tab-pane>

      <a-tab-pane key="resources" :tab="t('admin.resourceWorkers')">
        <a-card :loading="resourceLoading">
          <div class="resource-status-toolbar">
            <div>
              <h3>{{ t('admin.resourceWorkers') }}</h3>
              <p>{{ t('admin.resourceWorkersSubtitle') }}</p>
            </div>
            <a-space>
              <a-tag :color="resourceStatusColor(resourceStatus?.status)">
                {{ resourceStatusText(resourceStatus?.status) }}
              </a-tag>
              <span class="muted-text">
                {{ t('admin.totalResourceWorkers') }}: {{ resourceStatus?.total_workers ?? 0 }}
              </span>
            </a-space>
          </div>

          <a-table
            :columns="resourceWorkerColumns"
            :data-source="resourceStatus?.workers ?? []"
            :loading="resourceLoading"
            :pagination="{ pageSize: 8, showSizeChanger: false }"
            :scroll="{ x: 980 }"
            row-key="worker_id"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'worker_id'">
                <a-space direction="vertical" size="small">
                  <strong>{{ record.worker_id }}</strong>
                  <a-tag :color="record.healthy ? 'green' : 'red'">
                    {{ record.healthy ? t('admin.workerHealthy') : t('admin.workerUnhealthy') }}
                  </a-tag>
                </a-space>
              </template>

              <template v-else-if="column.key === 'queue'">
                <a-typography-text code>{{ record.queue || '-' }}</a-typography-text>
              </template>

              <template v-else-if="column.key === 'executors'">
                <a-space wrap>
                  <a-tag v-for="item in record.executor_types" :key="item">{{ item }}</a-tag>
                </a-space>
              </template>

              <template v-else-if="column.key === 'tiers'">
                <a-space wrap>
                  <a-tag v-for="item in record.tiers" :key="item" color="blue">{{ item }}</a-tag>
                </a-space>
              </template>

              <template v-else-if="column.key === 'cpu'">
                <span>{{ formatCapacity(record.cpu_used, record.cpu_capacity, ' cores') }}</span>
              </template>

              <template v-else-if="column.key === 'memory'">
                <span>{{ formatCapacity(record.memory_used_gb, record.memory_capacity_gb, ' GB') }}</span>
              </template>

              <template v-else-if="column.key === 'parallelism'">
                <span>{{ formatCapacity(record.parallelism_used, record.parallelism, '') }}</span>
              </template>

              <template v-else-if="column.key === 'reservations'">
                <a-tag :color="record.reservation_count ? 'orange' : 'default'">
                  {{ record.reservation_count }}
                </a-tag>
              </template>

              <template v-else-if="column.key === 'executions'">
                <a-tag :color="record.execution_count ? 'blue' : 'default'">
                  {{ record.execution_count }}
                </a-tag>
              </template>

              <template v-else-if="column.key === 'gpu'">
                <span v-if="record.gpu_count != null">
                  {{ record.gpu_count }} · {{ record.gpu_memory_mb ?? '-' }} MB
                </span>
                <span v-else>-</span>
              </template>
            </template>
          </a-table>
          <a-empty v-if="!resourceLoading && !(resourceStatus?.workers?.length)" :description="t('admin.noResourceWorkers')" />
        </a-card>

        <a-card class="quota-card" :loading="quotaLoading">
          <div class="resource-status-toolbar">
            <div>
              <h3>{{ t('admin.resourceQuotas') }}</h3>
              <p>{{ t('admin.resourceQuotasSubtitle') }}</p>
            </div>
            <a-space>
              <a-tag :color="resourceQuotaStatus?.enabled ? 'green' : 'default'">
                {{ resourceQuotaStatus?.enabled ? t('admin.quotaEnabled') : t('admin.quotaDisabled') }}
              </a-tag>
              <span class="muted-text">
                {{ t('admin.gpuQuotaMode') }}: {{ resourceQuotaStatus?.gpu_scope_quota || '-' }}
              </span>
            </a-space>
          </div>

          <a-table
            :columns="resourceQuotaColumns"
            :data-source="resourceQuotaStatus?.scopes ?? []"
            :loading="quotaLoading"
            :pagination="{ pageSize: 8, showSizeChanger: false }"
            :scroll="{ x: 1080 }"
            :row-key="quotaRowKey"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'scope'">
                <a-space direction="vertical" size="small">
                  <a-tag :color="record.scope_type === 'user' ? 'blue' : 'purple'">
                    {{ record.scope_type === 'user' ? t('admin.userScope') : t('admin.projectScope') }}
                  </a-tag>
                  <a-typography-text code>{{ record.scope_id }}</a-typography-text>
                </a-space>
              </template>
              <template v-else-if="column.key === 'cpu'">
                {{ formatQuotaCapacity(record.cpu_used, record.cpu_limit, ' cores') }}
              </template>
              <template v-else-if="column.key === 'memory'">
                {{ formatQuotaCapacity(record.memory_used_gb, record.memory_limit_gb, ' GB') }}
              </template>
              <template v-else-if="column.key === 'parallelism'">
                {{ formatQuotaCapacity(record.parallelism_used, record.parallelism_limit, '') }}
              </template>
              <template v-else-if="column.key === 'gpu'">
                {{ record.gpu_requested_count }} · {{ record.gpu_requested_memory_mb }} MB
              </template>
              <template v-else-if="column.key === 'rejections'">
                <a-space v-if="Object.keys(record.rejection_counts).length" wrap>
                  <a-tag v-for="(count, reason) in record.rejection_counts" :key="reason" color="orange">
                    {{ reason }}: {{ count }}
                  </a-tag>
                </a-space>
                <span v-else class="muted-text">-</span>
              </template>
            </template>
          </a-table>
          <a-empty
            v-if="!quotaLoading && !(resourceQuotaStatus?.scopes?.length)"
            :description="resourceQuotaStatus?.enabled ? t('admin.noQuotaScopes') : t('admin.quotaDisabled')"
          />
        </a-card>
      </a-tab-pane>

      <a-tab-pane key="config" :tab="t('admin.configSnapshot')">
        <a-card :loading="loading">
          <pre class="json-view">{{ formattedConfig }}</pre>
        </a-card>
      </a-tab-pane>
    </a-tabs>

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import {
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  ThunderboltOutlined
} from '@ant-design/icons-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import {
  formatAdminDateTime,
  getSystemHealthServiceLabel,
  getSystemHealthStatusColor,
  getSystemHealthStatusText,
  sortSystemHealthServices
} from '@/domain/admin'
import {
  getSystemConfig,
  getSystemHealth,
  getSystemInfo,
  getSystemStats,
  getResourceQuotaStatus,
  getWorkerResourceStatus
} from '@/api/system'
import type {
  ResourceQuotaScope,
  SystemConfig,
  SystemHealth,
  SystemInfo,
  SystemStats,
  ResourceQuotaStatusResponse,
  WorkerResourceStatusResponse
} from '@/types/models'

const { t } = useI18n()

const activeTab = ref('overview')
const loading = ref(false)
const systemInfo = ref<SystemInfo | null>(null)
const systemStats = ref<SystemStats | null>(null)
const systemConfig = ref<SystemConfig | null>(null)
const systemHealth = ref<SystemHealth | null>(null)
const resourceLoading = ref(false)
const resourceStatus = ref<WorkerResourceStatusResponse | null>(null)
const quotaLoading = ref(false)
const resourceQuotaStatus = ref<ResourceQuotaStatusResponse | null>(null)

const formattedConfig = computed(() => {
  return JSON.stringify(systemConfig.value ?? {}, null, 2)
})

const healthServices = computed(() => {
  return sortSystemHealthServices(systemHealth.value?.services)
})

const resourceWorkerColumns = computed(() => [
  { title: t('admin.workerId'), key: 'worker_id', width: 190 },
  { title: t('admin.workerQueue'), key: 'queue', width: 180 },
  { title: t('admin.executorTypes'), key: 'executors', width: 220 },
  { title: t('admin.resourceTiers'), key: 'tiers', width: 140 },
  { title: t('admin.resourceCpuUsage'), key: 'cpu', width: 150 },
  { title: t('admin.resourceMemoryUsage'), key: 'memory', width: 150 },
  { title: t('admin.resourceParallelismUsage'), key: 'parallelism', width: 150 },
  { title: t('admin.resourceReservationCount'), key: 'reservations', width: 120 },
  { title: t('admin.resourceExecutionCount'), key: 'executions', width: 120 },
  { title: t('admin.resourceGpuCapacity'), key: 'gpu', width: 150 }
])

const resourceQuotaColumns = computed(() => [
  { title: t('admin.quotaScope'), key: 'scope', width: 180 },
  { title: t('admin.quotaCpu'), key: 'cpu', width: 150 },
  { title: t('admin.quotaMemory'), key: 'memory', width: 160 },
  { title: t('admin.quotaParallelism'), key: 'parallelism', width: 160 },
  { title: t('admin.quotaGpuRequests'), key: 'gpu', width: 150 },
  { title: t('admin.quotaRejections'), key: 'rejections', width: 360 }
])

const quotaRowKey = (record: ResourceQuotaScope) => record.scope_type + ':' + record.scope_id

const fetchSystemData = async () => {
  loading.value = true
  try {
    const [infoRes, statsRes, configRes, healthRes, resourceRes, quotaRes] = await Promise.all([
      getSystemInfo(),
      getSystemStats(),
      getSystemConfig(),
      getSystemHealth(),
      fetchResourceStatus(),
      fetchResourceQuotaStatus()
    ])
    systemInfo.value = infoRes.data
    systemStats.value = statsRes.data
    systemConfig.value = configRes.data
    systemHealth.value = healthRes.data
    resourceStatus.value = resourceRes
    resourceQuotaStatus.value = quotaRes
  } finally {
    loading.value = false
  }
}

const fetchResourceStatus = async (): Promise<WorkerResourceStatusResponse> => {
  resourceLoading.value = true
  try {
    const res = await getWorkerResourceStatus()
    return res.data
  } finally {
    resourceLoading.value = false
  }
}

const fetchResourceQuotaStatus = async (): Promise<ResourceQuotaStatusResponse> => {
  quotaLoading.value = true
  try {
    const res = await getResourceQuotaStatus()
    return res.data
  } finally {
    quotaLoading.value = false
  }
}

const refreshSystemData = async () => {
  await fetchSystemData()
  message.success(t('common.refreshSuccess'))
}

const healthStatusColor = getSystemHealthStatusColor
const healthStatusText = getSystemHealthStatusText
const healthServiceLabel = getSystemHealthServiceLabel
const formatDateTime = formatAdminDateTime

const resourceStatusColor = (status?: string) => {
  if (status === 'healthy') return 'green'
  if (status === 'degraded') return 'orange'
  if (status === 'unavailable') return 'red'
  return 'default'
}

const resourceStatusText = (status?: string) => {
  if (status === 'healthy') return t('admin.resourceStatusHealthy')
  if (status === 'degraded') return t('admin.resourceStatusDegraded')
  if (status === 'unavailable') return t('admin.resourceStatusUnavailable')
  return t('admin.resourceStatusUnknown')
}

const formatCapacity = (
  used: number,
  capacity: number | null | undefined,
  suffix: string
) => {
  if (capacity == null) return String(used) + suffix + ' / -'
  return String(used) + suffix + ' / ' + String(capacity) + suffix
}

const formatQuotaCapacity = (
  used: number,
  limit: number | null | undefined,
  suffix: string
) => {
  if (limit == null) return String(used) + suffix + ' / -'
  return String(used) + suffix + ' / ' + String(limit) + suffix
}

onMounted(() => {
  void fetchSystemData()
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-system {
  .system-tabs {
    :deep(.ant-tabs-nav) {
      margin-bottom: @spacing-lg;
    }
  }

  .health-card {
    margin-top: @spacing-md;
  }

  .quota-card {
    margin-top: @spacing-md;
  }

  .resource-status-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    margin-bottom: @spacing-md;

    h3,
    p {
      margin: 0;
    }

    p {
      color: @text-color-light-secondary;
      margin-top: @spacing-xs;
    }
  }

  .health-panel {
    display: grid;
    gap: @spacing-md;
  }

  .health-overall {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: @spacing-sm;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .health-services {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: @spacing-sm;
  }

  .health-service {
    min-width: 0;
    padding: @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    background: @bg-light-secondary;

    p {
      min-height: 40px;
      margin: @spacing-xs 0;
      color: @text-color-light-secondary;
      line-height: @line-height-base;
      word-break: break-word;
    }

    small {
      color: @text-color-light-tertiary;
    }
  }

  .health-service-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-sm;

    strong {
      color: @text-color-light-primary;
    }
  }

  .service-name-cell,
  .endpoint-cell,
  .runtime-cell {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
  }

  .service-name-line {
    display: flex;
    align-items: center;
    gap: @spacing-xs;
    flex-wrap: wrap;
  }

  .service-title {
    color: @text-color-light-primary;
    font-weight: @font-weight-semibold;
  }

  .service-meta,
  .muted-text,
  .test-message {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: @line-height-base;
  }

  .endpoint-cell span:last-child,
  .test-message {
    word-break: break-all;
  }

  .runtime-cell span {
    white-space: nowrap;
  }

  .json-view {
    background: @bg-color-light;
    padding: @spacing-md;
    border-radius: @border-radius-base;
    font-size: @font-size-sm;
    overflow: auto;
    max-height: 560px;
    margin: 0;
  }

}

@media (max-width: @screen-md) {
  .admin-system {
    }
}
</style>
