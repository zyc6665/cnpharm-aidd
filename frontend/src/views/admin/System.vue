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

      <a-tab-pane key="model-services" :tab="t('admin.modelServices')">
        <div class="model-services-panel">
          <div class="model-services-toolbar">
            <div>
              <h3>{{ t('admin.modelServices') }}</h3>
              <p>{{ t('admin.modelServicesSubtitle') }}</p>
            </div>
            <a-space>
              <a-button @click="fetchModelServices">
                <ReloadOutlined />
                {{ t('common.refresh') }}
              </a-button>
              <a-button type="primary" @click="openCreateModelService">
                <PlusOutlined />
                {{ t('admin.createModelService') }}
              </a-button>
            </a-space>
          </div>

          <a-table
            :columns="modelServiceColumns"
            :data-source="modelServices"
            :loading="modelServicesLoading"
            :pagination="{ pageSize: 8, showSizeChanger: false }"
            :scroll="{ x: 1120 }"
            row-key="id"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'name'">
                <div class="service-name-cell">
                  <div class="service-name-line">
                    <span class="service-title">{{ record.name }}</span>
                    <a-tag v-if="record.is_default" color="blue">{{ t('admin.defaultService') }}</a-tag>
                  </div>
                  <span class="service-meta">{{ record.model_name }}</span>
                </div>
              </template>

              <template v-else-if="column.key === 'endpoint'">
                <div class="endpoint-cell">
                  <a-typography-text code>{{ record.provider_type }}</a-typography-text>
                  <span>{{ record.base_url }}</span>
                </div>
              </template>

              <template v-else-if="column.key === 'secret'">
                <a-space direction="vertical" size="small">
                  <a-tag :color="record.has_api_key ? 'green' : 'orange'">
                    {{ record.has_api_key ? t('admin.configuredApiKey') : t('admin.noApiKey') }}
                  </a-tag>
                  <span v-if="record.api_key_masked" class="muted-text">{{ record.api_key_masked }}</span>
                </a-space>
              </template>

              <template v-else-if="column.key === 'status'">
                <a-space direction="vertical" size="small">
                  <a-tag :color="record.is_enabled ? 'green' : 'default'">
                    {{ record.is_enabled ? t('admin.active') : t('admin.disabled') }}
                  </a-tag>
                  <a-tag v-if="record.is_default" color="processing">{{ t('admin.defaultService') }}</a-tag>
                </a-space>
              </template>

              <template v-else-if="column.key === 'runtime'">
                <div class="runtime-cell">
                  <span>{{ t('admin.timeoutSeconds') }}: {{ record.timeout_seconds }}{{ t('common.seconds') }}</span>
                  <span>{{ t('admin.maxTokens') }}: {{ record.max_tokens }}</span>
                  <span>{{ t('admin.temperature') }}: {{ record.temperature }}</span>
                </div>
              </template>

              <template v-else-if="column.key === 'last_test'">
                <a-space direction="vertical" size="small">
                  <a-tag :color="testStatusColor(record.last_test_status)">
                    {{ record.last_test_status || '-' }}
                  </a-tag>
                  <span class="muted-text">{{ formatDateTime(record.last_tested_at) }}</span>
                  <span v-if="record.last_test_message" class="test-message">{{ record.last_test_message }}</span>
                </a-space>
              </template>

              <template v-else-if="column.key === 'actions'">
                <a-space wrap>
                  <a-button
                    size="small"
                    :loading="testingServiceId === record.id"
                    @click="handleTestModelService(record)"
                  >
                    <ThunderboltOutlined />
                    {{ t('admin.testConnection') }}
                  </a-button>
                  <a-button
                    size="small"
                    :disabled="record.is_default || !record.is_enabled"
                    :loading="defaultingServiceId === record.id"
                    @click="handleSetDefaultModelService(record)"
                  >
                    <StarOutlined />
                    {{ t('admin.setDefault') }}
                  </a-button>
                  <a-button size="small" @click="openEditModelService(record)">
                    <EditOutlined />
                    {{ t('common.edit') }}
                  </a-button>
                  <a-popconfirm
                    :title="t('admin.confirmDeleteModelService')"
                    @confirm="handleDeleteModelService(record)"
                  >
                    <a-button size="small" danger :loading="deletingServiceId === record.id">
                      <DeleteOutlined />
                      {{ t('common.delete') }}
                    </a-button>
                  </a-popconfirm>
                </a-space>
              </template>
            </template>
          </a-table>
        </div>
      </a-tab-pane>

      <a-tab-pane key="config" :tab="t('admin.configSnapshot')">
        <a-card :loading="loading">
          <pre class="json-view">{{ formattedConfig }}</pre>
        </a-card>
      </a-tab-pane>
    </a-tabs>

    <a-drawer
      v-model:open="modelServiceDrawerOpen"
      :title="editingModelService ? t('admin.editModelService') : t('admin.createModelService')"
      width="560"
      destroy-on-close
      @close="resetModelServiceForm"
    >
      <a-form
        ref="modelServiceFormRef"
        :model="modelServiceForm"
        :rules="modelServiceRules"
        layout="vertical"
      >
        <a-form-item :label="t('common.name')" name="name">
          <a-input v-model:value="modelServiceForm.name" />
        </a-form-item>
        <a-form-item :label="t('admin.providerType')" name="provider_type">
          <a-select v-model:value="modelServiceForm.provider_type">
            <a-select-option value="openai_compatible">OpenAI Compatible</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('admin.baseUrl')" name="base_url">
          <a-input v-model:value="modelServiceForm.base_url" placeholder="https://api.example.com/v1" />
        </a-form-item>
        <a-form-item :label="t('admin.modelName')" name="model_name">
          <a-input v-model:value="modelServiceForm.model_name" placeholder="gpt-4o-mini" />
        </a-form-item>
        <a-form-item :label="t('admin.apiKey')" name="api_key">
          <a-input-password
            v-model:value="modelServiceForm.api_key"
            :placeholder="editingModelService ? t('admin.apiKeyPlaceholder') : ''"
          />
        </a-form-item>

        <a-row :gutter="12">
          <a-col :span="8">
            <a-form-item :label="t('admin.timeoutSeconds')" name="timeout_seconds">
              <a-input-number
                v-model:value="modelServiceForm.timeout_seconds"
                :min="1"
                :max="600"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item :label="t('admin.maxTokens')" name="max_tokens">
              <a-input-number
                v-model:value="modelServiceForm.max_tokens"
                :min="1"
                :max="200000"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item :label="t('admin.temperature')" name="temperature">
              <a-input-number
                v-model:value="modelServiceForm.temperature"
                :min="0"
                :max="2"
                :step="0.1"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item>
          <a-space direction="vertical">
            <a-checkbox v-model:checked="modelServiceForm.is_enabled">
              {{ t('admin.enabled') }}
            </a-checkbox>
            <a-checkbox v-model:checked="modelServiceForm.is_default" :disabled="!modelServiceForm.is_enabled">
              {{ t('admin.defaultService') }}
            </a-checkbox>
          </a-space>
        </a-form-item>
      </a-form>

      <div class="drawer-actions">
        <a-button @click="closeModelServiceDrawer">{{ t('common.cancel') }}</a-button>
        <a-button type="primary" :loading="savingModelService" @click="submitModelService">
          {{ t('common.save') }}
        </a-button>
      </div>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  StarOutlined,
  ThunderboltOutlined
} from '@ant-design/icons-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import {
  formatAdminDateTime,
  getModelServiceTestStatusColor,
  getSystemHealthServiceLabel,
  getSystemHealthStatusColor,
  getSystemHealthStatusText,
  sortSystemHealthServices
} from '@/domain/admin'
import {
  createModelService,
  deleteModelService,
  getModelServices,
  getSystemConfig,
  getSystemHealth,
  getSystemInfo,
  getSystemStats,
  setDefaultModelService,
  testModelService,
  updateModelService
} from '@/api/system'
import type {
  ModelService,
  ModelServiceCreateParams,
  ModelServiceUpdateParams,
  SystemConfig,
  SystemHealth,
  SystemInfo,
  SystemStats
} from '@/types/models'

