<template>
  <section
    v-if="chains.length"
    class="sequence-bar"
    :class="[`sequence-bar--${theme}`]"
    data-testid="viewer-sequence-bar"
    :aria-label="t('tasks.visualizationSequenceTitle')"
  >
    <header class="sequence-bar__header">
      <div class="sequence-bar__chains" role="tablist" :aria-label="t('tasks.visualizationChain')">
        <button
          v-for="chain in chains"
          :key="chain.chain"
          type="button"
          role="tab"
          class="sequence-chain-tab"
          :class="{ 'is-active': activeChain === chain.chain }"
          :aria-selected="activeChain === chain.chain"
          data-testid="sequence-chain-tab"
          @click="activeChain = chain.chain"
        >
          <span>{{ t('tasks.visualizationChain') }} {{ chain.chain }}</span>
          <span class="sequence-chain-tab__count">{{ chain.residues.length }}</span>
        </button>
      </div>

      <div class="sequence-bar__meta">
        <span v-if="selectedKeys.length" class="sequence-bar__selection-badge" data-testid="sequence-selected-count">
          {{ t('tasks.visualizationSelectedResidues', { count: selectedKeys.length }) }}
          <span v-if="selectionPreview" class="sequence-bar__selection-preview">({{ selectionPreview }})</span>
        </span>
        <span v-else class="sequence-bar__hint">{{ t('tasks.visualizationSequenceHint') }}</span>
      </div>

      <div class="sequence-bar__actions">
        <button
          type="button"
          class="sequence-action-btn"
          :disabled="!selectedKeys.length"
          data-testid="sequence-focus-btn"
          @click="$emit('focus-selection')"
        >
          {{ t('tasks.visualizationFocusSelection') }}
        </button>
        <button
          type="button"
          class="sequence-action-btn"
          :disabled="!selectedKeys.length"
          data-testid="sequence-clear-btn"
          @click="$emit('clear-selection')"
        >
          {{ t('tasks.visualizationClearSelection') }}
        </button>
        <button
          type="button"
          class="sequence-action-btn"
          data-testid="sequence-close-btn"
          @click="$emit('close')"
        >
          {{ t('tasks.visualizationHideSequence') }}
        </button>
      </div>
    </header>

    <div class="sequence-bar__track" data-testid="sequence-residue-track">
      <div
        v-for="(res, index) in activeResidues"
        :key="res.key"
        class="sequence-cell"
      >
        <span class="sequence-cell__tick">
          {{ shouldShowSequenceRulerTick(index, res.seqId, activeResidues.length) ? res.seqId : '' }}
        </span>
        <button
          type="button"
          class="sequence-cell__btn"
          :class="{ 'is-selected': selectedSet.has(res.key) }"
          :title="`${res.chain}:${res.compId} ${res.seqId}`"
          :aria-pressed="selectedSet.has(res.key)"
          :data-residue-key="res.key"
          data-testid="sequence-residue-btn"
          @click="handleResidueClick($event, res)"
        >
          {{ res.oneLetter }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  shouldShowSequenceRulerTick,
  type MolstarBackground,
  type SequenceChain,
  type SequenceResidue,
} from '@/domain/tasks'

const props = withDefaults(
  defineProps<{
    chains: SequenceChain[]
    selectedKeys: string[]
    theme?: MolstarBackground
  }>(),
  {
    theme: 'dark',
  },
)

const emit = defineEmits<{
  (event: 'toggle-residue', payload: { chain: string; seqId: number; shiftKey: boolean }): void
  (event: 'focus-selection'): void
  (event: 'clear-selection'): void
  (event: 'close'): void
}>()

const { t } = useI18n()
const activeChain = ref<string>('')

watch(
  () => props.chains,
  chains => {
    if (!chains.length) {
      activeChain.value = ''
      return
    }
    if (!chains.some(item => item.chain === activeChain.value)) {
      activeChain.value = chains[0]!.chain
    }
  },
  { immediate: true },
)

