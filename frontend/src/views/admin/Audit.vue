<template>
  <div class="admin-audit">
    <AppPageHeader :title="t('admin.audit.title')" :subtitle="t('admin.audit.subtitle')">
      <template #actions>
        <a-button @click="refreshAuditData" :loading="loading">
          <ReloadOutlined /> {{ t('common.refresh') }}
        </a-button>
      </template>
    </AppPageHeader>

    <a-alert
      class="audit-notice"
      type="info"
      show-icon
      :message="t('admin.audit.appendOnlyNotice')"
      :description="t('admin.audit.detailNotice')"
    />

    <AppFilterBar class="audit-filters">
      <a-form layout="inline" :model="filters" @submit.prevent>
        <a-form-item :label="t('admin.audit.actor')">
          <a-select
            v-model:value="filters.actor"
            :options="actorOptions"
            :placeholder="t('common.all')"
            allow-clear
            show-search
            style="min-width: 180px"
          />
        </a-form-item>
        <a-form-item :label="t('admin.audit.action')">
          <a-select
            v-model:value="filters.action"
            :options="actionOptions"
            :placeholder="t('common.all')"
            allow-clear
            show-search
            style="min-width: 180px"
          />
        </a-form-item>
        <a-form-item :label="t('admin.audit.result')">
          <a-select
            v-model:value="filters.result"
            :options="resultOptions"
            :placeholder="t('common.all')"
            allow-clear
            style="min-width: 150px"
          />
        </a-form-item>
        <a-form-item :label="t('admin.audit.resourceType')">
          <a-select
            v-model:value="filters.resource_type"
            :options="resourceTypeOptions"
            :placeholder="t('common.all')"
            allow-clear
            show-search
            style="min-width: 170px"
          />
        </a-form-item>
        <a-form-item :label="t('admin.audit.timeRange')">
          <a-range-picker
            v-model:value="dateRange"
            show-time
            :placeholder="[t('admin.audit.startTime'), t('admin.audit.endTime')]"
          />
        </a-form-item>
        <a-form-item>
          <a-space>
            <a-button type="primary" @click="handleSearch">
              <SearchOutlined /> {{ t('common.search') }}
            </a-button>
            <a-button @click="handleReset">
              <ClearOutlined /> {{ t('common.reset') }}
            </a-button>
          </a-space>
        </a-form-item>
      </a-form>
    </AppFilterBar>

    <a-alert
      v-if="errorMessage"
      class="audit-error"
      type="error"
      show-icon
      :message="t('admin.audit.loadError')"
    >
      <template #action>
        <a-button size="small" danger @click="retryLoad">{{ t('admin.audit.retryLoad') }}</a-button>
      </template>
      <template #description>
        <span>{{ errorMessage }}</span>
      </template>
    </a-alert>

    <a-table
      :scroll="{ x: 1200 }"
      :columns="columns"
      :data-source="rows"
      :loading="loading"
      :pagination="pagination"
      :locale="{ emptyText: errorMessage ? t('admin.audit.loadError') : t('admin.audit.emptyState') }"
      row-key="id"
      size="middle"
      @change="handleTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'created_at'">
          <span class="audit-time">{{ formatAuditTimestamp(record.created_at) }}</span>
        </template>
        <template v-else-if="column.key === 'action'">
          <span class="audit-action">{{ record.action }}</span>
        </template>
        <template v-else-if="column.key === 'result'">
          <a-tag :color="resultColor(record.result)">{{ record.result }}</a-tag>
        </template>
        <template v-else-if="column.key === 'target'">
          <span class="audit-target">{{ describeAuditTarget(record) }}</span>
        </template>
        <template v-else-if="column.key === 'request_id'">
          <span class="audit-request">{{ record.request_id || '-' }}</span>
        </template>
        <template v-else-if="column.key === 'ip'">
          <span>{{ record.ip || '-' }}</span>
        </template>
        <template v-else-if="column.key === 'actor'">
          <span>{{ record.actor || '-' }}</span>
        </template>
        <template v-else-if="column.key === 'resource_type'">
          <span>{{ record.resource_type || '-' }}</span>
        </template>
      </template>

      <template #expandedRowRender="{ record }">
        <div class="audit-detail">
          <p class="audit-detail__title">{{ t('admin.audit.detail') }}</p>
          <pre class="audit-detail__body">{{ formatDetail(record.detail) }}</pre>
        </div>
      </template>
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Dayjs } from 'dayjs'
import { ClearOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import AppFilterBar from '@/components/common/AppFilterBar.vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import { getAuditFacets, listAuditLogs } from '@/api/admin-audit'
import {
  DEFAULT_AUDIT_PAGE_SIZE,
  MAX_AUDIT_PAGE_SIZE,
  buildAuditActionOptions,
  buildAuditActorOptions,
  buildAuditQueryParams,
  buildAuditResourceTypeOptions,
  buildAuditResultOptions,
  describeAuditTarget,
  formatAuditTimestamp
} from '@/domain/admin/audit'
import type { AuditFacets, AuditLogRow } from '@/types/audit'

const { t } = useI18n()

const loading = ref(false)
const rows = ref<AuditLogRow[]>([])
const facets = ref<AuditFacets | null>(null)
const dateRange = ref<[Dayjs, Dayjs] | null>(null)
const errorMessage = ref('')

/** 请求序号：并发筛选时只允许最后一次响应落地，避免旧结果覆盖新结果。 */
let requestSeq = 0

const filters = reactive({
  actor: undefined as string | undefined,
  action: undefined as string | undefined,
  result: undefined as string | undefined,
  resource_type: undefined as string | undefined
})

const pagination = reactive({
  current: 1,
  pageSize: DEFAULT_AUDIT_PAGE_SIZE,
  total: 0,
  showSizeChanger: true,
  pageSizeOptions: ['10', '20', '50', '100'],
  showTotal: (total: number) => t('common.totalItems', { total })
})

const toOptions = (values: string[]) => values.map(value => ({ label: value, value }))

const actorOptions = computed(() => toOptions(buildAuditActorOptions(facets.value)))
const actionOptions = computed(() => toOptions(buildAuditActionOptions(facets.value)))
const resultOptions = computed(() => toOptions(buildAuditResultOptions(facets.value)))
const resourceTypeOptions = computed(() => toOptions(buildAuditResourceTypeOptions(facets.value)))

const columns = computed(() => [
  { title: t('admin.audit.createdAt'), key: 'created_at', dataIndex: 'created_at', width: 180 },
  { title: t('admin.audit.actor'), key: 'actor', dataIndex: 'actor', width: 160 },
  { title: t('admin.audit.action'), key: 'action', dataIndex: 'action', width: 200 },
  { title: t('admin.audit.result'), key: 'result', dataIndex: 'result', width: 120 },
  { title: t('admin.audit.resourceType'), key: 'resource_type', dataIndex: 'resource_type', width: 160 },
  { title: t('admin.audit.target'), key: 'target', width: 240 },
  { title: t('admin.audit.ip'), key: 'ip', dataIndex: 'ip', width: 150 },
  { title: t('admin.audit.requestId'), key: 'request_id', dataIndex: 'request_id', width: 200 }
])

const resultColor = (result: string): string => {
  switch ((result || '').toUpperCase()) {
    case 'SUCCESS':
      return 'green'
    case 'DENIED':
      return 'orange'
    case 'FAILURE':
    case 'ERROR':
      return 'red'
    default:
      return 'default'
  }
}

const formatDetail = (detail: Record<string, unknown> | null): string => {
  if (detail === null || detail === undefined) {
    return '-'
  }
  try {
    return JSON.stringify(detail, null, 2)
  } catch {
    return String(detail)
  }
}

const currentFilters = (): Parameters<typeof buildAuditQueryParams>[0] => ({
  ...filters,
  start_time: dateRange.value?.[0]?.toISOString(),
  end_time: dateRange.value?.[1]?.toISOString(),
  page: pagination.current,
  page_size: Math.min(pagination.pageSize, MAX_AUDIT_PAGE_SIZE)
})

const fetchFacets = async (): Promise<void> => {
  try {
    const response = await getAuditFacets()
    facets.value = response.data ?? null
  } catch {
    // facet 只是筛选下拉的数据源，取不到时保持空下拉，不影响表格主查询。
    facets.value = null
  }
}

const fetchRows = async (): Promise<void> => {
  const seq = ++requestSeq
  loading.value = true
  try {
    const response = await listAuditLogs(buildAuditQueryParams(currentFilters()))
    if (seq !== requestSeq) {
      return
    }

    const items = response.data?.items ?? []
    const totalPages = response.data?.total_pages ?? 0
    // 越界页收敛：删掉最后一页的最后一条后再点「下一页」不应停留在空表。
    if (totalPages > 0 && pagination.current > totalPages) {
      pagination.current = totalPages
      await fetchRows()
      return
    }

    rows.value = items
    pagination.total = response.data?.total ?? 0
    errorMessage.value = ''
  } catch (error) {
    if (seq !== requestSeq) {
      return
    }
    // 不静默成空表：明确提示查询失败，并允许原地重试。
    rows.value = []
    pagination.total = 0
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    if (seq === requestSeq) {
      loading.value = false
    }
  }
}

const handleSearch = async (): Promise<void> => {
  pagination.current = 1
  await fetchRows()
}

const handleReset = async (): Promise<void> => {
  filters.actor = undefined
  filters.action = undefined
  filters.result = undefined
  filters.resource_type = undefined
  dateRange.value = null
  pagination.current = 1
  pagination.pageSize = DEFAULT_AUDIT_PAGE_SIZE
  await fetchRows()
}

const handleTableChange = async (pag: { current?: number; pageSize?: number }): Promise<void> => {
  const nextPageSize = Math.min(pag.pageSize || DEFAULT_AUDIT_PAGE_SIZE, MAX_AUDIT_PAGE_SIZE)
  // 每页条数变化时页码必须回到 1，否则 current 与 pageSize 组合会落到空页。
  const pageSizeChanged = nextPageSize !== pagination.pageSize
  pagination.pageSize = nextPageSize
  pagination.current = pageSizeChanged ? 1 : pag.current || 1
  await fetchRows()
}

const retryLoad = async (): Promise<void> => {
  await Promise.all([fetchFacets(), fetchRows()])
}

const refreshAuditData = async (): Promise<void> => {
  await Promise.all([fetchFacets(), fetchRows()])
}

onMounted(refreshAuditData)
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.admin-audit {
  .audit-notice {
    margin-bottom: @spacing-md;
  }

  .audit-filters {
    margin-bottom: @spacing-lg;
  }

  .audit-error {
    margin-bottom: @spacing-md;
  }

  .audit-time {
    font-variant-numeric: tabular-nums;
    color: @text-color-light-secondary;
  }

  .audit-action {
    font-weight: 500;
  }

  .audit-target,
  .audit-request {
    word-break: break-all;
  }

  .audit-detail {
    padding: @spacing-sm @spacing-md;
    background: @bg-hover;
    border-radius: 8px;
  }

  .audit-detail__title {
    margin: 0 0 @spacing-xs;
    font-size: @font-size-xs;
    color: @text-color-light-tertiary;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .audit-detail__body {
    margin: 0;
    max-height: 320px;
    overflow: auto;
    font-size: @font-size-xs;
    color: @text-color-light-secondary;
    white-space: pre-wrap;
    word-break: break-all;
  }
}
</style>