const { t } = useI18n()

const activeTab = ref('overview')
const loading = ref(false)
const systemInfo = ref<SystemInfo | null>(null)
const systemStats = ref<SystemStats | null>(null)
const systemConfig = ref<SystemConfig | null>(null)
const systemHealth = ref<SystemHealth | null>(null)

const modelServices = ref<ModelService[]>([])
const modelServicesLoading = ref(false)
const modelServiceDrawerOpen = ref(false)
const savingModelService = ref(false)
const testingServiceId = ref<string | null>(null)
const defaultingServiceId = ref<string | null>(null)
const deletingServiceId = ref<string | null>(null)
const editingModelService = ref<ModelService | null>(null)
const modelServiceFormRef = ref<FormInstance>()

const createDefaultModelServiceForm = (): ModelServiceCreateParams => ({
  name: '',
  provider_type: 'openai_compatible',
  base_url: '',
  api_key: '',
  model_name: '',
  is_default: false,
  is_enabled: true,
  timeout_seconds: 60,
  max_tokens: 2048,
  temperature: 0.2
})

const modelServiceForm = reactive<ModelServiceCreateParams>(createDefaultModelServiceForm())

const formattedConfig = computed(() => {
  return JSON.stringify(systemConfig.value ?? {}, null, 2)
})

