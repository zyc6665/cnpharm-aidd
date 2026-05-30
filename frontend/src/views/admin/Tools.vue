<template>
  <div class="admin-tools">
    <AppPageHeader :title="t('admin.tools')" :subtitle="t('admin.toolsSubtitle')">
      <template #actions>
      <a-space>
        <a-button @click="openImportModal">
          <UploadOutlined />
          {{ t('admin.importToolConfig') }}
        </a-button>
        <a-button type="primary" @click="openCreatePage">
          <PlusOutlined />
          {{ t('admin.createTool') }}
        </a-button>
      </a-space>
      </template>
    </AppPageHeader>

    <a-card class="filter-card">
      <a-form layout="inline">
        <a-form-item :label="t('admin.keyword')">
          <a-input
            v-model:value="filters.keyword"
            :placeholder="t('admin.searchToolPlaceholder')"
            style="width: 220px"
            @pressEnter="fetchTools"
          />
        </a-form-item>
        <a-form-item :label="t('tools.category')">
          <a-select
            v-model:value="filters.category"
            :placeholder="t('common.all')"
            style="width: 180px"
            allow-clear
          >
            <a-select-option v-for="category in categories" :key="category.id" :value="category.id">
              {{ category.name }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item :label="t('admin.status')">
          <a-select
            v-model:value="filters.status"
            :placeholder="t('common.all')"
            style="width: 160px"
            allow-clear
          >
            <a-select-option value="draft">draft</a-select-option>
            <a-select-option value="published">published</a-select-option>
            <a-select-option value="disabled">disabled</a-select-option>
            <a-select-option value="deprecated">deprecated</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item>
          <a-space>
            <a-button type="primary" @click="handleSearch">
              <SearchOutlined />
              {{ t('common.search') }}
            </a-button>
            <a-button @click="resetFilters">
              <ReloadOutlined />
              {{ t('common.reset') }}
            </a-button>
          </a-space>
        </a-form-item>
      </a-form>
    </a-card>

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
              <div class="tool-icon">{{ record.icon || '🧪' }}</div>
              <div class="tool-info">
                <span class="name">{{ record.name }}</span>
                <span class="meta">{{ record.slug }}</span>
              </div>
            </div>
          </template>
          <template v-else-if="column.key === 'category'">
            <a-tag>{{ record.category || '-' }}</a-tag>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag>
          </template>
          <template v-else-if="column.key === 'stats'">
            <a-space>
              <span>{{ record.statistics?.usage_count ?? 0 }}</span>
              <span>/</span>
              <span>{{ record.statistics?.favorite_count ?? 0 }}</span>
            </a-space>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-button size="small" @click="handleEdit(record)">
                <EditOutlined />
                {{ t('common.edit') }}
              </a-button>
              <a-button size="small" danger @click="handleDelete(record)">
                <DeleteOutlined />
                {{ t('common.delete') }}
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>
    </a-card>

    <input
      ref="importConfigFileInput"
      type="file"
      accept=".json,application/json"
      class="hidden-file-input"
      @change="handleImportConfigFileChange"
    />

    <a-modal
      :open="importModalVisible"
      :title="t('admin.importToolConfigTitle')"
      :confirm-loading="importing"
      @ok="handleImportConfig"
      @cancel="resetImportModal"
    >
      <p class="import-config-description">{{ t('admin.importToolConfigDescription') }}</p>
      <a-form layout="vertical">
        <a-form-item :label="t('tools.category')">
          <a-select
            v-model:value="importCategoryId"
            :placeholder="t('common.all')"
            allow-clear
          >
            <a-select-option v-for="category in categories" :key="category.id" :value="category.id">
              {{ category.name }}
            </a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item>
          <a-checkbox v-model:checked="importPublish">
            {{ t('admin.importToolConfigPublish') }}
          </a-checkbox>
        </a-form-item>
        <a-form-item :label="t('admin.importToolConfig')">
          <a-space direction="vertical" style="width: 100%">
            <a-button @click="triggerImportConfigFile">
              <UploadOutlined />
              {{ t('admin.importToolConfigFromFile') }}
            </a-button>
            <a-textarea
              v-model:value="importConfigText"
              :rows="14"
              :placeholder="t('admin.importToolConfigPlaceholder')"
            />
          </a-space>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  UploadOutlined
} from '@ant-design/icons-vue'
import type { Category, Tool } from '@/types/models'
import {
  adminGetToolCategories,
  deleteTool,
  getToolList,
  importToolConfig
} from '@/api/tools'

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const categories = ref<Category[]>([])
const tools = ref<Tool[]>([])
const importModalVisible = ref(false)
const importing = ref(false)
const importConfigText = ref('')
const importCategoryId = ref<string | undefined>()
const importPublish = ref(false)
const importConfigFileInput = ref<HTMLInputElement | null>(null)

