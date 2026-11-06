<template>
  <div class="design-runs-page" :class="{ embedded }">
    <div class="container">
      <AppPageHeader
        v-if="!embedded"
        :title="t('design.runs.title')"
        :subtitle="t('design.runs.subtitle')"
      >
        <template #actions>
          <a-space>
            <a-button :loading="loading" @click="load(false)">
              <ReloadOutlined />
              {{ t('common.refresh') }}
            </a-button>
            <a-button type="primary" data-testid="design-runs-continue" @click="goSubmit">
              <PlusOutlined />
              {{ t('design.runs.continueFlow') }}
            </a-button>
          </a-space>
        </template>
      </AppPageHeader>

      <AppInlineError
        v-if="loadError"
        data-testid="design-runs-error"
        :title="t('design.runs.loadError')"
        :description="t('common.listStates.errorDescription')"
      >
        <a-button size="small" @click="load(false)">{{ t('common.listStates.retry') }}</a-button>
      </AppInlineError>

      <a-tabs v-model:activeKey="activeCategory" data-testid="design-runs-tabs">
        <a-tab-pane key="all" :tab="t('design.runs.category.all')" />
        <a-tab-pane
          v-for="category in DESIGN_RUN_CATEGORIES"
          :key="category.key"
          :tab="t(`design.runs.category.${category.key}`)"
        />
      </a-tabs>

      <a-table
        :columns="columns"
        :data-source="visibleRows"
        :loading="loading"
        :pagination="false"
        :locale="{ emptyText: emptyText }"
        row-key="id"
        size="middle"
        data-testid="design-runs-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <router-link class="run-name" :to="resolveDesignRunPath(record.tool_slug, record.id)">
              {{ record.name || record.id.slice(0, 8) }}
            </router-link>
            <div v-if="record.error_message" class="run-error" :title="record.error_message">
              {{ record.error_message }}
            </div>
          </template>
          <template v-else-if="column.key === 'category'">
            <span>{{ categoryLabel(record.tool_slug) }}</span>
          </template>
          <template v-else-if="column.key === 'tool'">
            <span>{{ record.tool_name || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'project'">
            <span v-if="record.project_id">{{ projectName(record.project_id) }}</span>
            <span v-else>-</span>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="getTaskStatusColor(record.status)">
              {{ t(getTaskStatusTextKey(record.status)) }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'progress'">
            <div class="run-progress">
              <a-progress
                :percent="Math.round(record.progress ?? 0)"
                size="small"
                :status="progressStatus(record.status)"
              />
            </div>
          </template>
          <template v-else-if="column.key === 'created_at'">
            {{ formatServerDateTime(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-button
                v-if="hasDedicatedResult(record)"
                type="link"
                size="small"
                data-testid="design-runs-open-result"
                @click="openResult(record)"
              >
                {{ t('design.runs.openResult') }}
              </a-button>
              <a-button type="link" size="small" @click="openDetail(record)">
                {{ t('design.runs.openDetail') }}
              </a-button>
              <a-button
                v-if="nextStepPath(record)"
                type="link"
                size="small"
                data-testid="design-runs-next-step"
                @click="openNext(record)"
              >
                {{ t('design.runs.nextStep') }}
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>

      <div v-if="total > pageSize" class="design-runs-pagination">
        <a-pagination
          v-model:current="page"
          :total="total"
          :page-size="pageSize"
          :show-total="(count: number) => t('common.totalItems', { total: count })"
          @change="load(false)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import type { TableColumnsType } from 'ant-design-vue'

defineProps<{ embedded?: boolean }>()

import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppInlineError from '@/components/common/AppInlineError.vue'
import { getTaskList } from '@/api/tasks'
import { listProjects } from '@/api/projects'
import {
  ALL_DESIGN_TOOL_SLUGS,
  DESIGN_RUN_CATEGORIES,
  findDesignRunCategory,
  resolveDesignRunPath,
  resolveTaskResultPath
} from '@/domain/design/runs'
import {
  getTaskStatusColor,
  getTaskStatusTextKey,
  isTerminalTask
} from '@/domain/tasks/status'
import { formatServerDateTime } from '@/utils/datetime'
import type { Task, TaskStatus } from '@/types/models'

const { t } = useI18n()
const router = useRouter()

const PAGE_SIZE = 20

const loading = ref(false)
const loadError = ref(false)
const rows = ref<Task[]>([])
const total = ref(0)
const page = ref(1)
const activeCategory = ref('all')
const projectNames = ref<Record<string, string>>({})

const pageSize = PAGE_SIZE

const columns = computed<TableColumnsType>(() => {
  const base: TableColumnsType = [
    { title: t('design.runs.columns.name'), key: 'name', width: 240 },
    { title: t('design.runs.columns.category'), key: 'category', width: 110 },
    { title: t('design.runs.columns.tool'), key: 'tool', width: 160 },
    { title: t('design.runs.columns.project'), key: 'project', width: 160 },
    { title: t('design.runs.columns.status'), key: 'status', width: 100 },
    { title: t('design.runs.columns.progress'), key: 'progress', width: 140 },
    { title: t('design.runs.columns.createdAt'), key: 'created_at', width: 170 },
    { title: t('design.runs.columns.actions'), key: 'actions', width: 170 }
  ]
  // 「全部」页签才需要类别列；单类别页签里这一列是常量，纯占地方。
  return activeCategory.value === 'all'
    ? base
    : base.filter(column => column.key !== 'category')
})

const visibleRows = computed(() => rows.value)

const emptyText = computed(() =>
  loadError.value ? t('common.listStates.emptyAfterError') : t('design.runs.empty')
)

function progressStatus(status: TaskStatus) {
  if (status === 'success') return 'success'
  if (isTerminalTask({ status })) return 'exception'
  if (status === 'running') return 'active'
  return 'normal'
}

function categoryLabel(toolSlug: string | undefined): string {
  const category = findDesignRunCategory(toolSlug)
  return category ? t(`design.runs.category.${category.key}`) : t('design.runs.category.other')
}

function projectName(projectId: string): string {
  return projectNames.value[projectId] ?? projectId.slice(0, 8)
}

function hasDedicatedResult(task: Task): boolean {
  return Boolean(resolveTaskResultPath(task.tool_slug, task.id))
}

function openResult(task: Task) {
  const path = resolveTaskResultPath(task.tool_slug, task.id)
  if (path) {
    void router.push(path)
  }
}

function openDetail(task: Task) {
  void router.push(`/tasks/${task.id}`)
}

function goSubmit() {
  void router.push('/design')
}

/**
 * 任务行的「下一步」目标：按类别给出后继环节。
 * 结构与口袋无专属结果页，统一落到「设计流程总览」并聚焦对应阶段。
 */
function nextStepPath(record: Task): string | null {
  const category = findDesignRunCategory(record.tool_slug)
  if (!category) return null
  const pid = record.project_id
  const q = pid ? `?project_id=${pid}` : ''
  switch (category.key) {
    case 'structure':
      return pid ? `/design?focus=pocket&project_id=${pid}` : '/design?focus=pocket'
    case 'pocket':
      return `/design/molecules${q}`
    case 'molecule':
      return `/predict${q}`
    default:
      return null
  }
}

function openNext(record: Task) {
  const path = nextStepPath(record)
  if (path) void router.push(path)
}

async function loadProjectNames() {
  try {
    const response = await listProjects()
    const map: Record<string, string> = {}
    for (const project of response.data?.items ?? []) {
      map[project.id] = project.name
    }
    projectNames.value = map
  } catch {
    // 项目名只是辅助信息，取不到就退化成短 id，不打断列表。
    projectNames.value = {}
  }
}

async function load(resetPage: boolean) {
  if (resetPage) page.value = 1
  loading.value = true
  loadError.value = false
  try {
    const category = DESIGN_RUN_CATEGORIES.find(item => item.key === activeCategory.value)
    const response = await getTaskList(
      {
        page: page.value,
        page_size: pageSize,
        view: 'all',
        // 「全部」页签拉六类 slug 的并集；单类别页签只拉该类别。
        tool_slugs: category ? [...category.slugs] : [...ALL_DESIGN_TOOL_SLUGS]
      },
      { silent: true }
    )
    const data = response.data
    rows.value = (data?.items ?? []) as Task[]
    total.value = data?.total ?? rows.value.length
  } catch {
    loadError.value = true
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadProjectNames()
  void load(true)
})

// 切页签时回到第 1 页，否则会停在上一个类别没有的页码上。
watch(activeCategory, () => {
  page.value = 1
  void load(false)
})
</script>

<style scoped lang="less">
.design-runs-page {
  min-height: 100%;
  padding: 0 0 40px;
}

.container {
  max-width: 1440px;
  margin: 0 auto;
  padding: 24px 24px 0;
}

.run-name {
  font-weight: 500;
}

.run-error {
  margin-top: 2px;
  overflow: hidden;
  color: var(--color-error, #ff4d4f);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-progress {
  min-width: 110px;
}

.design-runs-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
