<template>
  <div class="admin-tools">
    <div class="page-header">
      <h2>{{ t('admin.tools') }}</h2>
      <a-button type="primary" @click="showCreateModal = true">
        <PlusOutlined /> {{ t('admin.createTool') }}
      </a-button>
    </div>

    <!-- 搜索筛选 -->
    <a-card class="filter-card">
      <a-form layout="inline">
        <a-form-item :label="t('admin.keyword')">
          <a-input
            v-model:value="filters.keyword"
            :placeholder="t('admin.searchToolPlaceholder')"
            style="width: 200px"
            @pressEnter="handleSearch"
          />
        </a-form-item>
        <a-form-item :label="t('tools.category')">
          <a-select
            v-model:value="filters.category"
            :placeholder="t('common.all')"
            style="width: 150px"
            allowClear
          >
            <a-select-option value="structure-prediction">{{ t('admin.categoryStructure') }}</a-select-option>
            <a-select-option value="molecular-docking">{{ t('admin.categoryDocking') }}</a-select-option>
            <a-select-option value="sequence-analysis">{{ t('admin.categorySequence') }}</a-select-option>
            <a-select-option value="visualization">{{ t('admin.categoryVisualization') }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('admin.status')">
          <a-select
            v-model:value="filters.status"
            :placeholder="t('common.all')"
            style="width: 120px"
            allowClear
          >
            <a-select-option value="active">{{ t('admin.active') }}</a-select-option>
            <a-select-option value="inactive">{{ t('admin.inactive') }}</a-select-option>
            <a-select-option value="maintenance">{{ t('admin.maintenance') }}</a-select-option>
          </a-select>
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

    <!-- 工具列表 -->
    <a-card>
      <a-table
        :columns="columns"
        :data-source="tools"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <div class="tool-cell">
              <a-avatar
                :size="40"
                :src="record.icon"
                shape="square"
              >
                <template #icon><ExperimentOutlined /></template>
              </a-avatar>
              <div class="tool-info">
                <span class="name">{{ record.name }}</span>
                <span class="version">v{{ record.version }}</span>
              </div>
            </div>
          </template>
          <template v-else-if="column.key === 'category'">
            <a-tag :color="getCategoryColor(record.category)">
              {{ getCategoryName(record.category) }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-badge
              :status="getStatusBadge(record.status)"
              :text="t(`admin.${record.status}`)"
            />
          </template>
          <template v-else-if="column.key === 'credits'">
            💎 {{ record.credits_cost }}
          </template>
          <template v-else-if="column.key === 'stats'">
            <a-space>
              <span><PlayCircleOutlined /> {{ record.run_count }}</span>
              <span><HeartOutlined /> {{ record.favorite_count }}</span>
            </a-space>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-tooltip :title="t('common.edit')">
                <a-button type="link" size="small" @click="handleEdit(record)">
                  <EditOutlined />
                </a-button>
              </a-tooltip>
              <a-tooltip :title="t('admin.configParams')">
                <a-button type="link" size="small" @click="handleConfigParams(record)">
                  <SettingOutlined />
                </a-button>
              </a-tooltip>
              <a-dropdown>
                <a-button type="link" size="small">
                  <MoreOutlined />
                </a-button>
                <template #overlay>
                  <a-menu>
                    <a-menu-item v-if="record.status === 'active'" @click="handleToggleStatus(record, 'inactive')">
                      <PauseCircleOutlined /> {{ t('admin.deactivate') }}
                    </a-menu-item>
                    <a-menu-item v-else @click="handleToggleStatus(record, 'active')">
                      <PlayCircleOutlined /> {{ t('admin.activate') }}
                    </a-menu-item>
                    <a-menu-item @click="handleToggleStatus(record, 'maintenance')">
                      <ToolOutlined /> {{ t('admin.setMaintenance') }}
                    </a-menu-item>
                    <a-menu-divider />
                    <a-menu-item danger @click="handleDelete(record)">
                      <DeleteOutlined /> {{ t('common.delete') }}
                    </a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- 创建/编辑工具弹窗 -->
    <a-modal
      v-model:open="showCreateModal"
      :title="editingTool ? t('admin.editTool') : t('admin.createTool')"
      width="700px"
      @ok="handleSaveTool"
      :confirm-loading="saveLoading"
    >
      <a-form
        ref="formRef"
        :model="toolForm"
        :rules="formRules"
        :label-col="{ span: 5 }"
        :wrapper-col="{ span: 18 }"
      >
        <a-form-item :label="t('admin.toolName')" name="name">
          <a-input v-model:value="toolForm.name" />
        </a-form-item>
        <a-form-item :label="t('admin.toolCode')" name="code">
          <a-input v-model:value="toolForm.code" :disabled="!!editingTool" />
        </a-form-item>
        <a-form-item :label="t('common.description')" name="description">
          <a-textarea v-model:value="toolForm.description" :rows="3" />
        </a-form-item>
        <a-form-item :label="t('tools.category')" name="category">
          <a-select v-model:value="toolForm.category">
            <a-select-option value="structure-prediction">{{ t('admin.categoryStructure') }}</a-select-option>
            <a-select-option value="molecular-docking">{{ t('admin.categoryDocking') }}</a-select-option>
            <a-select-option value="sequence-analysis">{{ t('admin.categorySequence') }}</a-select-option>
            <a-select-option value="visualization">{{ t('admin.categoryVisualization') }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('tools.version')" name="version">
          <a-input v-model:value="toolForm.version" />
        </a-form-item>
        <a-form-item :label="t('admin.creditsCost')" name="credits_cost">
          <a-input-number v-model:value="toolForm.credits_cost" :min="0" style="width: 100%" />
        </a-form-item>
        <a-form-item :label="t('admin.serviceUrl')" name="service_url">
          <a-input v-model:value="toolForm.service_url" placeholder="http://localhost:8000" />
        </a-form-item>
        <a-form-item :label="t('admin.gpuRequired')">
          <a-switch v-model:checked="toolForm.gpu_required" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 参数配置弹窗 -->
    <a-modal
      v-model:open="showParamsModal"
      :title="t('admin.configParams')"
      width="800px"
      @ok="handleSaveParams"
    >
      <a-alert
        :message="t('admin.paramsConfigTip')"
        type="info"
        show-icon
        style="margin-bottom: 16px"
      />
      <a-textarea
        v-model:value="paramsJson"
        :rows="15"
        :placeholder="t('admin.paramsJsonPlaceholder')"
        style="font-family: monospace"
      />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  PlusOutlined,
  SearchOutlined,
  ReloadOutlined,
  EditOutlined,
  SettingOutlined,
  MoreOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  HeartOutlined,
  ToolOutlined
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import type { FormInstance } from 'ant-design-vue'

const { t } = useI18n()

const loading = ref(false)
const saveLoading = ref(false)
const showCreateModal = ref(false)
const showParamsModal = ref(false)
const editingTool = ref<any>(null)
const formRef = ref<FormInstance>()
const paramsJson = ref('')

const filters = reactive({
  keyword: '',
  category: undefined as string | undefined,
  status: undefined as string | undefined
})

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 50
})

const toolForm = reactive({
  name: '',
  code: '',
  description: '',
  category: 'structure-prediction',
  version: '1.0.0',
  credits_cost: 10,
  service_url: '',
  gpu_required: false
})

const formRules = {
  name: [{ required: true, message: t('admin.enterToolName') }],
  code: [{ required: true, message: t('admin.enterToolCode') }],
  description: [{ required: true, message: t('admin.enterDescription') }],
  category: [{ required: true, message: t('admin.selectCategory') }],
  version: [{ required: true, message: t('admin.enterVersion') }],
  service_url: [{ required: true, message: t('admin.enterServiceUrl') }]
}

// 模拟工具数据
const tools = ref([
  { id: 1, name: 'LVPocket', code: 'lvpocket', category: 'structure-prediction', version: '1.2.0', status: 'active', credits_cost: 20, run_count: 1500, favorite_count: 320, gpu_required: true },
  { id: 2, name: 'AlphaFold', code: 'alphafold', category: 'structure-prediction', version: '2.3.1', status: 'active', credits_cost: 50, run_count: 3200, favorite_count: 890, gpu_required: true },
  { id: 3, name: 'AutoDock', code: 'autodock', category: 'molecular-docking', version: '4.2.6', status: 'active', credits_cost: 15, run_count: 2100, favorite_count: 450, gpu_required: false },
  { id: 4, name: 'BLAST', code: 'blast', category: 'sequence-analysis', version: '2.14.0', status: 'active', credits_cost: 5, run_count: 5600, favorite_count: 1200, gpu_required: false },
  { id: 5, name: 'PyMOL', code: 'pymol', category: 'visualization', version: '2.5.0', status: 'maintenance', credits_cost: 10, run_count: 800, favorite_count: 150, gpu_required: false }
])

const columns = computed(() => [
  { title: t('admin.toolName'), key: 'name', width: 200 },
  { title: t('tools.category'), key: 'category', width: 150 },
  { title: t('admin.status'), key: 'status', width: 100 },
  { title: t('admin.creditsCost'), key: 'credits', width: 100 },
  { title: t('admin.statistics'), key: 'stats', width: 150 },
  { title: t('common.actions'), key: 'actions', width: 150, fixed: 'right' }
])

const getCategoryColor = (category: string) => {
  const colors: Record<string, string> = {
    'structure-prediction': 'blue',
    'molecular-docking': 'green',
    'sequence-analysis': 'orange',
    visualization: 'purple'
  }
  return colors[category] || 'default'
}

const getCategoryName = (category: string) => {
  const names: Record<string, string> = {
    'structure-prediction': t('admin.categoryStructure'),
    'molecular-docking': t('admin.categoryDocking'),
    'sequence-analysis': t('admin.categorySequence'),
    visualization: t('admin.categoryVisualization')
  }
  return names[category] || category
}

const getStatusBadge = (status: string) => {
  const badges: Record<string, 'success' | 'default' | 'warning'> = {
    active: 'success',
    inactive: 'default',
    maintenance: 'warning'
  }
  return badges[status] || 'default'
}

const handleSearch = () => {
  pagination.current = 1
  // TODO: 实现搜索
}

const handleReset = () => {
  filters.keyword = ''
  filters.category = undefined
  filters.status = undefined
  handleSearch()
}

const handleTableChange = (pag: any) => {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
}

const handleEdit = (record: any) => {
  editingTool.value = record
  toolForm.name = record.name
  toolForm.code = record.code
  toolForm.description = record.description || ''
  toolForm.category = record.category
  toolForm.version = record.version
  toolForm.credits_cost = record.credits_cost
  toolForm.service_url = record.service_url || ''
  toolForm.gpu_required = record.gpu_required
  showCreateModal.value = true
}

const handleSaveTool = async () => {
  try {
    await formRef.value?.validate()
    saveLoading.value = true
    // TODO: 保存工具
    message.success(t('common.success'))
    showCreateModal.value = false
    resetForm()
  } catch {
    // 验证失败
  } finally {
    saveLoading.value = false
  }
}

const resetForm = () => {
  editingTool.value = null
  toolForm.name = ''
  toolForm.code = ''
  toolForm.description = ''
  toolForm.category = 'structure-prediction'
  toolForm.version = '1.0.0'
  toolForm.credits_cost = 10
  toolForm.service_url = ''
  toolForm.gpu_required = false
}

const handleConfigParams = (record: any) => {
  editingTool.value = record
  paramsJson.value = JSON.stringify(record.input_params_schema || {}, null, 2)
  showParamsModal.value = true
}

const handleSaveParams = () => {
  try {
    JSON.parse(paramsJson.value)
    // TODO: 保存参数配置
    message.success(t('common.success'))
    showParamsModal.value = false
  } catch {
    message.error(t('admin.invalidJson'))
  }
}

const handleToggleStatus = (record: any, status: string) => {
  record.status = status
  message.success(t('common.success'))
}

const handleDelete = (record: any) => {
  Modal.confirm({
    title: t('admin.deleteToolConfirm'),
    content: t('admin.deleteToolConfirmContent', { name: record.name }),
    okType: 'danger',
    onOk: () => {
      tools.value = tools.value.filter(t => t.id !== record.id)
      message.success(t('common.success'))
    }
  })
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-tools {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: @spacing-lg;

    h2 {
      margin: 0;
    }
  }

  .filter-card {
    margin-bottom: @spacing-lg;
  }

  .tool-cell {
    display: flex;
    align-items: center;
    gap: @spacing-sm;

    .tool-info {
      display: flex;
      flex-direction: column;

      .name {
        font-weight: @font-weight-medium;
      }

      .version {
        font-size: @font-size-sm;
        color: @text-color-light-secondary;
      }
    }
  }
}
</style>
