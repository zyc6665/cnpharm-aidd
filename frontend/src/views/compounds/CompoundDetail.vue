<template>
  <main class="compound-detail-page">
    <AppPageHeader :title="compoundTitle" :subtitle="t('compounds.detail.subtitle')">
      <template #actions>
        <a-space>
          <a-button :loading="loading" data-testid="compound-refresh" @click="loadCompound">
            {{ t('common.refresh') }}
          </a-button>
          <router-link v-if="compound?.id && projectId" :to="`/projects/${projectId}/assets`">
            <a-button data-testid="compound-back-assets">{{ t('compounds.backToAssets') }}</a-button>
          </router-link>
        </a-space>
      </template>
    </AppPageHeader>

    <a-alert
      v-if="loadError"
      class="compound-alert"
      type="error"
      show-icon
      data-testid="compound-error"
      :message="t('compounds.errors.loadCompound')"
    >
      <template #action>
        <a-button size="small" @click="loadCompound">{{ t('common.refresh') }}</a-button>
      </template>
    </a-alert>

    <SkeletonDetail v-if="loading && !compound" />

    <template v-else-if="compound">
      <a-row :gutter="24" class="compound-summary">
        <a-col :xs="24" :md="8">
          <div class="structure-panel" data-testid="compound-structure">
            <Smiles2DCell v-if="compound.canonical_smiles" :smiles="compound.canonical_smiles" block />
            <p v-else class="structure-empty">{{ t('compounds.detail.noStructure') }}</p>
          </div>
        </a-col>
        <a-col :xs="24" :md="16">
          <a-descriptions bordered :column="2" size="small" data-testid="compound-facts">
            <a-descriptions-item :label="t('compounds.columns.name')">
              {{ compound.name || '-' }}
            </a-descriptions-item>
            <a-descriptions-item :label="t('compounds.columns.inchikey')">
              <span class="mono-cell" data-testid="compound-inchikey">{{ compound.inchikey }}</span>
            </a-descriptions-item>
            <a-descriptions-item :label="t('compounds.columns.formula')">
              {{ compound.mol_formula || '-' }}
            </a-descriptions-item>
            <a-descriptions-item :label="t('compounds.columns.molWeight')">
              {{ formatPropertyValue('mol_weight', compound.mol_weight) }}
            </a-descriptions-item>
            <a-descriptions-item :label="t('compounds.columns.smiles')" :span="2">
              <span class="mono-cell" data-testid="compound-smiles">
                {{ compound.canonical_smiles }}
              </span>
            </a-descriptions-item>
            <a-descriptions-item :label="t('compounds.columns.createdAt')" :span="2">
              {{ formatDate(compound.created_at) }}
            </a-descriptions-item>
          </a-descriptions>
        </a-col>
      </a-row>

      <section class="compound-section">
        <h3 class="section-title">{{ t('compounds.properties.title') }}</h3>
        <a-table
          :scroll="{ x: 'max-content' }"
          :columns="propertyColumns"
          :data-source="propertyRows"
          :pagination="false"
          row-key="key"
          size="small"
          data-testid="compound-property-table"
        />
      </section>

      <section class="compound-section">
        <div class="section-header">
          <div>
            <h3 class="section-title">{{ t('compounds.similarity.title') }}</h3>
            <p class="section-subtitle">{{ t('compounds.similarity.subtitle') }}</p>
          </div>
        </div>

        <a-form layout="inline" class="similarity-form">
          <a-form-item :label="t('compounds.similarity.querySmiles')">
            <a-input
              v-model:value="similarityQuery"
              class="similarity-query"
              allow-clear
              data-testid="compound-similarity-query"
              :placeholder="t('compounds.similarity.hint')"
            />
          </a-form-item>
          <a-form-item :label="t('compounds.similarity.threshold')">
            <a-input-number
              v-model:value="similarityThreshold"
              :min="0"
              :max="1"
              :step="0.05"
              data-testid="compound-similarity-threshold"
            />
          </a-form-item>
          <a-form-item>
            <a-button
              type="primary"
              :loading="searching"
              data-testid="compound-similarity-submit"
              @click="runSimilaritySearch"
            >
              {{ t('compounds.similarity.submit') }}
            </a-button>
          </a-form-item>
        </a-form>

        <a-alert
          v-if="similarityError"
          class="compound-alert"
          type="error"
          show-icon
          data-testid="compound-similarity-error"
          :message="t('compounds.errors.searchSimilar')"
        />

        <a-spin :spinning="searching">
          <a-table
            :scroll="{ x: 'max-content' }"
            v-if="similarityHits.length > 0"
            :columns="similarityColumns"
            :data-source="similarityHits"
            :pagination="false"
            row-key="compound.id"
            size="small"
            data-testid="compound-similarity-table"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'name'">
                <router-link :to="compoundRoute(record.compound.id)">
                  {{ record.compound.name || record.compound.inchikey }}
                </router-link>
              </template>
              <template v-else-if="column.key === 'inchikey'">
                <span class="mono-cell">{{ record.compound.inchikey }}</span>
              </template>
              <template v-else-if="column.key === 'mol_formula'">
                {{ record.compound.mol_formula || '-' }}
              </template>
              <template v-else-if="column.key === 'mol_weight'">
                {{ formatPropertyValue('mol_weight', record.compound.mol_weight) }}
              </template>
              <template v-else-if="column.key === 'similarity'">
                <span class="similarity-value" data-testid="compound-similarity-value">
                  {{ formatSimilarity(record.similarity) }}
                </span>
              </template>
            </template>
          </a-table>
          <p
            v-else-if="similaritySearched && !similarityError"
            class="section-empty"
            data-testid="compound-similarity-empty"
          >
            {{ t('compounds.similarity.empty') }}
          </p>
        </a-spin>
      </section>
    </template>

    <p v-else class="section-empty" data-testid="compound-not-found">
      {{ t('compounds.errors.loadCompound') }}
    </p>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import { formatDateTimeMinutes } from '@/utils/datetime'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import Smiles2DCell from '@/components/tasks/Smiles2DCell.vue'
  import { getCompound, searchCompounds } from '@/api/compounds'
  import { PROPERTY_COLUMNS, formatPropertyValue, type PropertyKey } from '@/domain/compounds'
  import type { Compound, CompoundSimilarityHit } from '@/types/compounds'

  const route = useRoute()
  const { t } = useI18n()

  const compoundId = computed(() => String(route.params.compoundId || ''))

  /**
   * 化合物本身不带 `project_id`，所属项目只能由入口链接的 query 传入
   * （Assets/CandidateDetail/相似性表格跳转均带 `project_id`）。
   * 取不到时「返回数据资产」按钮不渲染，避免生成 `/projects//assets` 死链。
   */
  const projectId = computed(() => String(route.query.project_id || ''))

  const loading = ref(false)
  const loadError = ref(false)
  const compound = ref<Compound | null>(null)

  const searching = ref(false)
  const similarityError = ref(false)
  const similaritySearched = ref(false)
  const similarityQuery = ref('')
  const similarityThreshold = ref(0)
  const similarityHits = ref<CompoundSimilarityHit[]>([])

  const compoundTitle = computed(() => compound.value?.name || t('compounds.detail.title'))

  const propertyColumns = computed(() => [
    { title: t('compounds.properties.column'), dataIndex: 'label', key: 'label', width: 200 },
    { title: t('compounds.properties.value'), dataIndex: 'value', key: 'value' }
  ])

  const propertyRows = computed(() => {
    const current = compound.value
    return PROPERTY_COLUMNS.map(column => ({
      key: column.key,
      label: t(column.labelKey),
      value: formatPropertyValue(column.key, readValue(current, column.key))
    }))
  })

  const similarityColumns = computed(() => [
    { title: t('compounds.columns.name'), key: 'name', width: 220 },
    { title: t('compounds.columns.inchikey'), key: 'inchikey', width: 200 },
    { title: t('compounds.columns.formula'), key: 'mol_formula', width: 120 },
    { title: t('compounds.columns.molWeight'), key: 'mol_weight', width: 110 },
    { title: t('compounds.similarity.similarity'), key: 'similarity', width: 120 }
  ])

  /** Tanimoto 相似度固定三位小数（docs/06 P-13）。 */
  function formatSimilarity(value: number | null | undefined): string {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return '-'
    }
    return value.toFixed(3)
  }

  /**
   * 化合物详情路由必须带上 `project_id`，否则目标页拿不到所属项目、
   * 「返回数据资产」无法生成（见 docs/06 P-13）。
   */
  function compoundRoute(id: string): string {
    const base = `/compounds/${encodeURIComponent(id)}`
    return projectId.value ? `${base}?project_id=${encodeURIComponent(projectId.value)}` : base
  }

  function readValue(source: Compound | null, key: PropertyKey): number | null {
    if (!source) {
      return null
    }
    if (key === 'mol_weight') {
      return source.mol_weight
    }
    const value = source.props?.[key]
    return typeof value === 'number' ? value : null
  }

  function formatDate(value: string | null | undefined): string {
    return value ? formatDateTimeMinutes(value) : '-'
  }

  async function loadCompound(): Promise<void> {
    if (!compoundId.value) return

    loading.value = true
    loadError.value = false
    try {
      const response = await getCompound(compoundId.value)
      compound.value = response.data
      if (!similarityQuery.value) {
        similarityQuery.value = response.data.canonical_smiles ?? ''
      }
    } catch {
      loadError.value = true
      compound.value = null
    } finally {
      loading.value = false
    }
  }

  async function runSimilaritySearch(): Promise<void> {
    const smiles = similarityQuery.value.trim()
    if (!smiles) {
      message.warning(t('compounds.similarity.queryRequired'))
      return
    }

    searching.value = true
    similarityError.value = false
    try {
      const response = await searchCompounds(
        { smiles },
        { limit: 20, threshold: similarityThreshold.value }
      )
      similarityHits.value = [...response.data.items]
        .sort((left, right) => right.similarity - left.similarity)
      similaritySearched.value = true
    } catch {
      similarityError.value = true
      similarityHits.value = []
    } finally {
      searching.value = false
    }
  }

  onMounted(() => {
    void loadCompound()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .compound-detail-page {
    max-width: 1240px;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .compound-alert {
    margin-bottom: @spacing-lg;
  }

  .compound-summary {
    margin-bottom: @spacing-xl;
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

  .structure-empty {
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .compound-section {
    margin-bottom: @spacing-xl;
  }

  .section-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
  }

  .section-title {
    margin: 0 0 @spacing-sm;
    color: @text-primary;
    font-size: @font-size-lg;
  }

  .section-subtitle {
    margin: 0 0 @spacing-md;
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .section-empty {
    padding: @spacing-lg;
    color: @text-tertiary;
    text-align: center;
    background: @bg-surface;
    border: 1px dashed @border-color;
    border-radius: @border-radius-md;
  }

  .similarity-form {
    margin-bottom: @spacing-md;
  }

  .similarity-query {
    width: 320px;
  }

  .similarity-value {
    color: @success-color;
    font-family: @font-family-mono;
  }

  .mono-cell {
    font-family: @font-family-mono;
    font-size: @font-size-xs;
    word-break: break-all;
  }
</style>