const activeResidues = computed<SequenceResidue[]>(() => {
  const match = props.chains.find(item => item.chain === activeChain.value) ?? props.chains[0]
  return match?.residues ?? []
})

const selectedSet = computed(() => new Set(props.selectedKeys))

const selectionPreview = computed(() => {
  if (!props.selectedKeys.length) {
    return ''
  }
  const byKey = new Map<string, SequenceResidue>()
  for (const chain of props.chains) {
    for (const res of chain.residues) {
      byKey.set(res.key, res)
    }
  }
  const labels = props.selectedKeys
    .slice(0, 3)
    .map(key => {
      const res = byKey.get(key)
      return res ? `${res.chain}:${res.compId}${res.seqId}` : key
    })
  return props.selectedKeys.length > 3 ? `${labels.join(', ')} +${props.selectedKeys.length - 3}` : labels.join(', ')
})

function handleResidueClick(event: MouseEvent, residue: SequenceResidue) {
  emit('toggle-residue', {
    chain: residue.chain,
    seqId: residue.seqId,
    shiftKey: event.shiftKey,
  })
}
</script>

<style scoped lang="less">
.sequence-bar {
  position: relative;
  z-index: 3;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 12px 10px;
  border-top: 1px solid rgba(148, 163, 184, 0.24);
  background: rgba(8, 18, 34, 0.92);
  color: #e2e8f0;
  backdrop-filter: blur(8px);
  flex-shrink: 0;
}

.sequence-bar--white {
  border-top-color: rgba(15, 23, 42, 0.14);
  background: rgba(248, 250, 252, 0.96);
  color: #0f172a;
}

.sequence-bar__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.sequence-bar__chains {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.sequence-chain-tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 5px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  background: transparent;
  color: inherit;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
}

.sequence-chain-tab.is-active {
  border-color: #38bdf8;
  background: rgba(56, 189, 248, 0.16);
  color: #38bdf8;
}

.sequence-bar--white .sequence-chain-tab.is-active {
  border-color: #0284c7;
  background: rgba(2, 132, 199, 0.1);
  color: #0369a1;
}

.sequence-chain-tab__count {
  opacity: 0.72;
  font-variant-numeric: tabular-nums;
}

.sequence-bar__meta {
  flex: 1;
  min-width: 140px;
  font-size: 11px;
  opacity: 0.85;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sequence-bar__selection-badge {
  font-weight: 600;
  color: #22d3ee;
}

.sequence-bar--white .sequence-bar__selection-badge {
  color: #0284c7;
}

.sequence-bar__selection-preview {
  font-weight: 400;
  font-family: @font-family-mono;
  opacity: 0.88;
}

.sequence-bar__actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sequence-action-btn {
  padding: 2px 8px;
  border-radius: 5px;
  border: 1px solid rgba(148, 163, 184, 0.3);
  background: rgba(15, 23, 42, 0.45);
  color: inherit;
  font-size: 11px;
  cursor: pointer;
}

.sequence-bar--white .sequence-action-btn {
  background: #ffffff;
  border-color: rgba(15, 23, 42, 0.18);
}

.sequence-action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.sequence-bar__track {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: thin;
}

.sequence-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 0 0 auto;
}

.sequence-cell__tick {
  height: 13px;
  line-height: 13px;
  font-size: 9px;
  font-family: @font-family-mono;
  opacity: 0.65;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.sequence-cell__btn {
  width: 20px;
  height: 22px;
  padding: 0;
  border-radius: 4px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(30, 41, 59, 0.65);
  color: inherit;
  font-family: @font-family-mono;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.1s ease, border-color 0.1s ease, background-color 0.1s ease;
}

.sequence-bar--white .sequence-cell__btn {
  background: #ffffff;
  border-color: rgba(15, 23, 42, 0.14);
}

.sequence-cell__btn:hover {
  border-color: #38bdf8;
  transform: translateY(-1px);
}

.sequence-cell__btn.is-selected {
  border-color: #22d3ee;
  background: #0891b2;
  color: #ffffff;
}
</style>
