<template>
  <a-modal :open="open" :title="mode === 'fragment' ? label('fragmentTitle') : label('dockTitle')" :width="980"
    @cancel="close">
    <div v-if="molecule" class="sketch-layout">
      <section v-for="panel in panels" :key="panel" :class="`sketch-${panel}`">
        <div v-if="panel === 'editor'" class="sketch-toolbar">
          <div class="sketch-group" role="group" :aria-label="label('toolGroup')">
            <a-button v-for="option in tools" :key="option" size="small" :type="tool === option ? 'primary' : 'default'"
              :aria-pressed="tool === option" :data-testid="`sketch-tool-${option}`" @click="setTool(option)">
              {{ label(option) }}
            </a-button>
          </div>
          <div class="sketch-group" role="group" :aria-label="label('selectionGroup')">
            <a-button size="small" @click="selectAll">{{ label('selectAll') }}</a-button>
            <a-button size="small" @click="invert">{{ label('invert') }}</a-button>
            <a-button size="small" @click="clearSelection">{{ label('clear') }}</a-button>
          </div>
          <div class="sketch-group" role="group" :aria-label="label('viewGroup')">
            <a-button size="small" :aria-label="label('zoomOut')" :title="label('zoomOut')" :disabled="zoom <= minZoom"
              @click="changeZoom(-1)">−</a-button>
            <a-button size="small" :aria-label="label('zoomIn')" :title="label('zoomIn')" :disabled="zoom >= maxZoom"
              @click="changeZoom(1)">+</a-button>
            <a-button size="small" @click="resetView">{{ label('resetView') }}</a-button>
          </div>
        </div>
        <h3 v-else class="sketch-heading">{{ label('preview') }}</h3>
        <svg :viewBox="panel === 'editor' ? viewBox : defaultViewBox" :role="panel === 'editor' ? 'group' : 'img'"
          :aria-label="label(panel === 'editor' ? 'canvas' : 'preview')" :data-testid="`sketch-${panel}-canvas`"
          class="sketch-canvas" :class="{ 'sketch-box-mode': panel === 'editor' && tool === 'box' }"
          @pointerdown="panel === 'editor' && startBox($event)"
          @pointermove="panel === 'editor' && moveBox($event)"
          @pointerup="panel === 'editor' && finishBox($event)"
          @pointercancel="panel === 'editor' && cancelBox($event)"
          @lostpointercapture="panel === 'editor' && cancelBox($event)">
          <g v-for="bond in drawnBonds" :key="`${bond.a}-${bond.b}`" class="sketch-bond"
            :class="{ 'is-selected': selected.has(bond.a) && selected.has(bond.b) }">
            <line v-for="(line, i) in bond.lines" :key="i" :x1="line.x1" :y1="line.y1" :x2="line.x2" :y2="line.y2"
              :stroke-dasharray="line.dashed ? '4 3' : undefined" />
          </g>
          <g v-for="atom in drawnAtoms" :key="atom.index" :transform="`translate(${atom.cx} ${atom.cy})`" class="sketch-atom"
            :class="{ 'is-selected': selected.has(atom.index), 'is-interactive': panel === 'editor' && tool !== 'box' }"
            :data-testid="panel === 'editor' ? `sketch-atom-${atom.index}` : undefined"
            :aria-hidden="panel === 'preview' || tool === 'box' ? 'true' : undefined"
            :role="panel === 'editor' && tool !== 'box' ? 'button' : undefined"
            :tabindex="panel === 'editor' && tool !== 'box' ? 0 : undefined"
            :aria-pressed="panel === 'editor' && tool !== 'box' ? selected.has(atom.index) : undefined"
            :aria-label="panel === 'editor' && tool !== 'box' ? atomLabel(atom) : undefined"
            @click="panel === 'editor' && activateAtom(atom.index)"
            @dblclick="panel === 'editor' && tool !== 'box' && addRing(atom.index)"
            @keydown.enter.prevent="panel === 'editor' && activateAtom(atom.index)"
            @keydown.space.prevent="panel === 'editor' && activateAtom(atom.index)">
            <title v-if="panel === 'editor'">{{ atomLabel(atom) }}</title>
            <circle v-if="panel === 'editor'" r="17" class="sketch-hit" />
            <circle r="14" class="sketch-halo" />
            <circle :r="atom.isHetero || atom.element !== 'C' ? 9 : 4" class="sketch-node"
              :style="{ '--atom-ink': elementColor[atom.element] }" />
            <text v-if="atom.isHetero || atom.element !== 'C'" class="sketch-element">{{ atom.element }}</text>
            <g v-if="panel === 'editor'" transform="translate(10 -12)">
              <rect :x="-badgeWidth(atom.index) / 2" y="-7" :width="badgeWidth(atom.index)" height="14" rx="5" class="sketch-badge" />
              <text class="sketch-index">{{ atom.index }}</text>
            </g>
          </g>
          <rect v-if="panel === 'editor' && marquee" v-bind="marquee" class="sketch-marquee" />
        </svg>
        <template v-if="panel === 'preview'">
          <p class="sketch-count" data-testid="sketch-count" aria-live="polite">
            {{ label('selectionCount', { count: indices.length, total: molecule.atoms.length }) }}
          </p>
          <div v-if="indices.length" class="sketch-tags">
            <a-button v-for="index in indices" :key="index" size="small" shape="round" :data-testid="`sketch-remove-${index}`"
              :aria-label="label('removeAtom', { index })" @click="toggleAtom(index)">{{ index }} ×</a-button>
            <a-button size="small" type="link" @click="clearSelection">{{ label('clear') }}</a-button>
          </div>
          <p class="sketch-hint">{{ label(mode === 'fragment' ? 'fragmentHint' : 'dockHint') }}</p>
        </template>
        <p v-else class="sketch-hint">{{ label(tool === 'box' ? 'boxHint' : 'canvasHint') }}</p>
      </section>
    </div>
    <p v-else class="sketch-hint">{{ label('noMolecule') }}</p>
    <p v-if="exportError" class="sketch-error" role="alert">{{ label('exportError', { reason: exportError }) }}</p>
    <template #footer>
      <a-button @click="close">{{ label('cancel') }}</a-button>
      <a-button type="primary" data-testid="sketch-confirm" :disabled="!molecule || !indices.length" @click="confirm">
        {{ label('confirm') }}
      </a-button>
    </template>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { exportSelectedFragmentSdf, findRingAtomIndices } from '@/domain/molecules/fragment-graph'
