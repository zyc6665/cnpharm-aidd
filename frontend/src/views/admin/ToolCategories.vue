<template>
  <div class="admin-tool-categories">
    <AppPageHeader :title="t('admin.toolCategories')" :subtitle="t('admin.toolCategoriesSubtitle')">
      <template #actions>
      <a-button type="primary" @click="openCreateModal">
        <PlusOutlined />
        {{ t('admin.createCategory') }}
      </a-button>
      </template>
    </AppPageHeader>

    <a-card>
      <SkeletonList v-if="loading && categories.length === 0" :count="6" />

      <AppInlineError
        v-else-if="loadError"
        data-testid="categories-error"
        :title="t('admin.listStates.categoriesLoadError')"
        :description="t('common.listStates.errorDescription')"
        :detail="loadErrorDetail"
      >
        <a-button size="small" @click="fetchCategories">{{ t('common.listStates.retry') }}</a-button>
      </AppInlineError>

      <AppEmptyState
        v-else-if="categories.length === 0"
        :title="t('admin.listStates.categoriesEmptyTitle')"
        :description="t('admin.listStates.categoriesEmptyHint')"
      >
        <a-button type="primary" @click="openCreateModal">{{ t('admin.createCategory') }}</a-button>
      </AppEmptyState>

      <a-table
        v-else
        :scroll="{ x: 'max-content' }"
        :columns="columns"
        :data-source="categories"
        :loading="loading"
        :pagination="false"
        row-key="id"
      >
        <template #bodyCell="{ column, record, index }">
          <template v-if="column.key === 'name'">
            <div class="name-cell">
              <div class="name-main">{{ record.name }}</div>
              <div class="name-meta">{{ record.slug }}</div>
            </div>
          </template>
          <template v-else-if="column.key === 'description'">
            <span>{{ record.description || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="record.is_enabled ? 'green' : 'default'">
              {{ record.is_enabled ? t('admin.active') : t('admin.inactive') }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'sort_order'">
            <a-space>
              <a-button size="small" @click="moveCategory(record, -1)" :disabled="index === 0">
                <ArrowUpOutlined />
              </a-button>
              <a-button
                size="small"
                @click="moveCategory(record, 1)"
                :disabled="index === categories.length - 1"
              >
                <ArrowDownOutlined />
              </a-button>
              <span>{{ record.sort_order }}</span>
            </a-space>
          </template>
          <template v-else-if="column.key === 'tool_count'">
            <span>{{ record.tool_count ?? record.count ?? 0 }}</span>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-button size="small" @click="handleEdit(record)">
                <EditOutlined />
                {{ t('common.edit') }}
              </a-button>
              <a-button size="small" @click="handleToggleStatus(record)">
                {{ record.is_enabled ? t('admin.deactivate') : t('admin.activate') }}
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
      :title="editingCategory ? t('admin.editCategory') : t('admin.createCategory')"
      :confirm-loading="saving"
      @ok="handleSave"
      @cancel="resetForm"
    >
      <a-form ref="formRef" :model="formState" :rules="formRules" layout="vertical">
        <a-form-item :label="t('admin.categoryName')" name="name">
          <a-input v-model:value="formState.name" />
        </a-form-item>
        <a-form-item :label="t('admin.categorySlug')" name="slug">
          <a-input v-model:value="formState.slug" />
        </a-form-item>
        <a-form-item :label="t('common.description')" name="description">
          <a-textarea v-model:value="formState.description" :rows="3" />
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
import { isAxiosError } from 'axios'
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined
} from '@ant-design/icons-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppEmptyState from '@/components/common/AppEmptyState.vue'
import AppInlineError from '@/components/common/AppInlineError.vue'
import SkeletonList from '@/components/common/SkeletonList.vue'
import type { Category } from '@/types/models'
import {
  adminCreateToolCategory,
  adminDeleteToolCategory,
  adminGetToolCategories,
  adminReorderToolCategories,
  adminToggleToolCategory,
  adminUpdateToolCategory
} from '@/api/tools'

const { t } = useI18n()

const loading = ref(false)
const loadError = ref(false)
const loadErrorDetail = ref('')
const saving = ref(false)
const showCreateModal = ref(false)
const editingCategory = ref<Category | null>(null)
const categories = ref<Category[]>([])
const formRef = ref<FormInstance>()
const formState = reactive({
  name: '',
  slug: '',
  description: ''
})

const formRules = computed(() => ({
  name: [{ required: true, message: t('admin.enterCategoryName') }],
  slug: [{ required: true, message: t('admin.enterCategorySlug') }]
}))

const columns = computed(() => [
  { title: t('admin.categoryName'), key: 'name' },
  { title: t('common.description'), key: 'description' },
  { title: t('admin.statistics'), key: 'tool_count', width: 100 },
  { title: t('admin.status'), key: 'status', width: 120 },
  { title: t('common.sort'), key: 'sort_order', width: 140 },
  { title: t('common.actions'), key: 'actions', width: 260 }
])

const normalizeCategorySlug = (value: string) => {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\s_]+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}

const fetchCategories = async () => {
  loading.value = true
  loadError.value = false
  loadErrorDetail.value = ''
  try {
    const res = await adminGetToolCategories()
    categories.value = res.data
  } catch (error) {
    categories.value = []
    loadError.value = true
    loadErrorDetail.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  editingCategory.value = null
  formState.name = ''
  formState.slug = ''
  formState.description = ''
}

const openCreateModal = () => {
  resetForm()
  showCreateModal.value = true
}

const handleEdit = (record: Category) => {
  editingCategory.value = record
  formState.name = record.name
  formState.slug = record.slug
  formState.description = record.description || ''
  showCreateModal.value = true
}

const handleSave = async () => {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  const normalizedSlug = normalizeCategorySlug(formState.slug || formState.name)
  if (!normalizedSlug) {
    message.error(t('admin.invalidCategorySlug'))
    return
  }

  saving.value = true
  try {
    if (editingCategory.value) {
      await adminUpdateToolCategory(editingCategory.value.id, {
        name: formState.name,
        slug: normalizedSlug,
        description: formState.description || undefined
      })
      message.success(t('common.success'))
    } else {
      await adminCreateToolCategory({
        name: formState.name,
        slug: normalizedSlug,
        description: formState.description || undefined
      })
      message.success(t('common.success'))
    }
    formState.slug = normalizedSlug
    showCreateModal.value = false
    resetForm()
    await fetchCategories()
  } catch (error) {
    if (isAxiosError(error) && error.response?.status === 422) {
      message.error(t('admin.invalidCategorySlug'))
    }
  } finally {
    saving.value = false
  }
}

const handleToggleStatus = async (record: Category) => {
  try {
    await adminToggleToolCategory(record.id, !record.is_enabled)
    message.success(t('common.success'))
    await fetchCategories()
  } catch {
    // 请求层已处理错误提示
  }
}

const handleDelete = (record: Category) => {
  Modal.confirm({
    title: t('admin.deleteCategoryConfirm'),
    content: t('admin.deleteCategoryConfirmContent', { name: record.name }),
    okType: 'danger',
    onOk: async () => {
      try {
        await adminDeleteToolCategory(record.id)
        message.success(t('common.success'))
        await fetchCategories()
      } catch {
        // 请求层已处理错误提示
      }
    }
  })
}

const moveCategory = async (record: Category, offset: -1 | 1) => {
  const currentIndex = categories.value.findIndex(item => item.id === record.id)
  const targetIndex = currentIndex + offset
  if (currentIndex < 0 || targetIndex < 0 || targetIndex >= categories.value.length) {
    return
  }

  const reordered = [...categories.value]
  const [moved] = reordered.splice(currentIndex, 1)
  if (!moved) {
    return
  }
  reordered.splice(targetIndex, 0, moved)
  try {
    await adminReorderToolCategories(reordered.map(item => item.id))
    await fetchCategories()
  } catch {
    // 请求层已处理错误提示
  }
}

onMounted(() => {
  void fetchCategories()
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-tool-categories {
  .name-cell {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .name-main {
    font-weight: @font-weight-semibold;
  }

  .name-meta {
    color: @text-color-light-tertiary;
    font-size: @font-size-sm;
  }
}
</style>
