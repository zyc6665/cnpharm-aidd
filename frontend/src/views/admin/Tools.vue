<template>
  <div class="admin-tools">
    <div class="page-header">
      <div>
        <h2>{{ t('admin.tools') }}</h2>
        <p>{{ t('admin.toolsSubtitle') }}</p>
      </div>
      <a-button type="primary" @click="openCreateModal">
        <PlusOutlined />
        {{ t('admin.createTool') }}
      </a-button>
    </div>

    <a-card class="filter-card">
      <a-form layout="inline">
        <a-form-item :label="t('admin.keyword')">
          <a-input
            v-model:value="filters.keyword"
            :placeholder="t('admin.searchToolPlaceholder')"
            style="width: 220px"
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
            <a-button type="primary" @click="fetchTools">
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
        :data-source="filteredTools"
        :loading="loading"
        :pagination="false"
        row-key="id"
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

    <a-modal
      v-model:open="showCreateModal"
      :title="editingTool ? t('admin.editTool') : t('admin.createTool')"
      :confirm-loading="saving"
      @ok="handleSaveTool"
      @cancel="resetForm"
    >
      <a-form ref="formRef" :model="toolForm" :rules="formRules" layout="vertical">
        <a-form-item :label="t('admin.toolName')" name="name">
          <a-input v-model:value="toolForm.name" />
        </a-form-item>
        <a-form-item :label="t('admin.toolCode')" name="slug">
          <a-input v-model:value="toolForm.slug" :disabled="!!editingTool" />
        </a-form-item>
        <a-form-item :label="t('common.description')" name="description">
          <a-textarea v-model:value="toolForm.description" :rows="3" />
        </a-form-item>
        <a-form-item :label="t('tools.category')" name="category_id">
          <a-select v-model:value="toolForm.category_id">
            <a-select-option v-for="category in categories" :key="category.id" :value="category.id">
              {{ category.name }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormInstance } from 'ant-design-vue'
import { message, Modal } from 'ant-design-vue'
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined
} from '@ant-design/icons-vue'
import type { Category, Tool, ToolCreateParams } from '@/types/models'
import {
  adminGetToolCategories,
  createTool,
  deleteTool,
  getToolList,
  updateTool
} from '@/api/tools'

const { t } = useI18n()

const loading = ref(false)
const saving = ref(false)
const showCreateModal = ref(false)
const formRef = ref<FormInstance>()
const categories = ref<Category[]>([])
const tools = ref<Tool[]>([])
const editingTool = ref<Tool | null>(null)

const filters = reactive({
  keyword: '',
  category: undefined as string | undefined,
  status: undefined as string | undefined
})

const toolForm = reactive({
  name: '',
  slug: '',
  description: '',
  category_id: ''
})

const formRules = computed(() => ({
  name: [{ required: true, message: t('admin.enterToolName') }],
  slug: [{ required: true, message: t('admin.enterToolCode') }],
  category_id: [{ required: true, message: t('admin.selectCategory') }]
}))

const columns = computed(() => [
  { title: t('admin.toolName'), key: 'name' },
  { title: t('tools.category'), key: 'category', width: 180 },
  { title: t('admin.status'), key: 'status', width: 140 },
  { title: t('admin.statistics'), key: 'stats', width: 140 },
  { title: t('common.actions'), key: 'actions', width: 180 }
])

const filteredTools = computed(() => {
  return tools.value.filter(tool => {
    const matchKeyword =
      !filters.keyword ||
      tool.name.toLowerCase().includes(filters.keyword.toLowerCase()) ||
      tool.slug.toLowerCase().includes(filters.keyword.toLowerCase())
    const matchCategory = !filters.category || tool.category_id === filters.category
    const matchStatus = !filters.status || tool.status === filters.status
    return matchKeyword && matchCategory && matchStatus
  })
})

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
    const res = await getToolList({ status: filters.status })
    tools.value = res.data.items
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  editingTool.value = null
  toolForm.name = ''
  toolForm.slug = ''
  toolForm.description = ''
  toolForm.category_id = ''
}

const resetFilters = async () => {
  filters.keyword = ''
  filters.category = undefined
  filters.status = undefined
  await fetchTools()
}

const openCreateModal = () => {
  resetForm()
  showCreateModal.value = true
}

const handleEdit = (tool: Tool) => {
  editingTool.value = tool
  toolForm.name = tool.name
  toolForm.slug = tool.slug
  toolForm.description = tool.description || ''
  toolForm.category_id = tool.category_id || ''
  showCreateModal.value = true
}

const handleSaveTool = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  saving.value = true
  try {
    if (editingTool.value) {
      await updateTool(editingTool.value.id, {
        name: toolForm.name,
        description: toolForm.description || undefined,
        category_id: toolForm.category_id
      })
    } else {
      const payload: ToolCreateParams = {
        name: toolForm.name,
        slug: toolForm.slug,
        description: toolForm.description || undefined,
        category_id: toolForm.category_id
      }
      await createTool(payload)
    }
    message.success(t('common.success'))
    showCreateModal.value = false
    resetForm()
    await fetchTools()
  } finally {
    saving.value = false
  }
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
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: @spacing-lg;
    margin-bottom: @spacing-lg;

    h2 {
      margin: 0;
    }

    p {
      margin: @spacing-xs 0 0;
      color: @text-color-light-secondary;
    }
  }

  .filter-card {
    margin-bottom: @spacing-lg;
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
    font-weight: @font-weight-semibold;
  }

  .meta {
    color: @text-color-light-tertiary;
    font-size: @font-size-sm;
  }
}
</style>