import type { FragmentAtom, FragmentMolecule } from '@/domain/molecules/fragment-graph'

const props = defineProps<{
  open: boolean
  molecule: FragmentMolecule | null
  selectedIndices: number[]
  mode: 'fragment' | 'dock'
}>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  confirm: [payload: { selectedIndices: number[]; exportedFile: File | null }]
}>()

const { te, t, locale } = useI18n()
const copy = {
  fragmentTitle: ['选择保留片段', 'Select fragment to keep'],
  dockTitle: ['选择重新对接的原子', 'Select atoms to redock'],
  point: ['点选', 'Click'], box: ['框选', 'Box'], ring: ['按环选中', 'Select ring'],
  toolGroup: ['选择工具', 'Selection tool'], selectionGroup: ['选区操作', 'Selection actions'], viewGroup: ['视图操作', 'View actions'],
  selectAll: ['全选', 'Select all'], invert: ['反选', 'Invert'], clear: ['清空', 'Clear'],
  resetView: ['重置视图', 'Reset view'], zoomIn: ['放大', 'Zoom in'], zoomOut: ['缩小', 'Zoom out'],
  canvas: ['分子草图', 'Molecule sketch'], preview: ['选区预览', 'Selection preview'],
  selectionCount: ['已选原子：{count} / {total}', 'Selected atoms: {count} / {total}'],
  atomLabel: ['{element} · 原子 {index}', '{element} · atom {index}'],
  removeAtom: ['移除原子 {index}', 'Remove atom {index}'],
  fragmentHint: ['选中原子将作为保留片段传入 LDDM，未全选时自动裁剪生成子结构 SDF。', 'LDDM keeps the selected atoms. Selecting a subset creates a cropped SDF.'],
  dockHint: ['选中原子将作为 atoms_to_dock 重新对接，未选部分固定。', 'Selected atoms are passed as atoms_to_dock. Unselected atoms stay fixed.'],
  canvasHint: ['原子编号从 0 开始。双击可选中该原子所在的最小环。', 'Atom indices start at 0. Double-click an atom to select its smallest ring.'],
  boxHint: ['拖动框选，将框内的原子加入选区。', 'Drag a box to add enclosed atoms to the selection.'],
  noMolecule: ['没有可预览的分子结构。', 'No molecular structure to preview.'],
  exportError: ['无法生成片段 SDF：{reason}', 'Unable to export fragment SDF: {reason}'],
  cancel: ['取消', 'Cancel'], confirm: ['确认', 'Confirm']
} as const

function label(key: keyof typeof copy, values: Record<string, string | number> = {}): string {
  const path = `design.molecule.sketch.${key}`
  if (te(path)) return t(path, values)
  return copy[key][locale.value.startsWith('zh') ? 0 : 1].replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ''))
}