const filters = reactive({
  keyword: '',
  category: undefined as string | undefined,
  status: undefined as string | undefined
})

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
  showSizeChanger: true
})

const columns = computed(() => [
  { title: t('admin.toolName'), key: 'name' },
  { title: t('tools.category'), key: 'category', width: 180 },
  { title: t('admin.status'), key: 'status', width: 140 },
  { title: t('admin.statistics'), key: 'stats', width: 140 },
  { title: t('common.actions'), key: 'actions', width: 180 }
])

const statusColor = (status: Tool['status']) => {
  const mapping: Record<Tool['status'], string> = {
    draft: 'default',
    published: 'green',
    disabled: 'orange',
    deprecated: 'red'
  }
  return mapping[status]
}

const fetchCategories = async () => {
  const res = await adminGetToolCategories()
  categories.value = res.data.filter(category => category.is_enabled !== false)
}

const fetchTools = async () => {
  loading.value = true
  try {
    const res = await getToolList({
      page: pagination.current,
      page_size: pagination.pageSize,
      search: filters.keyword || undefined,
      category: filters.category,
      status: filters.status
    })
    tools.value = res.data.items
    pagination.total = res.data.total
  } finally {
    loading.value = false
  }
}

const resetFilters = async () => {
  filters.keyword = ''
  filters.category = undefined
  filters.status = undefined
  pagination.current = 1
  await fetchTools()
}

const handleSearch = async () => {
  pagination.current = 1
  await fetchTools()
}

const handleTableChange = async (pag: { current?: number; pageSize?: number }) => {
  pagination.current = pag.current || 1
  pagination.pageSize = pag.pageSize || 10
  await fetchTools()
}

const openCreatePage = () => {
  router.push('/admin/tools/create')
}

const openImportModal = () => {
  importModalVisible.value = true
}

const resetImportModal = () => {
  importModalVisible.value = false
  importConfigText.value = ''
  importCategoryId.value = undefined
  importPublish.value = false
}

const triggerImportConfigFile = () => {
  importConfigFileInput.value?.click()
}

const handleImportConfigFileChange = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) {
    return
  }

  importConfigText.value = await file.text()
  input.value = ''
}

const handleImportConfig = async () => {
  if (!importConfigText.value.trim()) {
    message.error(t('admin.importToolConfigRequired'))
    return
  }

  let parsedConfig: Record<string, unknown>
  try {
    parsedConfig = JSON.parse(importConfigText.value)
  } catch {
    message.error(t('admin.importToolConfigInvalid'))
    return
  }

  importing.value = true
  try {
    const response = await importToolConfig({
      config: parsedConfig,
      category_id: importCategoryId.value,
      publish: importPublish.value
    })

    message.success(`${response.data.tool.name} · ${t('admin.importToolConfigSuccess')}`)
    resetImportModal()
    await fetchTools()
  } finally {
    importing.value = false
  }
}

const handleEdit = (tool: Tool) => {
  router.push(`/admin/tools/${tool.id}/edit`)
}

const handleDelete = (tool: Tool) => {
  Modal.confirm({
    title: t('admin.deleteToolConfirm'),
    content: t('admin.deleteToolConfirmContent', { name: tool.name }),
    okType: 'danger',
    onOk: async () => {
      await deleteTool(tool.id)
      message.success(t('common.success'))
      await fetchTools()
    }
  })
}

onMounted(async () => {
  await Promise.all([fetchCategories(), fetchTools()])
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-tools {
  .filter-card {
    margin-bottom: @spacing-lg;
  }

  .hidden-file-input {
    display: none;
  }

  .import-config-description {
    margin-bottom: @spacing-md;
    color: @text-color-light-secondary;
  }

  .tool-cell {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
  }

  .tool-icon {
    width: 40px;
    height: 40px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: @accent-color-light;
    font-size: 20px;
  }

  .tool-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .name {
    font-weight: @font-weight-medium;
  }

  .meta {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }
}
</style>
