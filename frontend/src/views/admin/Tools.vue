<template>
  <div class="admin-tools">
    <AppPageHeader :title="t('admin.tools')" :subtitle="t('admin.toolsSubtitle')">
      <template #actions>
        <a-space>
          <a-button @click="openModelGuide">
            <BookOutlined />
            {{ t('admin.modelGuide') }}
          </a-button>
          <a-button type="primary" @click="openToolPackages">
            <PlusOutlined />
            {{ t('admin.toolRegistrationPackageTitle') }}
          </a-button>
        </a-space>
      </template>
    </AppPageHeader>

    <a-alert
      type="info"
      show-icon
      class="model-admin-hint"
      :message="t('admin.modelAdminHintTitle')"
      :description="t('admin.modelAdminHint')"
    >
      <template #action>
        <a-button size="small" type="link" @click="openModelGuide">
          {{ t('admin.modelGuide') }}
        </a-button>
      </template>
    </a-alert>

    <AppFilterBar>
      <a-form layout="inline">
        <a-form-item :label="t('admin.keyword')">
          <a-input
            v-model:value="filters.keyword"
            :placeholder="t('admin.searchToolPlaceholder')"
            style="width: 240px"
            allow-clear
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
            style="width: 150px"
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

    <a-card :bordered="false" class="model-table-card">
      <SkeletonList v-if="loading && tools.length === 0" :count="6" />

      <AppInlineError
        v-else-if="loadError"
        data-testid="tools-error"
        :title="t('admin.listStates.toolsLoadError')"
        :description="t('common.listStates.errorDescription')"
        :detail="loadErrorDetail"
      >
        <a-button size="small" @click="fetchTools">{{ t('common.listStates.retry') }}</a-button>
      </AppInlineError>

      <AppEmptyState
        v-else-if="tools.length === 0"
        :title="t('admin.listStates.toolsEmptyTitle')"
        :description="t('admin.listStates.toolsEmptyHint')"
      >
        <a-button type="primary" @click="openToolPackages">
          {{ t('admin.listStates.goToolPackages') }}
        </a-button>
      </AppEmptyState>

      <a-table
        v-else
        :columns="columns"
        :data-source="tools"
        :loading="loading"
        :pagination="pagination"
        :row-class-name="rowClassName"
        row-key="id"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'model'">
            <div class="tool-cell">
              <div class="tool-icon">{{ record.icon || '🧪' }}</div>
              <div class="tool-info">
                <span class="name">{{ record.name }}</span>
                <span class="meta">{{ record.slug }}</span>
              </div>
            </div>
          </template>
          <template v-else-if="column.key === 'family'">
            <a-tag v-if="record.contract?.model_family" color="blue">
              {{ record.contract.model_family }}
            </a-tag>
            <span v-else class="muted">未归类</span>
          </template>
          <template v-else-if="column.key === 'version'">
            <div class="version-cell">
              <span class="version-number">{{ record.current_version?.version || '-' }}</span>
              <a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag>
            </div>
          </template>
          <template v-else-if="column.key === 'runtime'">
            <div class="runtime-cell">
              <a-tag :color="isLegacyTool(record) ? 'orange' : 'green'">
                {{ isLegacyTool(record) ? t('admin.modelRuntimeLegacy') : 'K8s Job' }}
              </a-tag>
              <span class="runtime-profile">{{ resourceProfile(record) }}</span>
            </div>
          </template>
          <template v-else-if="column.key === 'image'">
            <span class="image-digest" :title="imageDigest(record)">
              {{ shortDigest(record) || '-' }}
            </span>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space :size="2">
              <a-button type="link" size="small" @click="handleEdit(record)">
                <EditOutlined />
                {{ t('common.edit') }}
              </a-button>
              <a-dropdown>
                <a-button type="link" size="small" @click.stop>
                  {{ t('common.more') }}
                  <DownOutlined />
                </a-button>
                <template #overlay>
                  <a-menu @click="handleMenuClick($event, record)">
                    <a-menu-item key="publish">
                      <HistoryOutlined />
                      {{ t('admin.publishNewVersion') }}
                    </a-menu-item>
                    <a-menu-item key="packages">
                      <AppstoreOutlined />
                      {{ t('admin.toolPackages') }}
                    </a-menu-item>
                    <a-menu-divider />
                    <a-menu-item key="delete" danger>
                      <DeleteOutlined />
                      {{ t('common.delete') }}
                    </a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
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
import AppEmptyState from '@/components/common/AppEmptyState.vue'
import AppInlineError from '@/components/common/AppInlineError.vue'
import SkeletonList from '@/components/common/SkeletonList.vue'
import {
  AppstoreOutlined,
  BookOutlined,
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  HistoryOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'
import type { Category, Tool } from '@/types/models'
import {
  adminGetToolCategories,
  deleteTool,
  getToolList,
} from '@/api/tools'

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const loadError = ref(false)
const loadErrorDetail = ref('')
const categories = ref<Category[]>([])
const tools = ref<Tool[]>([])

const filters = reactive({
  keyword: '',
  category: undefined as string | undefined,
  status: undefined as string | undefined,
})

const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
  showSizeChanger: true,
})

