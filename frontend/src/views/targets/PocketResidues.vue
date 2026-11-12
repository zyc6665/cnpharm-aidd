<template>
  <main class="pocket-residues-page" data-testid="pocket-residues-page">
    <AppBackLink
      :fallback="backLink"
      :parent-label="t('targets.residues.backToPockets')"
    />

    <AppPageHeader
      :title="t('targets.residues.title')"
      :subtitle="t('targets.residues.subtitle')"
    >
      <template #actions>
        <a-checkbox
          v-model:checked="keyOnly"
          data-testid="residues-key-only"
          @change="load"
        >
          {{ t('targets.residues.keyOnly') }}
        </a-checkbox>
        <a-button :loading="loading" @click="load">{{ t('targets.refresh') }}</a-button>
      </template>
    </AppPageHeader>

    <AppErrorState
      v-if="loadError"
      data-testid="pocket-residues-error"
      code="ERR"
      :title="t('targets.loadFailed')"
      :description="t('targets.loadFailedHint')"
      :action-text="t('targets.residues.backToPockets')"
      :to="backLink"
    />

    <SkeletonList v-else-if="loading && residues.length === 0" :count="6" />

    <template v-else>
      <p v-if="residues.length" class="residue-hint" data-testid="residues-ranking-hint">
        按口袋内评分从高到低排列。
      </p>

      <AppEmptyState
        v-if="residues.length === 0"
        class="residue-empty"
        data-testid="residues-empty"
        :title="t('targets.residues.empty')"
        description="口袋残基是距口袋点 8 Å 内的整份清单；预测完成后会按几何与理化打分排序，标注核心 / 关键 / 外围。"
      />

      <a-table
        :scroll="{ x: 'max-content' }"
        v-else
        class="residue-table"
        data-testid="residues-table"
        :columns="columns"
        :data-source="residues"
        :loading="loading"
        :pagination="false"
        row-key="id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'chain'">
            <span class="residue-mono">{{ formatOptionalText(record.chain) }}</span>
          </template>
          <template v-else-if="column.key === 'residue_seq'">
            <span class="residue-mono">{{ record.residue_seq ?? '-' }}</span>
          </template>
          <template v-else-if="column.key === 'residue_name'">
            <span class="residue-mono">{{ formatOptionalText(record.residue_name) }}</span>
          </template>
          <template v-else-if="column.key === 'tier'">
            <a-tag
              :color="tierTagColor(record.score_tier)"
              :data-testid="record.is_key ? 'residue-key-tag' : 'residue-tier-tag'"
            >
              {{ tierLabel(record.score_tier) }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'contribution'">
            {{ formatResidueContribution(record.contribution) }}
          </template>
        </template>
      </a-table>
    </template>
  </main>
  <ResultDisclaimer />
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AppErrorState from '@/components/common/AppErrorState.vue'
  import AppEmptyState from '@/components/common/AppEmptyState.vue'
  import SkeletonList from '@/components/common/SkeletonList.vue'
  import { getPocket, listPocketResidues } from '@/api/targets'
  import { formatOptionalText, formatResidueContribution } from '@/domain/targets'
  import type { PocketResidue, PocketResidueTier } from '@/types/targets'
  import ResultDisclaimer from '@/components/common/ResultDisclaimer.vue'
  import AppBackLink from '@/components/common/AppBackLink.vue'

  const route = useRoute()
  const { t } = useI18n()

  const pocketId = computed(() => String(route.params.pocketId || ''))
  const residues = ref<PocketResidue[]>([])
  const structureId = ref('')
  const keyOnly = ref(false)
  const loading = ref(false)
  const loadError = ref(false)

  const backLink = computed(() =>
    structureId.value ? `/structures/${structureId.value}/pockets` : '/'
  )

  const columns = computed(() => [
    { title: t('targets.residues.chain'), key: 'chain', width: 90 },
    { title: t('targets.residues.residueSeq'), key: 'residue_seq', width: 120 },
    { title: t('targets.residues.residueName'), key: 'residue_name', width: 120 },
    { title: t('targets.residues.isKey'), key: 'tier', width: 130 },
    { title: t('targets.residues.contribution'), key: 'contribution' }
  ])

  function tierLabel(tier: PocketResidueTier | null | undefined): string {
    if (tier === 'core') return '核心残基'
    if (tier === 'key') return '关键残基'
    if (tier === 'peripheral') return '外围残基'
    return '未评分'
  }

  function tierTagColor(tier: PocketResidueTier | null | undefined): string {
    if (tier === 'core') return 'orange'
    if (tier === 'key') return 'gold'
    return 'default'
  }

  async function loadPocketContext(id: string) {
    try {
      const response = await getPocket(id)
      structureId.value = response.data.structure_id
    } catch {
      structureId.value = ''
    }
  }

  async function load() {
    if (!pocketId.value) {
      return
    }
    loading.value = true
    loadError.value = false
    try {
      const response = await listPocketResidues(pocketId.value, keyOnly.value)
      residues.value = response.data.items
      if (response.data.structure_id) {
        structureId.value = response.data.structure_id
      } else if (!structureId.value) {
        await loadPocketContext(pocketId.value)
      }
    } catch {
      loadError.value = true
      residues.value = []
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    void load()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .pocket-residues-page {
    max-width: @page-max-width;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .back-link {
    display: inline-block;
    margin-bottom: @spacing-lg;
    color: @text-tertiary;

    &:hover {
      color: @accent-color;
    }
  }

  .residue-empty {
    padding: @spacing-xxl 0;
  }

  .residue-hint {
    margin: 0 0 @spacing-sm;
    font-size: 12px;
    line-height: 1.6;
    color: @text-tertiary;
  }

  .residue-mono {
    font-family: @font-family-mono;
  }

  .residue-muted {
    color: @text-tertiary;
  }
</style>
