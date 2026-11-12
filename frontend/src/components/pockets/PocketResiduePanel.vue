<template>
  <div class="residue-panel">
    <div class="section-title">
      关键残基
      <span class="section-hint" data-testid="residues-ranking-hint">
        {{ hint }}
      </span>
    </div>

    <div v-if="keyResidues.length" class="residue-actions">
      <a-button size="small" @click="selectAllKeyResidues">全选关键残基</a-button>
      <a-button size="small" :disabled="!selected.length" @click="clearSelection">
        清空选择
      </a-button>
      <span class="residue-selected-count">
        已选 {{ selected.length }} / {{ keyResidues.length }}
      </span>
    </div>

    <div v-if="keyResidues.length" class="key-residue-list">
      <div
        v-for="(residue, index) in keyResidues"
        :key="residue.id"
        class="key-residue"
        :class="{
          'key-residue--core': residue.score_tier === 'core',
          'key-residue--key': residue.score_tier === 'key',
          'key-residue--active': isSelected(residue.residue_seq)
        }"
        :data-testid="`residue-chip-${residue.residue_seq}`"
        @click="toggleResidue(residue.residue_seq)"
      >
        <span class="kr-rank">{{ index + 1 }}</span>
        <span class="kr-name">{{ residue.residue_name }}{{ residue.residue_seq }}</span>
        <span class="kr-chinese">{{ propertyOf(residue.residue_name).chinese }}</span>
        <a-tag :color="residueCategoryColor(propertyOf(residue.residue_name).category)">
          {{ propertyOf(residue.residue_name).category }}
        </a-tag>
        <span class="kr-score">
          {{ residue.contribution !== null ? residue.contribution.toFixed(2) : '-' }}
        </span>
        <a-tag :color="tierTagColor(residue.score_tier)" data-testid="residue-tier-tag">
          {{ tierLabel(residue.score_tier) }}
        </a-tag>
      </div>
    </div>
    <div v-else class="residue-empty" data-testid="residue-empty">
      {{ emptyText }}
    </div>

    <div v-if="selectedSummary" class="residue-detail" data-testid="residue-selection-detail">
      {{ selectedSummary }}
    </div>

    <div class="section-title all-residues-title">
      全部残基
      <span class="section-hint">完整清单（{{ allResidueRows.length }}），此处不列分数</span>
    </div>
    <a-table
      size="small"
      class="all-residues-table"
      :columns="allResidueColumns"
      :data-source="allResidueRows"
      :pagination="{ pageSize: 10, size: 'small', showSizeChanger: false }"
      :row-class-name="allResidueRowClass"
      :custom-row="allResidueRowEvents"
      data-testid="all-residues-table"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'residue'">
          <span class="mono">{{ record.residue_name }}{{ record.residue_seq }}</span>
        </template>
        <template v-else-if="column.key === 'category'">
          <a-tag :color="residueCategoryColor(record.category)">{{ record.category }}</a-tag>
        </template>
        <template v-else-if="column.key === 'tier'">
          <a-tag :color="tierTagColor(record.tier)">{{ tierLabel(record.tier) }}</a-tag>
        </template>
      </template>
    </a-table>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import {
    residueCategoryColor,
    residuePropertyOf
  } from '@/domain/targets/residue-property'
  import { tierLabel, tierTagColor } from '@/domain/targets/residue-tier'
  import type { PocketResidue, PocketResidueTier } from '@/types/targets'

  /**
   * 口袋残基面板：关键残基按分数排序在上，完整清单在下，多选状态由父组件持有
   * （3D 视图要用同一份选择）。成果页与任务结果页共用这一个组件，
   * 免得两个页面各写一套排序/分级口径（docs/17 §5.54）。
   */
  const props = withDefaults(
    defineProps<{
      residues: PocketResidue[]
      selected: number[]
      hint?: string
      emptyText?: string
    }>(),
    {
      hint: '按口袋内评分从高到低 · 点击可在 3D 中多选高亮',
      emptyText: '该口袋暂未存储残基注释数据，仍可在 3D 中查看整个蛋白结构。'
    }
  )

  const emit = defineEmits<{ 'update:selected': [value: number[]] }>()

  const rankedResidues = computed(() => {
    const rank = (value: number | null | undefined) =>
      typeof value === 'number' ? value : -1
    return [...props.residues].sort((left, right) => {
      const delta = rank(right.contribution) - rank(left.contribution)
      if (delta !== 0) return delta
      return (left.residue_seq ?? 0) - (right.residue_seq ?? 0)
    })
  })

  const keyResidues = computed(() =>
    rankedResidues.value.filter(
      (residue) => residue.score_tier === 'core' || residue.score_tier === 'key'
    )
  )

  const allResidueRows = computed(() =>
    rankedResidues.value.map((residue, index) => {
      const property = residuePropertyOf(residue.residue_name)
      return {
        key: residue.id ?? `${residue.residue_seq}-${index}`,
        residue_seq: residue.residue_seq,
        residue_name: residue.residue_name,
        chain: residue.chain,
        chinese: property.chinese,
        category: property.category,
        hydropathy: property.hydropathy,
        tier: residue.score_tier ?? null
      }
    })
  )

  const allResidueColumns = [
    { title: '残基', key: 'residue', width: 96 },
    { title: '中文名', dataIndex: 'chinese', key: 'chinese', width: 96 },
    { title: '类别', key: 'category', width: 84 },
    { title: '疏水指数', dataIndex: 'hydropathy', key: 'hydropathy', width: 90 },
    { title: '分级', key: 'tier', width: 90 }
  ]

  function propertyOf(name: string | null | undefined) {
    return residuePropertyOf(name)
  }

  function isSelected(seq: number | null | undefined): boolean {
    return typeof seq === 'number' && props.selected.includes(seq)
  }

  function allResidueRowClass(record: { residue_seq: number | null }): string {
    return isSelected(record.residue_seq) ? 'all-residues-row--active' : ''
  }

  function allResidueRowEvents(record: { residue_seq: number | null }) {
    return { onClick: () => toggleResidue(record.residue_seq) }
  }

  function toggleResidue(seq: number | null | undefined) {
    if (typeof seq !== 'number') return
    emit(
      'update:selected',
      props.selected.includes(seq)
        ? props.selected.filter((item) => item !== seq)
        : [...props.selected, seq]
    )
  }

  function selectAllKeyResidues() {
    emit(
      'update:selected',
      keyResidues.value
        .map((residue) => residue.residue_seq)
        .filter((seq): seq is number => typeof seq === 'number')
    )
  }

  function clearSelection() {
    emit('update:selected', [])
  }

  /** 选中集的一句话摘要：选 1 个给细节，选多个给清单。 */
  const selectedSummary = computed(() => {
    if (!props.selected.length) return ''
    const picked = rankedResidues.value.filter(
      (residue) => residue.residue_seq != null && props.selected.includes(residue.residue_seq)
    )
    if (!picked.length) return ''
    if (picked.length === 1) {
      const residue = picked[0]
      if (!residue) return ''
      const property = residuePropertyOf(residue.residue_name)
      return [
        `${residue.residue_name}${residue.residue_seq}`,
        property.chinese,
        `${property.category}性`,
        `疏水指数 ${property.hydropathy.toFixed(1)}`,
        `链 ${residue.chain || '-'}`,
        tierLabel(residue.score_tier as PocketResidueTier | null | undefined),
        `评分 ${residue.contribution !== null ? residue.contribution.toFixed(2) : '-'}`
      ].join(' · ')
    }
    return `已选 ${picked.length} 个残基：${picked
      .map((residue) => `${residue.residue_name}${residue.residue_seq}`)
      .join('、')}`
  })