const panels = ['editor', 'preview'] as const
const tools = ['point', 'box', 'ring'] as const
type Tool = typeof tools[number]
const tool = ref<Tool>('point')
const selected = ref(new Set<number>())
const indices = computed(() => [...selected.value].sort((a, b) => a - b))
const exportError = ref('')
const width = 440
const height = 320
const minZoom = 0.75
const maxZoom = 2.5
const zoom = ref(1)
const viewport = computed(() => ({ x: (width - width / zoom.value) / 2, y: (height - height / zoom.value) / 2,
  width: width / zoom.value, height: height / zoom.value }))
const viewBox = computed(() => Object.values(viewport.value).join(' '))
const defaultViewBox = `0 0 ${width} ${height}`

function setTool(value: Tool) {
  tool.value = value
  drag.value = null
}

function setSelection(values: Iterable<number>) {
  selected.value = new Set(values)
  exportError.value = ''
}

function clearSelection() { setSelection([]) }
function selectAll() { setSelection(drawnAtoms.value.map(atom => atom.index)) }
function invert() { setSelection(drawnAtoms.value.map(atom => atom.index).filter(index => !selected.value.has(index))) }
function resetView() { zoom.value = 1 }
function changeZoom(direction: number) {
  zoom.value = Math.min(maxZoom, Math.max(minZoom, zoom.value * 1.25 ** direction))
}