const healthServices = computed(() => {
  return sortSystemHealthServices(systemHealth.value?.services)
})

const modelServiceRules = computed(() => ({
  name: [{ required: true, message: `${t('common.name')}${t('common.required')}` }],
  base_url: [{ required: true, message: `${t('admin.baseUrl')}${t('common.required')}` }],
  model_name: [{ required: true, message: `${t('admin.modelName')}${t('common.required')}` }]
}))

const modelServiceColumns = computed(() => [
  { title: t('common.name'), key: 'name', width: 220 },
  { title: t('admin.baseUrl'), key: 'endpoint', width: 280 },
  { title: t('admin.apiKey'), key: 'secret', width: 150 },
  { title: t('admin.status'), key: 'status', width: 130 },
  { title: t('admin.runtimeSettings'), key: 'runtime', width: 190 },
  { title: t('admin.lastTest'), key: 'last_test', width: 220 },
  { title: t('common.actions'), key: 'actions', width: 360, fixed: 'right' as const }
])

const fetchSystemData = async () => {
  loading.value = true
  try {
    const [infoRes, statsRes, configRes, healthRes] = await Promise.all([
      getSystemInfo(),
      getSystemStats(),
      getSystemConfig(),
      getSystemHealth()
    ])
    systemInfo.value = infoRes.data
    systemStats.value = statsRes.data
    systemConfig.value = configRes.data
    systemHealth.value = healthRes.data
  } finally {
    loading.value = false
  }
}

const fetchModelServices = async () => {
  modelServicesLoading.value = true
  try {
    const res = await getModelServices()
    modelServices.value = res.data.items
  } finally {
    modelServicesLoading.value = false
  }
}

const refreshSystemData = async () => {
  await Promise.all([fetchSystemData(), fetchModelServices()])
  message.success(t('common.refreshSuccess'))
}

const resetModelServiceForm = () => {
  editingModelService.value = null
  Object.assign(modelServiceForm, createDefaultModelServiceForm())
  modelServiceFormRef.value?.clearValidate()
}

const openCreateModelService = () => {
  resetModelServiceForm()
  modelServiceDrawerOpen.value = true
}

const openEditModelService = (record: ModelService) => {
  editingModelService.value = record
  Object.assign(modelServiceForm, {
    name: record.name,
    provider_type: record.provider_type,
    base_url: record.base_url,
    api_key: '',
    model_name: record.model_name,
    is_default: record.is_default,
    is_enabled: record.is_enabled,
    timeout_seconds: record.timeout_seconds,
    max_tokens: record.max_tokens,
    temperature: record.temperature
  })
  modelServiceDrawerOpen.value = true
}

