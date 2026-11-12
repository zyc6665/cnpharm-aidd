<template>
  <main class="decisions-page" data-testid="decisions-page">
    <router-link :to="`/projects/${projectId}`" class="back-link">
      {{ t('decisions.backToProject') }}
    </router-link>
    <ProjectWorkspaceNav :project-id="projectId" />

    <AppPageHeader :title="t('decisions.title')" :subtitle="t('decisions.subtitle')">
      <template #actions>
        <a-button :loading="loading" data-testid="decisions-refresh" @click="loadAll">
          {{ t('common.refresh') }}
        </a-button>
        <a-button type="primary" data-testid="decisions-create" @click="openDrawer">
          {{ t('decisions.create') }}
        </a-button>
      </template>
    </AppPageHeader>

    <!-- 只追加语义：页头常驻说明，页面不提供编辑/删除入口（docs/10 DB-09）。 -->
    <a-alert
      class="decisions-notice"
      type="info"
      show-icon
      data-testid="decisions-append-only-notice"
      :message="t('decisions.appendOnlyNotice')"
      :description="t('decisions.appendOnlyDescription')"
    />

    <section v-if="stage" class="decisions-stage" data-testid="decisions-stage">
      <div class="decisions-stage__head">
        <span class="decisions-stage__label">{{ t('decisions.stage.current') }}</span>
        <a-tag color="blue">{{ stage.currentStage }}</a-tag>
        <span class="decisions-stage__name">{{ stage.stageName }}</span>
        <span v-if="stage.nextStage" class="decisions-stage__next">
          {{ t('decisions.stage.next') }}: {{ stage.nextStage }}
        </span>
      </div>

      <div class="decisions-stage__counters">
        <span v-for="counter in counterEntries" :key="counter.key" class="decisions-stage__counter">
          {{ t(`decisions.stage.counters.${counter.key}`) }}: {{ counter.value }}
        </span>
      </div>

      <div v-if="stage.gaps.length > 0" class="decisions-stage__gaps" data-testid="decisions-stage-gaps">
        <span class="decisions-stage__gaps-title">{{ t('decisions.stage.gaps') }}</span>
        <div v-for="gap in stage.gaps" :key="gap.code" class="decisions-gap">
          <span class="decisions-gap__message">{{ gap.message }}</span>
          <span class="decisions-gap__action">{{ gap.action }}</span>
          <router-link
            v-if="gap.link"
            :to="gap.link"
            class="decisions-gap__link"
            data-testid="decisions-stage-gap-link"
          >
            {{ t('decisions.stage.go') }}
          </router-link>
        </div>
      </div>
      <p v-else class="decisions-stage__no-gaps">{{ t('decisions.stage.noGaps') }}</p>
    </section>

    <a-alert
      v-if="stageError"
      class="decisions-alert"
      type="warning"
      show-icon
      data-testid="decisions-stage-error"
      :message="t('decisions.errors.loadStage')"
    />

    <!-- 错态：AppErrorState 负责「回上一级」，重试留在原地，不必绕回项目总览再进来。 -->
    <div v-if="loadError" class="decisions-error" data-testid="decisions-error">
      <a-button
        class="decisions-error__retry"
        :loading="loading"
        data-testid="decisions-error-retry"
        @click="loadAll"
      >
        {{ t('decisions.errors.retry') }}
      </a-button>
      <AppErrorState
        code="ERR"
        :title="t('decisions.errors.loadDecisions')"
        :description="t('decisions.errors.loadDecisionsHint')"
        :action-text="t('decisions.backToProject')"
        :to="`/projects/${projectId}`"
      />
    </div>

    <template v-else>
      <div class="decisions-toolbar">
        <a-select
          v-model:value="pointFilter"
          class="decisions-filter"
          allow-clear
          :placeholder="t('decisions.filterPoint')"
          :options="pointFilterOptions"
          data-testid="decisions-point-filter"
          @change="handleFilterChange"
        />
        <span class="decisions-total" data-testid="decisions-total">
          {{ t('decisions.timeline.total', { total }) }}
        </span>
      </div>

      <SkeletonList v-if="loading && records.length === 0" :count="4" />

      <a-empty
        v-else-if="records.length === 0"
        class="decisions-empty"
        data-testid="decisions-empty"
      >
        <template #description>
          <p class="decisions-empty__title">{{ t('decisions.empty.title') }}</p>
          <p class="decisions-empty__hint">{{ t('decisions.empty.hint') }}</p>
        </template>
        <a-button type="primary" data-testid="decisions-empty-create" @click="openDrawer">
          {{ t('decisions.empty.create') }}
        </a-button>
      </a-empty>

      <div v-else class="decisions-timeline" data-testid="decisions-timeline">
        <section
          v-for="group in groups"
          :key="group.point"
          class="decisions-group"
          data-testid="decisions-group"
        >
          <header class="decisions-group__head">
            <span class="decisions-group__point">{{ group.point }}</span>
            <h2 class="decisions-group__title">{{ t(group.labelKey) }}</h2>
            <span class="decisions-group__count">{{ group.records.length }}</span>
          </header>

          <article
            v-for="record in group.records"
            :key="record.id"
            class="decisions-record"
            data-testid="decisions-record"
          >
            <div class="decisions-record__meta">
              <span class="decisions-record__meta-item">
                {{ t('decisions.timeline.decidedBy') }}: {{ record.decided_by || placeHolder }}
              </span>
              <span class="decisions-record__meta-item">
                {{ t('decisions.timeline.decidedAt') }}: {{ formatDecisionTime(record.decided_at) }}
              </span>
              <span class="decisions-record__meta-item">
                {{ t('decisions.timeline.subject') }}:
                {{ t(resolveDecisionSubjectLabel(record).typeKey) }}
                <span :title="record.subject_id">{{ resolveSubjectText(record) }}</span>
              </span>
              <a-tag color="green">
                {{ t('decisions.timeline.selected', { count: recordCounts(record).selected }) }}
              </a-tag>
              <a-tag color="red">
                {{ t('decisions.timeline.excluded', { count: recordCounts(record).excluded }) }}
              </a-tag>
            </div>

            <p class="decisions-record__reason" data-testid="decisions-record-reason">
              {{ record.reason }}
            </p>

            <a-button
              type="link"
              size="small"
              class="decisions-record__toggle"
              data-testid="decisions-record-toggle"
              @click="toggleRecord(record.id)"
            >
              {{ isExpanded(record.id) ? t('decisions.timeline.collapse') : t('decisions.timeline.expand') }}
            </a-button>

            <div v-if="isExpanded(record.id)" class="decisions-record__detail">
              <h3 class="decisions-detail__title">{{ t('decisions.snapshot.title') }}</h3>
              <p class="decisions-detail__hint">{{ t('decisions.snapshot.hint') }}</p>

              <a-table
                :scroll="{ x: 'max-content' }"
                class="decisions-snapshot"
                data-testid="decisions-snapshot-table"
                :columns="snapshotColumns"
                :data-source="record.items"
                :pagination="false"
                :locale="{ emptyText: t('common.noData') }"
                row-key="candidate_id"
                size="small"
              >
                <template #bodyCell="{ column, record: item }">
                  <template v-if="column.key === 'candidate_id'">
                    <span class="decisions-snapshot__candidate">
                      {{ snapshotCandidateId(item) }}
                    </span>
                  </template>
                  <template v-else-if="column.key === 'verdict'">
                    <a-tag :color="snapshotVerdictColor(item)">
                      {{ snapshotVerdictText(item) }}
                    </a-tag>
                  </template>
                  <template v-else-if="column.key === 'score'">
                    <!--
                      「未记录」与「0 分」必须分得开：缺失行的悬浮说明直接给出
                      `snapshot_attrs.score_source`，让人能看出这是当时没录分而不是录了 0。
                    -->
                    <span
                      v-if="snapshotScoreMissing(item)"
                      class="decisions-snapshot__missing"
                      :title="snapshotScoreSource(item)"
                      data-testid="decisions-snapshot-score-missing"
                    >
                      {{ snapshotScoreText(item) }}
                    </span>
                    <span v-else>{{ snapshotScoreText(item) }}</span>
                  </template>
                  <template v-else-if="column.key === 'rank'">
                    {{ snapshotRankText(item) }}
                  </template>
                </template>
              </a-table>

              <p
                v-if="recordHasMissingScore(record)"
                class="decisions-detail__missing-hint"
                data-testid="decisions-snapshot-missing-hint"
              >
                {{ t('decisions.snapshot.missingHint') }}
              </p>

              <h3 class="decisions-detail__title">{{ t('decisions.timeline.basisTasks') }}</h3>
              <p v-if="record.basis_task_ids.length === 0" class="decisions-detail__empty">
                {{ t('decisions.timeline.noBasisTasks') }}
              </p>
              <ul v-else class="decisions-detail__tasks">
                <li v-for="taskId in record.basis_task_ids" :key="taskId">
                  <router-link :to="`/tasks/${taskId}`" class="decisions-detail__task-link">
                    {{ taskId }}
                  </router-link>
                </li>
              </ul>

              <h3 class="decisions-detail__title">{{ t('decisions.timeline.basisMetrics') }}</h3>
              <p v-if="isBasisMetricsEmpty(record)" class="decisions-detail__empty">
                {{ t('decisions.timeline.noBasisMetrics') }}
              </p>
              <details v-else class="decisions-detail__metrics">
                <summary class="decisions-detail__metrics-summary">
                  {{ t('decisions.timeline.basisMetrics') }}
                </summary>
                <pre class="decisions-detail__metrics-body">{{ formatBasisMetrics(record.basis_metrics) }}</pre>
              </details>
            </div>
          </article>
        </section>
      </div>

      <div v-if="total > 0" class="decisions-pagination" data-testid="decisions-pagination">
        <a-pagination
          :current="page"
          :total="total"
          :page-size="pageSize"
          :page-size-options="pageSizeOptions"
          show-size-changer
          :show-total="(count: number) => t('decisions.timeline.total', { total: count })"
          @change="handlePageChange"
        />
      </div>
    </template>

    <a-drawer
      :open="createOpen"
      :title="t('decisions.drawer.title')"
      :width="560"
      placement="right"
      @close="closeDrawer"
    >
      <div v-if="createOpen" class="decisions-drawer" data-testid="decisions-drawer">
        <a-form layout="vertical">
          <a-form-item :label="t('decisions.drawer.decisionPoint')">
            <a-select
              v-model:value="draft.decisionPoint"
              :options="pointOptions"
              data-testid="decisions-drawer-point"
            />
          </a-form-item>
          <a-form-item :label="t('decisions.drawer.subjectType')">
            <a-select
              v-model:value="draft.subjectType"
              :options="subjectTypeOptions"
              data-testid="decisions-drawer-subject-type"
            />
          </a-form-item>
          <a-form-item :label="t('decisions.drawer.subjectId')">
            <a-input
              v-model:value="draft.subjectId"
              :placeholder="t('decisions.drawer.subjectIdPlaceholder')"
              data-testid="decisions-drawer-subject-id"
            />
          </a-form-item>
          <a-form-item :label="t('decisions.drawer.reason')">
            <a-textarea
              v-model:value="draft.reason"
              :rows="3"
              :placeholder="t('decisions.drawer.reasonPlaceholder')"
              data-testid="decisions-drawer-reason"
            />
          </a-form-item>
          <a-form-item :label="t('decisions.drawer.selectedIds')">
            <a-input
              v-model:value="draft.selectedIdsText"
              :placeholder="t('decisions.drawer.idsPlaceholder')"
              data-testid="decisions-drawer-selected"
            />
          </a-form-item>
          <a-form-item :label="t('decisions.drawer.excludedIds')">
            <a-input
              v-model:value="draft.excludedIdsText"
              :placeholder="t('decisions.drawer.idsPlaceholder')"
              data-testid="decisions-drawer-excluded"
            />
          </a-form-item>
          <a-form-item :label="t('decisions.drawer.basisTaskIds')">
            <a-input
              v-model:value="draft.basisTaskIdsText"
              :placeholder="t('decisions.drawer.basisTaskIdsPlaceholder')"
              data-testid="decisions-drawer-basis-tasks"
            />
          </a-form-item>
          <a-form-item :label="t('decisions.drawer.basisMetrics')">
            <a-textarea
              v-model:value="draft.basisMetricsText"
              :rows="3"
              :placeholder="t('decisions.drawer.basisMetricsPlaceholder')"
              data-testid="decisions-drawer-basis-metrics"
            />
          </a-form-item>
        </a-form>

        <a-alert
          type="warning"
          show-icon
          data-testid="decisions-drawer-snapshot-hint"
          :message="t('decisions.drawer.snapshotHint')"
        />

        <p v-if="submitError" class="decisions-drawer__error" data-testid="decisions-drawer-error">
          {{ submitError }}
        </p>

        <div class="decisions-drawer__actions">
          <a-button data-testid="decisions-drawer-cancel" @click="closeDrawer">
            {{ t('decisions.drawer.cancel') }}
          </a-button>
          <a-button
            type="primary"
            :loading="submitting"
            data-testid="decisions-drawer-submit"
            @click="submitDecision"
          >
            {{ t('decisions.drawer.submit') }}
          </a-button>
        </div>
      </div>
    </a-drawer>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, reactive, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AppErrorState from '@/components/common/AppErrorState.vue'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import SkeletonList from '@/components/common/SkeletonList.vue'
  import { createProjectDecision, getProjectStage, listProjectDecisions } from '@/api/decisions'
  import { listCandidateSets } from '@/api/compounds'
  import {
    DECISION_POINT_OPTIONS,
    DECISION_SUBJECT_TYPE_OPTIONS,
    DEFAULT_DECISION_PAGE_SIZE,
    DECISION_PAGE_SIZE_OPTIONS,
    PLACEHOLDER,
    buildDecisionCreatePayload,
    clampDecisionPage,
    clampDecisionPageSize,
    formatBasisMetrics,
    formatDecisionTime,
    formatSnapshotRank,
    formatSnapshotScore,
    groupDecisionsByPoint,
    isBasisMetricsEmpty,
    isSnapshotScoreMissing,
    recordHasMissingScore,
    resolveDecisionErrorMessage,
    resolveDecisionSubjectLabel,
    resolveVerdictKey,
    summarizeRecordCounts,
    type DecisionDraft
  } from '@/domain/decisions'
  import type { DecisionItem, DecisionPoint, DecisionRecord, ProjectStage } from '@/types/decisions'
  import { SCORE_SOURCE_MISSING } from '@/types/decisions'

  const route = useRoute()
  const { t } = useI18n()

  const projectId = computed(() => String(route.params.projectId ?? ''))
  const placeHolder = PLACEHOLDER

  const loading = ref(false)
  const loadError = ref(false)
  const stageError = ref(false)
  const submitting = ref(false)

  const records = ref<DecisionRecord[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(DEFAULT_DECISION_PAGE_SIZE)
  const pointFilter = ref<DecisionPoint | undefined>(undefined)
  const stage = ref<ProjectStage | null>(null)

  const expandedIds = ref<string[]>([])
  const createOpen = ref(false)
  const submitError = ref('')

  const draft = reactive<DecisionDraft>({
    decisionPoint: 'DP3',
    subjectType: 'CANDIDATE_SET',
    subjectId: '',
    reason: '',
    selectedIdsText: '',
    excludedIdsText: '',
    basisTaskIdsText: '',
    basisMetricsText: ''
  })

  const groups = computed(() => groupDecisionsByPoint(records.value))

  const pointOptions = computed(() =>
    DECISION_POINT_OPTIONS.map(option => ({ value: option.value, label: t(option.labelKey) }))
  )
  const pointFilterOptions = computed(() => pointOptions.value)

  const subjectTypeOptions = computed(() =>
    DECISION_SUBJECT_TYPE_OPTIONS.map(option => ({ value: option.value, label: t(option.labelKey) }))
  )

  const pageSizeOptions = DECISION_PAGE_SIZE_OPTIONS.map(size => String(size))

  const snapshotColumns = computed(() => [
    { title: t('decisions.snapshot.candidateId'), key: 'candidate_id', width: 220 },
    { title: t('decisions.snapshot.verdict'), key: 'verdict', width: 100 },
    { title: t('decisions.snapshot.score'), key: 'score', width: 120 },
    { title: t('decisions.snapshot.rank'), key: 'rank', width: 100 }
  ])

  const counterEntries = computed(() => {
    const counters = stage.value?.counters
    if (!counters) {
      return [] as { key: string; value: number }[]
    }
    return [
      { key: 'targets', value: counters.targets },
      { key: 'structures', value: counters.structures },
      { key: 'selectedPockets', value: counters.selected_pockets },
      { key: 'candidates', value: counters.candidates },
      { key: 'submittedTasks', value: counters.submitted_tasks },
      { key: 'finishedTasks', value: counters.finished_tasks },
      { key: 'decisions', value: counters.decisions }
    ]
  })

  /* 快照行：模板里拿到的 `record` 是 antd 表格的松类型，统一在脚本里收窄。 */

  function snapshotCandidateId(row: unknown): string {
    return (row as DecisionItem).candidate_id
  }

  function snapshotScoreMissing(row: unknown): boolean {
    return isSnapshotScoreMissing(row as DecisionItem)
  }

  function snapshotScoreText(row: unknown): string {
    const item = row as DecisionItem
    const text = formatSnapshotScore(item)
    return isSnapshotScoreMissing(item) ? t(text) : text
  }

  function snapshotRankText(row: unknown): string {
    return formatSnapshotRank(row as DecisionItem)
  }

  /**
   * 缺失行的原始来源标记（`snapshot_attrs.score_source`，后端没录分时写 `missing`）。
   *
   * 只用于悬浮说明，判定本身走 `@/domain/decisions`——页面不重复实现业务判断。
   */
  function snapshotScoreSource(row: unknown): string {
    const source = (row as DecisionItem).snapshot_attrs?.score_source
    return typeof source === 'string' && source ? source : SCORE_SOURCE_MISSING
  }

  function snapshotVerdictText(row: unknown): string {
    return t(resolveVerdictKey(row as DecisionItem))
  }

  function snapshotVerdictColor(row: unknown): string {
    return (row as DecisionItem).verdict === 'SELECTED' ? 'green' : 'red'
  }

  function recordCounts(record: DecisionRecord): { selected: number; excluded: number } {
    return summarizeRecordCounts(record)
  }

  function isExpanded(id: string): boolean {
    return expandedIds.value.includes(id)
  }

  function toggleRecord(id: string): void {
    expandedIds.value = isExpanded(id)
      ? expandedIds.value.filter(current => current !== id)
      : [...expandedIds.value, id]
  }

  /* 加载 */

  // 决策对象的名字。后端只存 subject_id，直接印 UUID 对使用者没有意义；
  // 候选集是本页最常见的对象，按项目把「id → 名称」拉一次即可，其余类型退化为短 id。
  const subjectNames = ref<Record<string, string>>({})

  async function loadSubjectNames(): Promise<void> {
    if (!projectId.value) {
      return
    }
    try {
      const response = await listCandidateSets(projectId.value, { page: 1, page_size: 100 })
      const mapping: Record<string, string> = {}
      for (const item of response.data.items) {
        mapping[item.id] = item.name
      }
      subjectNames.value = mapping
    } catch {
      subjectNames.value = {}
    }
  }

  function resolveSubjectText(record: DecisionRecord): string {
    const name = subjectNames.value[record.subject_id]
    if (name) {
      return name
    }
    return record.subject_id ? `${record.subject_id.slice(0, 8)}…` : placeHolder
  }

  async function loadStage(): Promise<void> {
    if (!projectId.value) {
      return
    }
    stageError.value = false
    try {
      const response = await getProjectStage(projectId.value)
      stage.value = response.data
    } catch {
      stageError.value = true
      stage.value = null
    }
  }

  async function loadDecisions(): Promise<void> {
    if (!projectId.value) {
      return
    }

    // 越界参数在 UI 侧也挡一次：后端 `ge=1` / `le=100` 会直接 422。
    page.value = clampDecisionPage(page.value)
    pageSize.value = clampDecisionPageSize(pageSize.value)

    loading.value = true
    loadError.value = false
    try {
      const response = await listProjectDecisions(projectId.value, {
        page: page.value,
        page_size: pageSize.value,
        ...(pointFilter.value ? { decision_point: pointFilter.value } : {})
      })
      records.value = response.data.items
      total.value = response.data.total
    } catch {
      loadError.value = true
      records.value = []
      total.value = 0
    } finally {
      loading.value = false
    }
  }

  function loadAll(): void {
    void loadStage()
    void loadSubjectNames()
    void loadDecisions()
  }

  function handleFilterChange(): void {
    page.value = 1
    void loadDecisions()
  }

  // 改页大小时 antd 会**先** emit `showSizeChange`、**再** emit `change(current, size)`，
  // 两个 handler 并存时第二个 emit 会把 `page = 1` 覆盖回旧页码，并且一次操作打两次请求。
  // 因此只监听 `change`，在同一个 handler 里按「size 变了没」分派。
  function handlePageChange(next: number, size?: number): void {
    if (typeof size === 'number' && size !== pageSize.value) {
      pageSize.value = clampDecisionPageSize(size)
      page.value = 1
    } else {
      page.value = clampDecisionPage(next)
    }
    void loadDecisions()
  }

  /* 新建抽屉 */

  function resetDraft(): void {
    draft.decisionPoint = 'DP3'
    draft.subjectType = 'CANDIDATE_SET'
    draft.subjectId = ''
    draft.reason = ''
    draft.selectedIdsText = ''
    draft.excludedIdsText = ''
    draft.basisTaskIdsText = ''
    draft.basisMetricsText = ''
    submitError.value = ''
  }

  function openDrawer(): void {
    resetDraft()
    createOpen.value = true
  }

  function closeDrawer(): void {
    createOpen.value = false
  }

  async function submitDecision(): Promise<void> {
    const result = buildDecisionCreatePayload({ ...draft })
    if (!result.ok) {
      submitError.value = t(result.errorKey)
      return
    }

    submitError.value = ''
    submitting.value = true
    try {
      await createProjectDecision(projectId.value, result.payload)
      message.success(t('decisions.drawer.submitted'))
      createOpen.value = false
      page.value = 1
      await loadAll()
    } catch (cause) {
      const text = resolveDecisionErrorMessage(cause, t('decisions.errors.createDecision'))
      submitError.value = text
      message.error(text)
    } finally {
      submitting.value = false
    }
  }

  onMounted(() => {
    loadAll()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .decisions-page {
    max-width: @page-max-width;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .back-link {
    display: inline-block;
    margin-bottom: @spacing-lg;
    color: @text-tertiary;
  }

  .decisions-notice,
  .decisions-alert {
    margin-bottom: @spacing-md;
  }

  .decisions-error {
    position: relative;
  }

  .decisions-error__retry {
    position: absolute;
    top: @spacing-lg;
    right: @spacing-lg;
    z-index: 1;
  }

  .decisions-stage {
    padding: @spacing-md @spacing-lg;
    margin-bottom: @spacing-lg;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
  }

  .decisions-stage__head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: @spacing-sm;
  }

  .decisions-stage__label {
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .decisions-stage__name {
    font-weight: @font-weight-semibold;
  }

  .decisions-stage__next {
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .decisions-stage__counters {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-md;
    margin-top: @spacing-sm;
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .decisions-stage__gaps {
    margin-top: @spacing-sm;
  }

  .decisions-stage__gaps-title {
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .decisions-gap {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: @spacing-sm;
    padding: @spacing-xs 0;
  }

  .decisions-gap__message {
    font-size: @font-size-sm;
  }

  .decisions-gap__action {
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .decisions-gap__link {
    color: @primary-color;
    font-size: @font-size-xs;
  }

  .decisions-stage__no-gaps {
    margin: @spacing-sm 0 0;
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .decisions-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    margin-bottom: @spacing-md;
  }

  .decisions-filter {
    width: 220px;
  }

  .decisions-total {
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .decisions-empty__title {
    margin-bottom: @spacing-xs;
    font-size: @font-size-md;
  }

  .decisions-empty__hint {
    max-width: 520px;
    margin: 0 auto @spacing-md;
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .decisions-timeline {
    display: flex;
    flex-direction: column;
    gap: @spacing-xl;
  }

  .decisions-group__head {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    padding-bottom: @spacing-sm;
    border-bottom: 1px solid @border-color;
  }

  .decisions-group__point {
    font-family: @font-family-mono;
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .decisions-group__title {
    margin: 0;
    font-size: @font-size-lg;
  }

  .decisions-group__count {
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .decisions-record {
    padding: @spacing-md 0;
    border-bottom: 1px solid @border-color;
  }

  .decisions-record__meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: @spacing-sm;
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .decisions-record__reason {
    margin: @spacing-sm 0;
    font-size: @font-size-sm;
    line-height: @line-height-base;
    white-space: pre-wrap;
  }

  .decisions-record__detail {
    padding: @spacing-md;
    margin-top: @spacing-sm;
    background: @bg-hover;
    border-radius: @border-radius-md;
  }

  .decisions-detail__title {
    margin: @spacing-md 0 @spacing-xs;
    font-size: @font-size-sm;
    font-weight: @font-weight-semibold;
  }

  .decisions-detail__hint,
  .decisions-detail__empty {
    margin: 0 0 @spacing-sm;
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .decisions-detail__missing-hint {
    margin: @spacing-xs 0 0;
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .decisions-snapshot__candidate {
    font-family: @font-family-mono;
    font-size: @font-size-xs;
  }

  .decisions-snapshot__missing {
    color: @text-tertiary;
    font-style: italic;
  }

  .decisions-detail__tasks {
    margin: 0;
    padding-left: @spacing-lg;
    font-size: @font-size-xs;
  }

  .decisions-detail__task-link {
    color: @primary-color;
  }

  .decisions-detail__metrics-summary {
    color: @text-tertiary;
    font-size: @font-size-xs;
    cursor: pointer;
  }

  .decisions-detail__metrics-body {
    max-height: 240px;
    padding: @spacing-sm;
    overflow: auto;
    font-family: @font-family-mono;
    font-size: @font-size-xs;
    white-space: pre-wrap;
    border-radius: @border-radius-sm;
  }

  .decisions-pagination {
    display: flex;
    justify-content: flex-end;
    margin-top: @spacing-lg;
  }

  .decisions-drawer__error {
    margin: @spacing-sm 0 0;
    color: @error-color;
    font-size: @font-size-xs;
  }

  .decisions-drawer__actions {
    display: flex;
    justify-content: flex-end;
    gap: @spacing-sm;
    margin-top: @spacing-md;
  }
</style>
