<template>
  <div class="task-result-detail" data-testid="pocket-task-result">
    <AppPageHeader
      :title="t('tasks.resultPage.pocketTitle')"
      :subtitle="t('tasks.resultPage.pocketSubtitle')"
    />
    <TaskContextBar
      :task-id="taskId"
      :task="task"
      active="result"
      :fetch-task="false"
    />

    <a-row :gutter="16" class="task-result-detail__stats">
      <a-col :xs="24" :sm="12" :lg="8">
        <a-card :bordered="false">
          <a-statistic :title="t('tasks.resultPage.pocketCount')" :value="pocketCount" />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="8">
        <a-card :bordered="false">
          <a-statistic :title="t('tasks.resultPage.duration')" :value="duration" suffix="s" />
        </a-card>
      </a-col>
      <a-col :xs="24" :sm="12" :lg="8">
        <a-card :bordered="false">
          <a-statistic :title="t('tasks.resultPage.selectedModel')" :value="selectedModel" />
        </a-card>
      </a-col>
    </a-row>

    <PocketComplexViewer :task="task" />

    <a-card
      v-if="domainPockets.length"
      :bordered="false"
      class="task-result-detail__residues"
      :title="t('tasks.resultPage.keyResidues')"
    >
      <template #extra>
        <a-button
          size="small"
          type="link"
          data-testid="view-residues-in-achievements"
          @click="openInAchievements"
        >
          {{ t('tasks.resultPage.viewInAchievements') }}
        </a-button>
      </template>
      <a-spin :spinning="residueLoading">
        <PocketResiduePanel
          v-model:selected="selectedResIds"
          :residues="residues"
          :hint="t('tasks.resultPage.keyResiduesHint')"
        />
      </a-spin>
    </a-card>

    <a-card
      v-if="pocketRows.length"
      :bordered="false"
      class="task-result-detail__pockets"
      :title="t('tasks.resultPage.pocketList')"
    >
      <template v-if="domainPockets.length > 1" #extra>
        <a-select
          v-model:value="selectedPocketId"
          size="small"
          style="min-width: 220px"
          :options="pocketOptions"
          data-testid="task-pocket-select"
        />
      </template>
      <a-table
        data-testid="pocket-result-table"
        :data-source="pocketRows"
        :columns="pocketColumns"
        :pagination="false"
        size="small"
        row-key="id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'id'">#{{ record.id }}</template>
          <template v-else-if="column.key === 'files'">
            <span>{{ [record.atomPdb, record.residuePdb].filter(Boolean).join(' · ') || '-' }}</span>
          </template>
        </template>
      </a-table>
    </a-card>

    <TaskOutputSummary v-if="hasOutput" :task="task" />
    <AppEmptyState v-else :title="t('tasks.resultPage.noOutput')" />
  </div>
  <ResultDisclaimer />
</template>

<script setup lang="ts">
  import { computed, onMounted, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { useRouter } from 'vue-router'
  import PocketResiduePanel from '@/components/pockets/PocketResiduePanel.vue'
  import { listPocketResidues } from '@/api/targets'
  import { listTaskPockets, type TaskPocketItem } from '@/api/tasks'
  import AppEmptyState from '@/components/common/AppEmptyState.vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import TaskContextBar from '@/components/tasks/TaskContextBar.vue'
  import TaskOutputSummary from '@/components/tasks/TaskOutputSummary.vue'
  import PocketComplexViewer from '@/views/tasks/PocketComplexViewer.vue'
  import {
    getPocketCount,
    getPocketResultRows,
    getTaskResultArtifacts,
    getTaskResultMetrics,
  } from '@/domain/tasks/result'
  import type { Task } from '@/types/models'
  import type { PocketResidue } from '@/types/targets'
  import ResultDisclaimer from '@/components/common/ResultDisclaimer.vue'

  const props = defineProps<{ task: Task; taskId: string }>()
  const { t } = useI18n()
  const router = useRouter()

  /**
   * 结果页直接用「这次任务写回领域的口袋」：残基挂在 `pockets.id` 上，
   * 而表格里的 `metrics.pockets[].id` 是模型侧编号，两者不是一回事。
   */
  const domainPockets = ref<TaskPocketItem[]>([])
  const selectedPocketId = ref<string>('')
  const residues = ref<PocketResidue[]>([])
  const residueLoading = ref(false)
  const selectedResIds = ref<number[]>([])

  const pocketOptions = computed(() =>
    domainPockets.value.map((pocket) => ({
      label: `#${pocket.rank ?? '-'} · ${pocket.residue_count ?? 0} 残基${
        pocket.selected ? ' · 已选定' : ''
      }`,
      value: pocket.id
    }))
  )

  const activePocket = computed(
    () => domainPockets.value.find((pocket) => pocket.id === selectedPocketId.value) ?? null
  )

  async function loadDomainPockets() {
    const response = await listTaskPockets(props.taskId)
    domainPockets.value = response.data?.items ?? []
    const preferred =
      domainPockets.value.find((pocket) => pocket.selected) ?? domainPockets.value[0]
    selectedPocketId.value = preferred?.id ?? ''
  }

  async function loadResidues(pocketId: string) {
    if (!pocketId) {
      residues.value = []
      return
    }
    residueLoading.value = true
    try {
      const response = await listPocketResidues(pocketId)
      residues.value = response.data?.items ?? []
      selectedResIds.value = []
    } finally {
      residueLoading.value = false
    }
  }

  watch(selectedPocketId, (pocketId) => {
    void loadResidues(pocketId)
  })

  onMounted(() => {
    void loadDomainPockets()
  })

  function openInAchievements() {
    const pocket = activePocket.value
    if (!pocket) return
    void router.push({
      path: '/achievements',
      query: { projectId: pocket.project_id, targetId: pocket.target_id }
    })
  }

  const metrics = computed(() => getTaskResultMetrics(props.task))
  const pocketRows = computed(() => getPocketResultRows(props.task))
  const pocketCount = computed(() => getPocketCount(props.task))
  const artifactCount = computed(() => Object.keys(getTaskResultArtifacts(props.task)).length)
  const duration = computed(() => {
    const raw = props.task.execution_time_sec ?? metrics.value.duration_sec
    return typeof raw === 'number' ? Math.round(raw * 10) / 10 : 0
  })
  const selectedModel = computed(
    () =>
      props.task.tool?.name ||
      props.task.tool_name ||
      String(metrics.value.selected_model ?? '-')
  )
  const hasOutput = computed(
    () => pocketRows.value.length > 0 || artifactCount.value > 0 || (props.task.output_files?.length ?? 0) > 0
  )

  const pocketColumns = computed(() => [
    { title: t('tasks.resultPage.pocketId'), key: 'id', width: 140 },
    { title: t('tasks.resultPage.pocketFiles'), key: 'files' },
  ])
</script>

<style scoped lang="less">
  .task-result-detail {
    &__stats {
      margin-bottom: @spacing-lg;
    }

    &__pockets {
      margin-bottom: @spacing-lg;
    }

    &__residues {
      margin-bottom: @spacing-lg;
    }
  }
</style>