const closeModelServiceDrawer = () => {
  modelServiceDrawerOpen.value = false
  resetModelServiceForm()
}

const normalizeModelServicePayload = (): ModelServiceCreateParams => ({
  name: modelServiceForm.name.trim(),
  provider_type: modelServiceForm.provider_type,
  base_url: modelServiceForm.base_url.trim().replace(/\/+$/, ''),
  api_key: modelServiceForm.api_key?.trim() || undefined,
  model_name: modelServiceForm.model_name.trim(),
  is_default: modelServiceForm.is_default,
  is_enabled: modelServiceForm.is_enabled,
  timeout_seconds: modelServiceForm.timeout_seconds,
  max_tokens: modelServiceForm.max_tokens,
  temperature: modelServiceForm.temperature
})

const submitModelService = async () => {
  try {
    await modelServiceFormRef.value?.validate()
  } catch {
    return
  }

  savingModelService.value = true
  try {
    const payload = normalizeModelServicePayload()
    if (editingModelService.value) {
      const updatePayload: ModelServiceUpdateParams = { ...payload }
      if (!payload.api_key) {
        delete updatePayload.api_key
      }
      await updateModelService(editingModelService.value.id, updatePayload)
      message.success(t('admin.modelServiceUpdated'))
    } else {
      await createModelService(payload)
      message.success(t('admin.modelServiceCreated'))
    }
    modelServiceDrawerOpen.value = false
    resetModelServiceForm()
    await fetchModelServices()
  } finally {
    savingModelService.value = false
  }
}

const handleTestModelService = async (record: ModelService) => {
  testingServiceId.value = record.id
  try {
    const res = await testModelService(record.id)
    if (res.data.success) {
      message.success(res.data.message || t('admin.connectionSuccess'))
    } else {
      message.warning(res.data.message || t('common.error'))
    }
    await fetchModelServices()
  } finally {
    testingServiceId.value = null
  }
}

const handleSetDefaultModelService = async (record: ModelService) => {
  defaultingServiceId.value = record.id
  try {
    await setDefaultModelService(record.id)
    message.success(t('admin.defaultModelServiceUpdated'))
    await fetchModelServices()
  } finally {
    defaultingServiceId.value = null
  }
}

const handleDeleteModelService = async (record: ModelService) => {
  deletingServiceId.value = record.id
  try {
    await deleteModelService(record.id)
    message.success(t('admin.modelServiceDeleted'))
    await fetchModelServices()
  } finally {
    deletingServiceId.value = null
  }
}

const testStatusColor = getModelServiceTestStatusColor
const healthStatusColor = getSystemHealthStatusColor
const healthStatusText = getSystemHealthStatusText
const healthServiceLabel = getSystemHealthServiceLabel
const formatDateTime = formatAdminDateTime

onMounted(() => {
  void Promise.all([fetchSystemData(), fetchModelServices()])
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

  .model-services-panel {
    background: @bg-card-light;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    padding: @spacing-lg;
  }

  .health-card {
    margin-top: @spacing-md;
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

  .model-services-toolbar {
    display: flex;
    justify-content: space-between;
    gap: @spacing-md;
    align-items: flex-start;
    margin-bottom: @spacing-lg;

    h3 {
      margin: 0 0 @spacing-xs;
      color: @text-color-light-primary;
      font-size: @font-size-lg;
      font-weight: @font-weight-semibold;
      letter-spacing: 0;
    }

    p {
      margin: 0;
      color: @text-color-light-secondary;
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

  .drawer-actions {
    position: sticky;
    bottom: 0;
    display: flex;
    justify-content: flex-end;
    gap: @spacing-sm;
    margin: @spacing-lg -@spacing-lg -@spacing-lg;
    padding: @spacing-md @spacing-lg;
    background: @bg-card-light;
    border-top: 1px solid @border-color-light;
  }
}

@media (max-width: @screen-md) {
  .admin-system {
    .model-services-toolbar {
      flex-direction: column;
    }
  }
}
</style>