function toggleAtom(index: number) {
  const next = new Set(selected.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  setSelection(next)
}

function addRing(index: number) {
  if (props.molecule) setSelection([...selected.value, ...findRingAtomIndices(props.molecule, index)])
}

function activateAtom(index: number) {
  if (tool.value === 'point') toggleAtom(index)
  if (tool.value === 'ring') addRing(index)
}

const elementColor: Record<string, string> = {
  N: '#3b82f6', O: '#ef4444', S: '#f59e0b', F: '#047857', Cl: '#047857', Br: '#047857', P: '#c2410c'
}
const drawnAtoms = computed(() => {
  const atoms = props.molecule?.atoms ?? []
  if (!atoms.length) return []
  const [minX, maxX, minY, maxY] = atoms.reduce(([left, right, top, bottom], { x2d, y2d }) =>
    [Math.min(left, x2d), Math.max(right, x2d), Math.min(top, y2d), Math.max(bottom, y2d)], [Infinity, -Infinity, Infinity, -Infinity])
  const scale = Math.min((width - 64) / (maxX - minX), (height - 64) / (maxY - minY))
  return atoms.map(atom => ({ ...atom,
    cx: width / 2 + (atom.x2d - (minX + maxX) / 2) * (Number.isFinite(scale) ? scale : 0),
    cy: height / 2 + (atom.y2d - (minY + maxY) / 2) * (Number.isFinite(scale) ? scale : 0)
  }))
})
const drawnBonds = computed(() => (props.molecule?.bonds ?? []).flatMap(({ a, b, order }) => {
  const from = drawnAtoms.value[a]
  const to = drawnAtoms.value[b]
  if (!from || !to) return []
  const dx = to.cx - from.cx
  const dy = to.cy - from.cy
  const length = Math.hypot(dx, dy) || 1
  const offsets = order === 3 ? [-4, 0, 4] : order === 2 || order === 1.5 ? [-2.5, 2.5] : [0]
  const lines = offsets.map((offset, i) => {
    const x = -(dy / length) * offset
    const y = (dx / length) * offset
    return { x1: from.cx + x, y1: from.cy + y, x2: to.cx + x, y2: to.cy + y, dashed: order === 1.5 && i === 1 }
  })
  return { a, b, lines }
}))
const badgeWidth = (index: number) => 9 + String(index).length * 6
const atomLabel = (atom: FragmentAtom) => label('atomLabel', { element: atom.element, index: atom.index })

interface Point { x: number; y: number }
const drag = ref<{ id: number; start: Point; end: Point } | null>(null)
const marquee = computed(() => {
  if (!drag.value) return null
  const { start, end } = drag.value
  return { x: Math.min(start.x, end.x), y: Math.min(start.y, end.y), width: Math.abs(start.x - end.x), height: Math.abs(start.y - end.y) }
})

watch([() => props.open, () => props.molecule, () => props.mode], ([open]) => {
  if (!open) return
  const count = props.molecule?.atoms.length ?? 0
  setSelection(props.selectedIndices.filter(i => Number.isInteger(i) && i >= 0 && i < count))
  setTool('point')
  resetView()
}, { immediate: true })

function pointerPosition(event: PointerEvent): Point | null {
  const svg = event.currentTarget as SVGSVGElement
  const matrix = svg.getScreenCTM?.()
  if (matrix) {
    const point = svg.createSVGPoint()
    point.x = event.clientX
    point.y = event.clientY
    return point.matrixTransform(matrix.inverse())
  }
  return null
}

function startBox(event: PointerEvent) {
  if (tool.value !== 'box' || event.button !== 0 || drag.value) return
  const point = pointerPosition(event)
  if (!point) return
  const svg = event.currentTarget as SVGSVGElement
  svg.setPointerCapture?.(event.pointerId)
  drag.value = { id: event.pointerId, start: point, end: point }
}

function moveBox(event: PointerEvent) {
  if (!drag.value || drag.value.id !== event.pointerId) return
  const point = pointerPosition(event)
  if (point) drag.value.end = point
}

function finishBox(event: PointerEvent) {
  if (!drag.value || drag.value.id !== event.pointerId) return
  moveBox(event)
  const box = marquee.value
  if (box) {
    const included = drawnAtoms.value.filter(({ cx, cy }) => cx >= box.x && cx <= box.x + box.width && cy >= box.y && cy <= box.y + box.height)
    setSelection([...selected.value, ...included.map(atom => atom.index)])
  }
  drag.value = null
}

function cancelBox(event: PointerEvent) {
  if (drag.value?.id === event.pointerId) drag.value = null
}

function close() { emit('update:open', false) }

function confirm() {
  if (!props.molecule || !indices.value.length) return
  const selectedIndices = [...indices.value]
  let exportedFile: File | null = null
  if (props.mode === 'fragment' && selectedIndices.length < props.molecule.atoms.length) {
    try {
      exportedFile = exportSelectedFragmentSdf(props.molecule, selectedIndices)
    } catch (error) {
      exportError.value = error instanceof Error ? error.message : String(error)
      return
    }
  }
  emit('confirm', { selectedIndices, exportedFile })
  close()
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.sketch-layout { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 16px; }
.sketch-editor, .sketch-preview {
  min-width: 0;
  padding: 12px;
  background: @bg-surface;
  border: 1px solid @border-strong;
  border-radius: @border-radius-md;
}
.sketch-toolbar, .sketch-group, .sketch-tags { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.sketch-toolbar { gap: 8px 12px; margin-bottom: 10px; }
.sketch-heading { color: @text-primary; font-size: 14px; margin: 0 0 8px; }
.sketch-canvas {
  display: block;
  width: 100%;
  aspect-ratio: 11 / 8;
  background: @bg-elevated;
  border: 1px solid @border-color;
  border-radius: @border-radius-md;
  user-select: none;
}
.sketch-box-mode { cursor: crosshair; touch-action: none; }
.sketch-bond { stroke: @text-secondary; stroke-width: 2; stroke-linecap: round; pointer-events: none; }
.sketch-bond.is-selected { stroke: @accent-color; stroke-width: 2.5; }
.sketch-atom { pointer-events: none; }
.sketch-atom.is-interactive { cursor: pointer; pointer-events: auto; }
.sketch-atom:focus-visible { outline: none; }
.sketch-hit { fill: transparent; }
.sketch-halo { fill: transparent; stroke: transparent; stroke-width: 2; }
.sketch-atom:hover .sketch-halo, .sketch-atom:focus-visible .sketch-halo { stroke: @text-primary; stroke-dasharray: 3 2; }
.sketch-atom.is-selected .sketch-halo { fill: @accent-color-light; stroke: @accent-color; }
.sketch-atom.is-selected:focus-visible .sketch-halo { stroke: @text-primary; }
.sketch-node { fill: @bg-surface; stroke: var(--atom-ink, @text-secondary); stroke-width: 2.5; }
.sketch-element, .sketch-index {
  text-anchor: middle;
  dominant-baseline: central;
  fill: @text-primary;
  font-size: 10px;
  font-weight: 600;
}
.sketch-badge { fill: @bg-surface; stroke: @border-strong; }
.sketch-atom.is-selected .sketch-badge { stroke: @accent-color; }
.sketch-marquee { fill: @accent-color-light; stroke: @accent-color; stroke-dasharray: 4 3; pointer-events: none; }
.sketch-preview .sketch-atom:not(.is-selected), .sketch-preview .sketch-bond:not(.is-selected) { opacity: 0.45; }
.sketch-count { margin: 10px 0 6px; font-weight: 600; color: @text-primary; }
.sketch-tags { max-height: 116px; overflow: auto; padding: 2px; }
.sketch-hint { margin: 8px 0 0; color: @text-secondary; font-size: 12px; }
.sketch-error { margin-top: 8px; color: @error-color; }

@media (max-width: 640px) {
  .sketch-layout { grid-template-columns: minmax(0, 1fr); }
}
</style>
