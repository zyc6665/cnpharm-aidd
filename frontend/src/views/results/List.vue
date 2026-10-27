<template>
  <main class="results-list-page">
    <router-link :to="`/projects/${projectId}`" class="back-link">
      {{ t('compounds.backToProject') }}
    </router-link>
    <ProjectWorkspaceNav :project-id="projectId" />

    <AppPageHeader :title="t('results.title')" :subtitle="t('results.subtitle')">
      <template #actions>
        <a-button :loading="loading" data-testid="results-refresh" @click="loadResults">
          {{ t('common.refresh') }}
        </a-button>
      </template>
    </AppPageHeader>

    <a-alert
      v-if="loadError"
      class="results-alert"
      type="error"
      show-icon
      data-testid="results-error"
      :message="t('results.errors.loadResults')"
    >
      <template #action>
        <a-button size="small" @click="loadResults">{{ t('common.refresh') }}</a-button>
      </template>
    </a-alert>

    <div class="results-toolbar">
      <a-select
        v-model:value="statusFilter"
        class="status-filter"
        allow-clear
        :placeholder="t('results.columns.status')"
        :options="statusOptions"
        data-testid="results-status-filter"
        @change="handleFilterChange"
      />
      <span class="results-total" data-testid="results-total">
        {{ t('common.totalItems', { total }) }}
      </span>
    </div>

    <SkeletonList v-if="loading && sortedResults.length === 0" :count="5" />

    <a-table
      :scroll="{ x: 'max-content' }"
      v-else
      :columns="columns"
      :data-source="sortedResults"
      :pagination="false"
      :locale="{ emptyText: t('results.empty') }"
      row-key="task_id"
      size="middle"
      :custom-row="handleRow"
      data-testid="results-table"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <router-link :to="`/results/${record.task_id}`" class="result-link">
            {{ record.name || record.task_id }}
          </router-link>
        </template>
        <template v-else-if="column.key === 'type'">
          {{ record.tool_name || record.domain || '-' }}
        </template>
        <template v-else-if="column.key === 'status'">
          <a-tag :color="statusColor(record.status)">
            {{ t(`tasks.status.${record.status}`) }}
          </a-tag>
        </template>
        <template v-else-if="column.key === 'finished_at'">
          {{ formatDate(record.finished_at) }}
        </template>
        <template v-else-if="column.key === 'submitted_by'">
          {{ record.submitted_by || '-' }}
        </template>
        <template v-else-if="column.key === 'execution_time_sec'">
          {{ formatExecutionSeconds(record.execution_time_sec) }}
        </template>
      </template>
    </a-table>

    <div v-if="total > pageSize" class="results-pagination">
      <a-pagination
        v-model:current="page"
        :total="total"
        :page-size="pageSize"
        :show-total="(count: number) => t('common.totalItems', { total: count })"
        @change="loadResults"
      />
    </div>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { formatDateTimeMinutes } from '@/utils/datetime'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import SkeletonList from '@/components/common/SkeletonList.vue'
  import { listProjectResults } from '@/api/results'
  import { RESULT_STATUSES, formatExecutionSeconds, sortResultsByFinishedDesc } from '@/domain/results'
  import type { ProjectResultSummary } from '@/types/compounds'
  import type { TaskStatus } from '@/types/models'

  interface StatusOption {
    label: string
    value: TaskStatus
  }

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()

  const projectId = computed(() => String(route.params.projectId || ''))
  const pageSize = 20

  const loading = ref(false)
  const loadError = ref(false)
  const results = ref<ProjectResultSummary[]>([])
  const total = ref(0)
  const page = ref(1)
  const statusFilter = ref<TaskStatus | undefined>(undefined)

  const sortedResults = computed(() => sortResultsByFinishedDesc(results.value))

  const statusOptions = computed<StatusOption[]>(() =>
    RESULT_STATUSES.map(status => ({ label: t(`tasks.status.${status}`), value: status }))
  )

  const columns = computed(() => [
    { title: t('results.columns.name'), key: 'name', width: 260 },
    { title: t('results.columns.type'), key: 'type', width: 160 },
    { title: t('results.columns.status'), key: 'status', width: 120 },
    { title: t('results.columns.finishedAt'), key: 'finished_at', width: 170 },
    { title: t('results.columns.submittedBy'), key: 'submitted_by', width: 160 },
    { title: t('results.columns.executionTime'), key: 'execution_time_sec', width: 120 }
  ])

  function statusColor(status: TaskStatus): string {
    if (status === 'success') return 'green'
    if (status === 'failure') return 'red'
    return 'default'
  }

  function formatDate(value: string | null | undefined): string {
    return value ? formatDateTimeMinutes(value) : '-'
  }

  function handleRow(record: ProjectResultSummary): { onClick: () => void } {
    return {
      onClick: () => {
        void router.push(`/results/${record.task_id}`)
      }
    }
  }

  function handleFilterChange(): void {
    page.value = 1
    void loadResults()
  }

  async function loadResults(): Promise<void> {
    if (!projectId.value) return

    loading.value = true
    loadError.value = false
    try {
      const response = await listProjectResults(projectId.value, {
        page: page.value,
        page_size: pageSize,
        ...(statusFilter.value ? { status: statusFilter.value } : {})
      })
      results.value = response.data.items
      total.value = response.data.total
    } catch {
      loadError.value = true
      results.value = []
      total.value = 0
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    void loadResults()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .results-list-page {
    max-width: 1240px;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .back-link {
    display: inline-block;
    margin-bottom: @spacing-lg;
    color: @text-tertiary;
  }

  .results-alert {
    margin-bottom: @spacing-md;
  }

  .results-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    margin-bottom: @spacing-md;
  }

  .status-filter {
    width: 200px;
  }

  .results-total {
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .results-pagination {
    display: flex;
    justify-content: flex-end;
    margin-top: @spacing-md;
  }

  .result-link {
    color: @primary-color;
  }
</style>
