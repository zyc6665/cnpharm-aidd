<template>
  <main class="pocket-residues-page" data-testid="pocket-residues-page">
    <router-link :to="backLink" class="back-link">
      {{ t('targets.residues.backToPockets') }}
    </router-link>

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
      <AppEmptyState
        v-if="residues.length === 0"
        class="residue-empty"
        data-testid="residues-empty"
        :title="t('targets.residues.empty')"
        description="口袋残基来自口袋预测的输出，预测完成后会按贡献度标注关键残基。"
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
          <template v-else-if="column.key === 'is_key'">
            <a-tag v-if="record.is_key" color="blue" data-testid="residue-key-tag">
              {{ t('targets.residues.isKey') }}
            </a-tag>
            <span v-else class="residue-muted">-</span>
          </template>
          <template v-else-if="column.key === 'contribution'">
            {{ formatResidueContribution(record.contribution) }}
          </template>
        </template>
      </a-table>
    </template>
  </main>
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
  import type { PocketResidue } from '@/types/targets'

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
    { title: t('targets.residues.isKey'), key: 'is_key', width: 130 },
    { title: t('targets.residues.contribution'), key: 'contribution' }
  ])

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
    max-width: 860px;
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

  .residue-mono {
    font-family: @font-family-mono;
  }

  .residue-muted {
    color: @text-tertiary;
  }
</style>
