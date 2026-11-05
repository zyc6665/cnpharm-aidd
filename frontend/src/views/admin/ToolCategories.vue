<template>
  <div class="admin-tool-categories">
    <AppPageHeader :title="t('admin.toolCategories')" :subtitle="t('admin.toolCategoriesSubtitle')" />

    <a-alert
      class="family-alert"
      type="info"
      show-icon
      :message="t('admin.toolCategoriesAutoTitle')"
      :description="t('admin.toolCategoriesAutoHint')"
    />

    <a-card>
      <SkeletonList v-if="loading && categories.length === 0" :count="4" />

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
      />

      <a-table
        v-else
        :scroll="{ x: 'max-content' }"
        :columns="columns"
        :data-source="categories"
        :loading="loading"
        :pagination="false"
        row-key="id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <div class="name-cell">
              <div class="name-main">{{ familyLabel(record.slug) }}</div>
              <div class="name-meta">{{ record.slug }}</div>
            </div>
          </template>
          <template v-else-if="column.key === 'tool_count'">
            <span>{{ record.tool_count ?? record.count ?? 0 }}</span>
          </template>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { isAxiosError } from 'axios'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppEmptyState from '@/components/common/AppEmptyState.vue'
import AppInlineError from '@/components/common/AppInlineError.vue'
import SkeletonList from '@/components/common/SkeletonList.vue'
import { adminGetToolCategories } from '@/api/tools'
import { modelFamilyLabelKey } from '@/domain/tools/model-families'
import type { Category } from '@/types/models'

const { t } = useI18n()
const loading = ref(false)
const loadError = ref(false)
const loadErrorDetail = ref('')
const categories = ref<Category[]>([])

const columns = computed(() => [
  { title: t('admin.categoryName'), key: 'name' },
  { title: t('admin.statistics'), key: 'tool_count', width: 120 }
])

const familyLabel = (family?: string | null) => {
  const key = modelFamilyLabelKey(family)
  return key ? t(key) : (family || '-')
}

const fetchCategories = async () => {
  loading.value = true
  loadError.value = false
  loadErrorDetail.value = ''
  try {
    const response = await adminGetToolCategories()
    categories.value = response.data
  } catch (cause) {
    loadError.value = true
    loadErrorDetail.value = isAxiosError(cause) ? cause.message : String(cause)
  } finally {
    loading.value = false
  }
}

onMounted(fetchCategories)
</script>

<style scoped lang="less">
.admin-tool-categories {
  .family-alert {
    margin-bottom: 16px;
  }

  .name-cell {
    .name-main {
      font-weight: 500;
    }

    .name-meta {
      color: @text-secondary;
      font-size: @font-size-sm;
    }
  }
}
</style>