</script>

<style scoped lang="less">
  .section-title {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin-bottom: 10px;
    font-size: 13px;
    font-weight: 600;
    color: var(--color-text-primary);
  }

  .section-hint {
    font-size: 12px;
    font-weight: 400;
    color: var(--color-text-tertiary);
  }

  .residue-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
  }

  .residue-selected-count {
    font-size: 12px;
    color: var(--color-text-tertiary);
    font-variant-numeric: tabular-nums;
  }

  .key-residue-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-height: 420px;
    overflow-y: auto;
    padding-right: 4px;
  }

  .key-residue {
    display: grid;
    grid-template-columns: 28px minmax(72px, auto) minmax(64px, auto) auto minmax(48px, auto) auto;
    align-items: center;
    gap: 10px;
    padding: 5px 10px;
    border: 1px solid transparent;
    border-radius: 8px;
    background: var(--color-bg-layout);
    font-size: 12px;
    cursor: pointer;
    transition: border-color 0.15s ease, background 0.15s ease;
  }

  .key-residue:hover {
    border-color: var(--color-border-secondary);
  }

  .key-residue--core .kr-name {
    color: #cf1322;
    font-weight: 600;
  }

  .key-residue--key .kr-name {
    color: #ad6800;
    font-weight: 600;
  }

  .key-residue--active {
    border-color: #22d3ee;
    background: rgba(34, 211, 238, 0.14);
  }

  .kr-rank {
    color: var(--color-text-tertiary);
    font-variant-numeric: tabular-nums;
  }

  .kr-name {
    font-family: 'JetBrains Mono', Consolas, monospace;
  }

  .kr-chinese {
    color: var(--color-text-secondary);
  }

  .kr-score {
    text-align: right;
    font-variant-numeric: tabular-nums;
    color: var(--color-text-secondary);
  }

  .residue-empty {
    padding: 10px 12px;
    border: 1px dashed var(--color-border-secondary);
    border-radius: 8px;
    font-size: 12px;
    color: var(--color-text-tertiary);
  }

  .residue-detail {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px dashed var(--color-border-secondary);
    font-size: 12px;
    color: var(--color-text-secondary);
  }

  .all-residues-title {
    margin-top: 18px;
  }

  .all-residues-table :deep(tr.all-residues-row--active > td) {
    background: rgba(34, 211, 238, 0.1);
  }

  .mono {
    font-family: 'JetBrains Mono', Consolas, monospace;
  }
</style>
