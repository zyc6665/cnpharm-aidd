<template>
  <main class="structure-pockets-page" data-testid="structure-pockets-page">
    <router-link :to="`/structures/${structureId}`" class="back-link">
      {{ t('targets.pockets.backToStructure') }}
    </router-link>

    <AppPageHeader :title="t('targets.pockets.title')" :subtitle="t('targets.pockets.subtitle')">
      <template #actions>
        <a-button :loading="loading" @click="load">{{ t('targets.refresh') }}</a-button>
      </template>
    </AppPageHeader>

    <AppErrorState
      v-if="loadError"
      data-testid="pockets-error"
      code="ERR"
      :title="t('targets.loadFailed')"
      :description="t('targets.loadFailedHint')"
      :action-text="t('targets.pockets.backToStructure')"
      :to="`/structures/${structureId}`"
    />

    <SkeletonList v-else-if="loading && pockets.length === 0" :count="4" />

    <template v-else>
      <a-alert
        v-if="selectionBroken"
        class="pocket-alert"
        type="warning"
        show-icon
        :message="t('targets.pockets.multipleSelected')"
        data-testid="pockets-multiple-selected"
      />

      <p v-if="selectedPocket" class="pocket-summary" data-testid="pockets-selected-summary">
        {{ t('targets.pockets.selectedBadge') }}：{{ t('targets.pockets.rank') }}
        #{{ selectedPocket.rank ?? '-' }} ·
        {{ t('targets.pockets.score') }} {{ formatPocketScore(selectedPocket.score) }} ·
        {{ t('targets.pockets.center') }} {{ formatPocketCenter(selectedPocket.center) }} ·
        {{ t('targets.pockets.volume') }} {{ formatPocketVolume(selectedPocket.volume) }}
      </p>

      <AppEmptyState
        v-if="pockets.length === 0"
        class="pocket-empty"
        data-testid="pockets-empty"
        :title="t('targets.pockets.empty')"
        :description="t('targets.pockets.emptyHint')"
      />

      <a-table
        :scroll="{ x: 'max-content' }"
        v-else
        class="pocket-table"
        data-testid="pockets-table"
        :columns="columns"
        :data-source="pockets"
        :loading="loading"
        :pagination="false"
        :custom-row="customRow"
        row-key="id"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'rank'">
            <span class="pocket-rank">{{ record.rank ?? '-' }}</span>
          </template>
          <template v-else-if="column.key === 'score'">
            <span class="pocket-score" :class="`tone-${pocketScoreTone(record.score)}`">
              {{ formatPocketScore(record.score) }}
            </span>
          </template>
          <template v-else-if="column.key === 'volume'">
            {{ formatPocketVolume(record.volume) }}
          </template>
          <template v-else-if="column.key === 'center'">
            <span class="pocket-center">{{ formatPocketCenter(record.center) }}</span>
          </template>
          <template v-else-if="column.key === 'residueCount'">
            {{ record.residue_count ?? '-' }}
          </template>
          <template v-else-if="column.key === 'selected'">
            <a-tag v-if="record.selected" color="green">
              {{ t('targets.pockets.selectedBadge') }}
            </a-tag>
            <span v-else class="pocket-not-selected">{{ t('targets.pockets.notSelected') }}</span>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-button
              size="small"
              :type="record.selected ? 'default' : 'primary'"
              :loading="selectingId === record.id"
              data-testid="pocket-select-button"
              @click.stop="handleSelect(record)"
            >
              {{ record.selected ? t('targets.pockets.unselect') : t('targets.pockets.select') }}
            </a-button>
          </template>
        </template>
      </a-table>
    </template>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AppErrorState from '@/components/common/AppErrorState.vue'
  import AppEmptyState from '@/components/common/AppEmptyState.vue'
  import SkeletonList from '@/components/common/SkeletonList.vue'
  import { useStructurePockets } from '@/composables/useStructurePockets'
  import {
    formatPocketCenter,
    formatPocketScore,
    formatPocketVolume,
    pocketScoreTone,
    resolveTargetErrorMessage
  } from '@/domain/targets'
  import type { PocketSummary } from '@/types/targets'

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()

  const structureId = computed(() => String(route.params.structureId || ''))

  // 与「上游接力条」共用同一套口袋列表/选定逻辑。
  const {
    pockets: rawPockets,
    sorted: pockets,
    selected: selectedPocket,
    loading,
    error,
    selectingId,
    load,
    select
  } = useStructurePockets(structureId)

  const loadError = computed(() => Boolean(error.value))
  const selectionBroken = computed(
    () => rawPockets.value.filter((pocket) => pocket.selected).length > 1
  )
  const columns = computed(() => [
    { title: t('targets.pockets.rank'), key: 'rank', width: 80 },
    { title: t('targets.pockets.score'), key: 'score', width: 120 },
    { title: t('targets.pockets.volume'), key: 'volume', width: 120 },
    { title: t('targets.pockets.center'), key: 'center', width: 200 },
    { title: t('targets.pockets.residueCount'), key: 'residueCount', width: 100 },
    { title: t('targets.pockets.selected'), key: 'selected', width: 110 },
    { title: t('targets.actions'), key: 'actions', width: 120 }
  ])

  async function handleSelect(pocket: PocketSummary) {
    await select(pocket.id)
    if (error.value) {
      message.error(resolveTargetErrorMessage(undefined, t('targets.pockets.selectFailed')))
    } else {
      message.success(t('targets.pockets.selectSuccess'))
    }
  }

  function handleRowClick(record: PocketSummary) {
    void router.push({ name: 'PocketResidues', params: { pocketId: record.id } })
  }

  function customRow(record: PocketSummary) {
    return {
      class: 'pocket-row',
      onClick: () => handleRowClick(record)
    }
  }

  onMounted(() => {
    void load()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .structure-pockets-page {
    max-width: 1080px;
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

  .pocket-alert {
    margin-bottom: @spacing-md;
  }

  .pocket-summary {
    margin: 0 0 @spacing-sm;
    color: @text-secondary;
    font-family: @font-family-mono;
    font-size: @font-size-sm;
  }

  .pocket-empty {
    padding: @spacing-xxl 0;
  }

  .empty-hint {
    margin: @spacing-sm 0 0;
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .pocket-table {
    :deep(.pocket-row) {
      cursor: pointer;
    }
  }

  .pocket-rank {
    color: @text-tertiary;
    font-family: @font-family-mono;
  }

  .pocket-score {
    font-family: @font-family-mono;
    font-weight: @font-weight-semibold;

    &.tone-strong {
      color: @success-color;
    }

    &.tone-medium {
      color: @warning-color;
    }

    &.tone-weak {
      color: @text-tertiary;
    }
  }

  .pocket-center {
    font-family: @font-family-mono;
    font-size: @font-size-xs;
  }

  .pocket-not-selected {
    color: @text-tertiary;
  }
</style>
