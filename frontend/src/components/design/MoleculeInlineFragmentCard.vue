<template>
  <div
    class="molecule-inline-fragment-card"
    :class="{ 'is-disabled': disabled }"
    :role="disabled ? undefined : 'button'"
    :tabindex="disabled ? -1 : 0"
    :aria-disabled="disabled ? 'true' : undefined"
    @click="handleCardClick"
    @keydown.enter.self.prevent="handleCardClick"
    @keydown.space.self.prevent="handleCardClick"
  >
    <div class="fragment-preview">
      <svg
        :viewBox="svgViewBox"
        class="fragment-svg"
      >
        <!-- Bonds -->
        <g class="bonds">
          <line
            v-for="(bond, index) in bonds"
            :key="`bond-${index}`"
            :x1="atomCoords[bond.a]?.x"
            :y1="atomCoords[bond.a]?.y"
            :x2="atomCoords[bond.b]?.x"
            :y2="atomCoords[bond.b]?.y"
            :stroke-width="bond.order === 2 ? 2.5 : bond.order === 3 ? 3 : 1.5"
            stroke="currentColor"
            stroke-linecap="round"
          />
        </g>
        <!-- Atoms -->
        <g class="atoms">
          <g v-for="atom in atoms" :key="`atom-${atom.index}`">
            <!-- Selection halo -->
            <circle
              v-if="isSelected(atom.index)"
              :cx="atomCoords[atom.index]?.x"
              :cy="atomCoords[atom.index]?.y"
              :r="6"
              class="selection-halo"
            />
            <!-- Atom circle -->
            <circle
              :cx="atomCoords[atom.index]?.x"
              :cy="atomCoords[atom.index]?.y"
              :r="atom.isHetero ? 3.5 : 2.5"
              :class="['atom-circle', { 'is-hetero': atom.isHetero, 'is-selected': isSelected(atom.index) }]"
            />
            <!-- Atom label (only for small molecules) -->
            <text
              v-if="atoms.length <= 32 && atom.isHetero"
              :x="atomCoords[atom.index]?.x"
              :y="(atomCoords[atom.index]?.y ?? 0) + 1"
              class="atom-label"
              text-anchor="middle"
              dominant-baseline="middle"
            >
              {{ atom.element }}
            </text>
          </g>
        </g>
      </svg>
    </div>

    <div class="fragment-metadata">
      <div class="metadata-header">
        <span class="filename">{{ filename }}</span>
        <a-tag :color="modeColor" class="mode-tag">{{ modeLabel }}</a-tag>
      </div>
      <div class="metadata-summary">
        <span class="atom-count">{{ atomCountLabel }}</span>
        <span v-if="selectedIndices.length > 0" class="selected-preview">
          {{ selectedIndicesPreview }}
        </span>
      </div>
      <a-button
        type="primary"
        size="small"
        :disabled="disabled"
        class="open-sketch-btn"
        data-testid="open-fragment-sketch"
        @click.stop="handleOpenSketch"
      >
        {{ openButtonLabel }}
      </a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

export interface InlineFragmentAtom {
  index: number
  element: string
  x2d: number
  y2d: number
  isHetero?: boolean
}

export interface InlineFragmentBond {
  a: number
  b: number
  order: number
}

const props = withDefaults(
  defineProps<{
    filename: string
    atoms: InlineFragmentAtom[]
    bonds: InlineFragmentBond[]
    selectedIndices: number[]
    mode: 'fragment' | 'dock'
    disabled?: boolean
  }>(),
  {
    disabled: false
  }
)

const emit = defineEmits<{
  (event: 'open-sketch'): void
}>()

const { t, te } = useI18n()

const safeT = (key: string, fallback: string): string => {
  return typeof te === 'function' && te(key) ? t(key) : fallback
}

const isSelected = (index: number): boolean => {
  return props.selectedIndices.includes(index)
}

