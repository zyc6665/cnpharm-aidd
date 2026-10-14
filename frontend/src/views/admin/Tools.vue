<template>
  <div class="admin-tools">
    <AppPageHeader :title="t('admin.tools')" :subtitle="t('admin.toolsSubtitle')">
      <template #actions>
      <a-button type="primary" @click="openToolPackages">
        {{ t('admin.toolRegistrationPackageTitle') }}
      </a-button>
      </template>
    </AppPageHeader>

    <AppFilterBar>
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
    </AppFilterBar>

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
          <template v-else-if="column.key === 'validation'">
            <a-space size="small" wrap>
              <a-tag
                v-for="badge in toolValidationSummary(record).badges"
                :key="badge.label"
                :color="badge.color"
              >
                {{ badge.label }}
              </a-tag>
            </a-space>
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

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import AppFilterBar from '@/components/common/AppFilterBar.vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import {
  DeleteOutlined,
  EditOutlined,
  ReloadOutlined,
  SearchOutlined
} from '@ant-design/icons-vue'
import type { Category, Tool } from '@/types/models'
import { getToolValidationSummary } from '@/utils/tool-validation'
import {
  adminGetToolCategories,
  deleteTool,
  getToolList
} from '@/api/tools'

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const categories = ref<Category[]>([])
const tools = ref<Tool[]>([])

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
  { title: '验证等级', key: 'validation', width: 210 },
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

const toolValidationSummary = (tool: Tool) => getToolValidationSummary(tool.current_version?.config)

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

const openToolPackages = () => {
  router.push('/admin/tool-packages')
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
  .hidden-file-input {
    display: none;
  }

  .import-config-description {
    margin-bottom: @spacing-md;
    color: @text-color-light-secondary;
  }

  .registration-description {
    margin: 0 0 @spacing-lg;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: 1.6;
  }

  .registration-options {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }

  .registration-option {
    display: flex;
    align-items: flex-start;
    gap: 14px;
    min-width: 0;
    min-height: 112px;
    padding: 18px;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    background: @bg-surface;
    color: @text-color-light-primary;
    text-align: left;
    cursor: pointer;
    transition: border-color @transition-fast, background @transition-fast, box-shadow @transition-fast;

    &:hover {
      border-color: @primary-color;
      background: @bg-hover;
      box-shadow: @shadow-sm;
    }

    &:focus-visible {
      outline: 2px solid @primary-color;
      outline-offset: 2px;
    }

    &.is-recommended {
      border-color: fade(@success-color, 45%);

      &:hover {
        border-color: @success-color;
      }
    }
  }

  .registration-option-icon {
    display: inline-flex;
    flex: 0 0 40px;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border-radius: @border-radius-md;
    background: @bg-elevated;
    color: @text-secondary;
    font-size: 19px;
  }

  .registration-option--template .registration-option-icon {
    background: @accent-color-light;
    color: @primary-color;
  }

  .registration-option--remote .registration-option-icon {
    background: @info-color-light;
    color: @info-color;
  }

  .registration-option--package .registration-option-icon {
    background: @success-color-light;
    color: @success-color;
  }

  .registration-option--advanced .registration-option-icon {
    background: @warning-color-light;
    color: @warning-color;
  }

  .registration-option-copy {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 7px;
    min-width: 0;

    strong {
      color: @text-color-light-primary;
      font-size: @font-size-md;
      font-weight: @font-weight-semibold;
      line-height: 1.35;
    }

    span {
      color: @text-color-light-secondary;
      font-size: @font-size-xs;
      line-height: 1.6;
    }
  }

  .registration-option-heading {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  .registration-recommended {
    padding: 2px 7px;
    border-radius: @border-radius-sm;
    background: @success-color-light;
    color: @success-color !important;
    font-size: 11px !important;
    font-weight: @font-weight-medium;
    line-height: 1.4 !important;
  }

  .registration-option-arrow {
    flex: 0 0 auto;
    margin-top: 12px;
    color: @text-tertiary;
    transition: color @transition-fast, transform @transition-fast;
  }

  .registration-option:hover .registration-option-arrow {
    color: @primary-color;
    transform: translateX(2px);
  }

  .registration-option--package:hover .registration-option-arrow {
    color: @success-color;
  }

  @media (max-width: 720px) {
    .registration-options {
      grid-template-columns: 1fr;
    }
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
