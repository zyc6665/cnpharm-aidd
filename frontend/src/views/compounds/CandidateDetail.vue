<template>
  <main class="candidate-detail-page">
    <AppPageHeader :title="candidateTitle" :subtitle="t('candidates.subtitle')">
      <template #actions>
        <a-space>
          <a-button :loading="loading" data-testid="candidate-refresh" @click="loadCandidate">
            {{ t('common.refresh') }}
          </a-button>
          <router-link v-if="candidate?.project_id" :to="`/projects/${candidate.project_id}/assets`">
            <a-button data-testid="candidate-back-assets">{{ t('compounds.backToAssets') }}</a-button>
          </router-link>
        </a-space>
      </template>
    </AppPageHeader>

    <a-alert
      v-if="loadError"
      class="candidate-alert"
      type="error"
      show-icon
      data-testid="candidate-error"
      :message="t('candidates.errors.load')"
    >
      <template #action>
        <a-button size="small" @click="loadCandidate">{{ t('common.refresh') }}</a-button>
      </template>
    </a-alert>

    <SkeletonDetail v-if="loading && !candidate" />

    <template v-else-if="candidate">
      <a-descriptions bordered :column="2" size="small" data-testid="candidate-facts">
        <a-descriptions-item :label="t('candidates.fields.name')">
          {{ candidate.name || '-' }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('candidates.fields.code')">
          {{ candidate.code || '-' }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('candidates.fields.type')">
          <a-tag data-testid="candidate-location-tag">{{ t(candidateLocationLabel(candidate)) }}</a-tag>
        </a-descriptions-item>
        <a-descriptions-item :label="t('candidates.fields.source')">
          {{ t(`candidates.source.${candidate.source}`) }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('candidates.fields.designScore')">
          {{ candidate.design_score ?? '-' }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('candidates.fields.createdAt')">
          {{ formatDateTimeOrDash(candidate.created_at) }}
        </a-descriptions-item>
      </a-descriptions>

      <!-- 小分子：compound 内联信息 -->
      <section v-if="candidate.compound" class="candidate-section">
        <h3 class="section-title">{{ t('candidates.detail.compoundInfo') }}</h3>
        <a-row :gutter="24">
          <a-col :xs="24" :md="8">
            <div class="structure-panel" data-testid="candidate-structure">
              <Smiles2DCell
                v-if="candidate.compound.canonical_smiles"
                :smiles="candidate.compound.canonical_smiles"
                block
              />
            </div>
          </a-col>
          <a-col :xs="24" :md="16">
            <a-descriptions bordered :column="2" size="small">
              <a-descriptions-item :label="t('compounds.columns.name')">
                <router-link :to="compoundRoute(candidate.compound.id)">
                  {{ candidate.compound.name || candidate.compound.inchikey }}
                </router-link>
              </a-descriptions-item>
              <a-descriptions-item :label="t('compounds.columns.inchikey')">
                <span class="mono-cell">{{ candidate.compound.inchikey }}</span>
              </a-descriptions-item>
              <a-descriptions-item :label="t('compounds.columns.formula')">
                {{ candidate.compound.mol_formula || '-' }}
              </a-descriptions-item>
              <a-descriptions-item :label="t('compounds.columns.molWeight')">
                {{ formatPropertyValue('mol_weight', candidate.compound.mol_weight) }}
              </a-descriptions-item>
              <a-descriptions-item :label="t('compounds.columns.smiles')" :span="2">
                <span class="mono-cell">{{ candidate.compound.canonical_smiles }}</span>
              </a-descriptions-item>
            </a-descriptions>
          </a-col>
        </a-row>

        <h3 class="section-title">{{ t('candidates.detail.properties') }}</h3>
        <a-table
          :scroll="{ x: 'max-content' }"
          :columns="propertyColumns"
          :data-source="propertyRows"
          :pagination="false"
          row-key="key"
          size="small"
          data-testid="candidate-property-table"
        />
      </section>

      <!-- 多肽：只有序列 -->
      <section v-else class="candidate-section">
        <h3 class="section-title">{{ t('candidates.fields.sequence') }}</h3>
        <p v-if="candidate.peptide_sequence" class="peptide-sequence" data-testid="candidate-peptide-sequence">
          {{ candidate.peptide_sequence }}
        </p>
        <p v-else class="section-empty">{{ t('candidates.detail.noStructure') }}</p>
      </section>

      <section v-if="attrSections.length" class="candidate-section">
        <h3 class="section-title">{{ t('candidates.detail.attrs') }}</h3>
        <p class="section-subtitle">{{ t('candidates.detail.attrsHint') }}</p>
        <AppDescriptionList :sections="attrSections" :columns="2" test-id="candidate-attrs" />
      </section>

      <section class="candidate-section">
        <h3 class="section-title">{{ t('candidates.detail.relatedTask') }}</h3>
        <div v-if="candidate.task_id" class="related-links" data-testid="candidate-related-task">
          <router-link :to="`/tasks/${candidate.task_id}`" class="related-link">
            {{ candidate.task_id }}
          </router-link>
          <router-link :to="resultRoute(candidate.task_id)" class="related-link">
            {{ t('candidates.detail.relatedResult') }}
          </router-link>
        </div>
        <p v-else class="section-empty" data-testid="candidate-no-task">
          {{ t('candidates.detail.noRelatedTask') }}
        </p>
      </section>

      <!--
        候选物相关结果：后端按「产出它的任务」+「为它提交的任务」取并集。
        只放一个 task_id 链接时，用户看不出跑过几次、结果成没成功。
      -->
      <section class="candidate-section">
        <h3 class="section-title">{{ t('candidates.detail.relatedResults') }}</h3>
        <a-table
          v-if="resultRows.length"
          :scroll="{ x: 'max-content' }"
          :columns="resultColumns"
          :data-source="resultRows"
          :pagination="false"
          row-key="task_id"
          size="small"
          data-testid="candidate-result-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <router-link :to="resultRoute(record.task_id)" class="related-link">
                {{ record.name || record.task_id }}
              </router-link>
            </template>
            <template v-else-if="column.key === 'status'">
              <a-tag>{{ t(`tasks.status.${record.status}`) }}</a-tag>
            </template>
            <template v-else-if="column.key === 'finished_at'">
              {{ formatDateTimeOrDash(record.finished_at) }}
            </template>
          </template>
        </a-table>
        <p v-else class="section-empty" data-testid="candidate-no-results">
          {{ t('candidates.detail.noRelatedResults') }}
        </p>
      </section>
    </template>

    <p v-else class="section-empty" data-testid="candidate-not-found">
      {{ t('candidates.errors.load') }}
    </p>
  </main>
  <ResultDisclaimer />
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import AppDescriptionList from '@/components/common/AppDescriptionList.vue'
  import Smiles2DCell from '@/components/tasks/Smiles2DCell.vue'
  import { getCandidate } from '@/api/compounds'
  import { listCandidateResults } from '@/api/results'
  import {
    PROPERTY_COLUMNS,
    candidateLocationLabel,
    formatPropertyValue,
    readPropertyValue
  } from '@/domain/compounds'
  import type { Candidate, ProjectResultSummary } from '@/types/compounds'
  import { formatNullable, humanizeKey, formatDateTimeOrDash } from '@/domain/common/format'
  import ResultDisclaimer from '@/components/common/ResultDisclaimer.vue'

  const route = useRoute()
  const { t } = useI18n()

  const candidateId = computed(() => String(route.params.candidateId || ''))

  /**
   * 化合物详情页拿不到所属项目，跳转时必须带上候选物的 `project_id`，
   * 否则 P-13 的「返回数据资产」会退化成死链。
   */
  function compoundRoute(compoundId: string): string {
    const projectId = candidate.value?.project_id
    const base = `/compounds/${encodeURIComponent(compoundId)}`
    return projectId ? `${base}?project_id=${encodeURIComponent(projectId)}` : base
  }

  function resultRoute(taskId: string): string {
    return `/results/${encodeURIComponent(taskId)}`
  }

  const loading = ref(false)
  const loadError = ref(false)
  const candidate = ref<Candidate | null>(null)

  /**
   * 相关结果单独加载：结果列表失败不该让整页变成错误态——候选物本身、结构、
   * 性质都还是可用的，只是暂时看不到它在哪些任务里出现过。
   */
  const resultRows = ref<ProjectResultSummary[]>([])

  const resultColumns = computed(() => [
    { title: t('candidates.resultColumns.name'), dataIndex: 'name', key: 'name' },
    { title: t('candidates.resultColumns.tool'), dataIndex: 'tool_name', key: 'tool' },
    { title: t('candidates.resultColumns.status'), dataIndex: 'status', key: 'status', width: 110 },
    {
      title: t('candidates.resultColumns.finishedAt'),
      dataIndex: 'finished_at',
      key: 'finished_at',
      width: 180
    }
  ])

  async function loadResults(): Promise<void> {
    if (!candidateId.value) return
    try {
      const response = await listCandidateResults(candidateId.value, { page: 1, page_size: 50 })
      resultRows.value = response.data.items ?? []
    } catch {
      resultRows.value = []
    }
  }

  /**
   * 候选物附加属性：键名随生成工具不同而不同，因此不做白名单、不隐藏未识别键，
   * 只做下划线转空格兜底。空值直接不出现，避免右侧一列「-」占满视线。
   */
  const attrSections = computed(() => {
    const attrs = candidate.value?.attrs ?? {}
    const entries = Object.entries(attrs).filter(
      ([, value]) => value !== null && value !== undefined && value !== '',
    )
    if (!entries.length) {
      return []
    }
    return [
      {
        key: 'attrs',
        fields: entries.map(([key, value]) => ({
          key,
          label: humanizeKey(key),
          value: formatNullable(value, {
            yes: t('tasks.parameters.yes'),
            no: t('tasks.parameters.no'),
          }),
          mono: typeof value === 'string' && /^[A-Za-z0-9_\-:.@]{16,}$/.test(value),
        })),
      },
    ]
  })

  const candidateTitle = computed(() => {
    const current = candidate.value
    if (!current) {
      return t('candidates.detail.title')
    }
    return current.name || current.code || t('candidates.detail.title')
  })

  const propertyColumns = computed(() => [
    { title: t('compounds.properties.column'), dataIndex: 'label', key: 'label', width: 200 },
    { title: t('compounds.properties.value'), dataIndex: 'value', key: 'value' }
  ])

  const propertyRows = computed(() => {
    const current = candidate.value
    return PROPERTY_COLUMNS.map(column => ({
      key: column.key,
      label: t(column.labelKey),
      value: formatPropertyValue(
        column.key,
        current ? readPropertyValue(current, column.key) : null
      )
    }))
  })

  async function loadCandidate(): Promise<void> {
    if (!candidateId.value) return

    loading.value = true
    loadError.value = false
    try {
      const response = await getCandidate(candidateId.value)
      candidate.value = response.data
    } catch {
      loadError.value = true
      candidate.value = null
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    void loadCandidate()
    void loadResults()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .candidate-detail-page {
    max-width: 1240px;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .candidate-alert {
    margin-bottom: @spacing-lg;
  }

  .candidate-section {
    margin-top: @spacing-xl;
  }

  .section-title {
    margin: 0 0 @spacing-md;
    color: @text-primary;
    font-size: @font-size-lg;
  }

  .section-empty {
    padding: @spacing-lg;
    color: @text-tertiary;
    text-align: center;
    background: @bg-surface;
    border: 1px dashed @border-color;
    border-radius: @border-radius-md;
  }

  .structure-panel {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 180px;
    padding: @spacing-md;
    background: @bg-elevated;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
  }

  .peptide-sequence {
    padding: @spacing-md;
    color: @text-primary;
    font-family: @font-family-mono;
    word-break: break-all;
    background: @bg-elevated;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
  }

  .related-links {
    display: flex;
    gap: @spacing-md;
  }

  .related-link {
    color: @primary-color;
  }

  .mono-cell {
    font-family: @font-family-mono;
    font-size: @font-size-xs;
    word-break: break-all;
  }
</style>