const atomCoords = computed(() => {
  if (props.atoms.length === 0) return {}

  const xValues = props.atoms.map(a => a.x2d)
  const yValues = props.atoms.map(a => a.y2d)
  const minX = Math.min(...xValues)
  const maxX = Math.max(...xValues)
  const minY = Math.min(...yValues)
  const maxY = Math.max(...yValues)

  const rangeX = maxX - minX || 1
  const rangeY = maxY - minY || 1
  const scale = 80 / Math.max(rangeX, rangeY)

  const coords: Record<number, { x: number; y: number }> = {}
  props.atoms.forEach(atom => {
    coords[atom.index] = {
      x: 50 + (atom.x2d - minX - rangeX / 2) * scale,
      y: 50 + (atom.y2d - minY - rangeY / 2) * scale
    }
  })

  return coords
})

const svgViewBox = computed(() => '0 0 100 100')

const modeColor = computed(() => {
  return props.mode === 'fragment' ? 'blue' : 'orange'
})

const modeLabel = computed(() => {
  return props.mode === 'fragment'
    ? safeT('modelParams.options.generationModeFragment', '保留片段')
    : safeT('modelParams.options.generationModeDock', '待对接原子')
})

const atomCountLabel = computed(() => {
  const total = props.atoms.length
  const selected = props.selectedIndices.length
  const hasTe = typeof te === 'function'
  if (props.mode === 'dock' && selected === 0) {
    return hasTe && te('design.molecule.dockWholeSummary')
      ? t('design.molecule.dockWholeSummary', { total })
      : `全配体对接（${total} 个原子）`
  }
  const key = props.mode === 'fragment' ? 'design.molecule.keptSummary' : 'design.molecule.dockSummary'
  if (hasTe && te(key)) {
    return t(key, { selected, total })
  }
  return `共 ${total} 个原子 · 已选 ${selected} 个`
})

const selectedIndicesPreview = computed(() => {
  if (props.selectedIndices.length === 0) return ''
  if (props.selectedIndices.length <= 5) {
    return props.selectedIndices.join(', ')
  }
  return `${props.selectedIndices.slice(0, 3).join(', ')}...`
})

const openButtonLabel = computed(() => {
  return props.mode === 'fragment'
    ? safeT('design.molecule.openSketchFragment', '在画板中选择保留片段')
    : safeT('design.molecule.openSketchDock', '在画板中选择对接原子')
})

const handleCardClick = () => {
  if (!props.disabled) {
    emit('open-sketch')
  }
}

const handleOpenSketch = () => {
  emit('open-sketch')
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.molecule-inline-fragment-card {
  display: flex;
  gap: @spacing-md;
  background: @bg-elevated;
  border: 1px solid @border-color;
  border-radius: @border-radius-md;
  padding: @spacing-md;
  cursor: pointer;
  transition: all @transition-base;

  &:hover:not(.is-disabled) {
    border-color: @accent-color-border;
    box-shadow: @shadow-md;
  }

  &.is-disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}

.fragment-preview {
  flex-shrink: 0;
  width: 120px;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: @bg-surface;
  border-radius: @border-radius-sm;
  border: 1px solid @border-color;
}

.fragment-svg {
  width: 100%;
  height: 100%;
  color: @text-secondary;

  .bonds line {
    opacity: 0.7;
  }

  .atom-circle {
    fill: @text-secondary;
    stroke: @bg-surface;
    stroke-width: 0.5;

    &.is-hetero {
      fill: @accent-color;
    }

    &.is-selected {
      fill: @error-color;
    }
  }

  .selection-halo {
    fill: none;
    stroke: @error-color;
    stroke-width: 2;
    opacity: 0.6;
  }

  .atom-label {
    fill: @bg-surface;
    font-size: 6px;
    font-weight: @font-weight-semibold;
    pointer-events: none;
  }
}

.fragment-metadata {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: @spacing-sm;
  min-width: 0;
}

.metadata-header {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  justify-content: space-between;
}

.filename {
  font-size: @font-size-md;
  font-weight: @font-weight-medium;
  color: @text-primary;
  .text-ellipsis();
}

.mode-tag {
  flex-shrink: 0;
}

.metadata-summary {
  display: flex;
  flex-direction: column;
  gap: @spacing-xs;
  font-size: @font-size-sm;
  color: @text-secondary;
}

.atom-count {
  font-weight: @font-weight-medium;
}

.selected-preview {
  font-family: @font-family-mono;
  color: @text-tertiary;
}

.open-sketch-btn {
  align-self: flex-start;
  margin-top: @spacing-xs;
}
</style>