const columns = computed(() => [
  { title: t('admin.modelColumn'), key: 'model', width: 280 },
  { title: t('admin.modelFamily'), key: 'family', width: 140 },
  { title: t('admin.currentVersion'), key: 'version', width: 150 },
  { title: t('admin.modelRuntime'), key: 'runtime', width: 180 },
  { title: t('admin.imageDigest'), key: 'image', width: 170 },
  { title: t('common.actions'), key: 'actions', width: 160, fixed: 'right' as const },
])

function configOf(tool: Tool): Record<string, unknown> {
  return (tool.current_version?.config ?? {}) as Record<string, unknown>
}

function isLegacyTool(tool: Tool): boolean {
  const config = configOf(tool)
  const toolType = config.tool_type ?? config.type
  if (typeof toolType === 'string' && toolType) {
    return toolType !== 'k8s_job'
  }
  return !config.k8s_image && !config.image
}

function resourceProfile(tool: Tool): string {
  const config = configOf(tool)
  const profile = config.k8s_resource_profile ?? config.resource_profile
  if (typeof profile === 'string' && profile) return profile
  const parts: string[] = []
  if (config.cpu_limit != null && config.cpu_limit !== '') parts.push(`${config.cpu_limit} vCPU`)
  if (typeof config.memory_limit === 'string' && config.memory_limit) parts.push(config.memory_limit)
  if (config.gpu_required) parts.push('GPU')
  return parts.length ? parts.join(' · ') : t('admin.modelRuntimeUnknown')
}

function imageDigest(tool: Tool): string {
  const config = configOf(tool)
  const raw = config.k8s_image || config.image
  if (typeof raw !== 'string' || !raw) return ''
  const at = raw.indexOf('@sha256:')
  return at >= 0 ? raw.slice(at + '@sha256:'.length) : raw
}

function shortDigest(tool: Tool): string {
  const digest = imageDigest(tool)
  return digest ? `${digest.slice(0, 12)}…` : ''
}

const statusColor = (status: Tool['status']) => {
  const mapping: Record<Tool['status'], string> = {
    draft: 'default',
    published: 'green',
    disabled: 'orange',
    deprecated: 'red',
  }
  return mapping[status]
}

function rowClassName(record: Tool): string {
  return isLegacyTool(record) ? 'model-row--legacy' : ''
}

const fetchCategories = async () => {
  const res = await adminGetToolCategories()
  categories.value = res.data.filter(category => category.is_enabled !== false)
}

const fetchTools = async () => {
  loading.value = true
  loadError.value = false
  loadErrorDetail.value = ''
  try {
    const res = await getToolList({
      page: pagination.current,
      page_size: pagination.pageSize,
      search: filters.keyword || undefined,
      category: filters.category,
      status: filters.status,
    })
    tools.value = res.data.items
    pagination.total = res.data.total
  } catch (error) {
    tools.value = []
    pagination.total = 0
    loadError.value = true
    loadErrorDetail.value = error instanceof Error ? error.message : String(error)
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

const openModelGuide = () => {
  router.push('/admin/model-guide')
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
    },
  })
}

const handleAction = (key: string, tool: Tool) => {
  if (key === 'publish') {
    handleEdit(tool)
    return
  }
  if (key === 'packages') {
    openToolPackages()
    return
  }
  if (key === 'delete') {
    handleDelete(tool)
  }
}

const handleMenuClick = (info: { key: string | number }, tool: Tool) => {
  handleAction(String(info.key), tool)
}

onMounted(async () => {
  await Promise.allSettled([fetchCategories(), fetchTools()])
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-tools {
  .model-admin-hint {
    margin-bottom: @spacing-lg;
    border-radius: @border-radius-lg;
  }

  .model-table-card {
    border: 1px solid @border-color;
    border-radius: @border-radius-lg;
    background: @bg-surface;
  }

  .tool-cell {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    min-width: 0;
  }

  .tool-icon {
    display: flex;
    flex: 0 0 38px;
    align-items: center;
    justify-content: center;
    width: 38px;
    height: 38px;
    border-radius: 11px;
    background: @accent-color-light;
    font-size: 19px;
  }

  .tool-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .name {
    overflow: hidden;
    color: @text-color-light-primary;
    font-weight: @font-weight-medium;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .meta {
    overflow: hidden;
    color: @text-color-light-tertiary;
    font-family: @font-family-mono;
    font-size: 11px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .version-cell,
  .runtime-cell {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }

  .version-number {
    color: @text-color-light-primary;
    font-family: @font-family-mono;
    font-size: 12px;
  }

  .runtime-profile {
    color: @text-color-light-tertiary;
    font-size: 11px;
  }

  .image-digest {
    display: inline-block;
    max-width: 100%;
    overflow: hidden;
    color: @text-color-light-secondary;
    font-family: @font-family-mono;
    font-size: 11px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .muted {
    color: @text-color-light-tertiary;
    font-size: @font-size-sm;
  }

  :deep(.model-row--legacy) td {
    background: fade(@warning-color, 3%);
  }

  :deep(.ant-table) {
    table-layout: fixed;
  }

  :deep(.ant-table-cell) {
    overflow: hidden;
  }
}
</style>
