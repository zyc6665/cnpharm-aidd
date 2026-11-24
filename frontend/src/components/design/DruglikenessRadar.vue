<template>
  <div
    class="druglikeness-radar"
    data-testid="druglikeness-radar"
    :data-violations="violations"
    :style="{ width: `${size}px`, height: `${size}px` }"
  >
    <canvas
      v-if="hasData"
      ref="canvasRef"
      class="druglikeness-radar__canvas"
      :width="canvasSize"
      :height="canvasSize"
      :style="{ width: `${size}px`, height: `${size}px` }"
      role="img"
      :aria-label="summary"
    />
    <span v-else class="druglikeness-radar__empty">
      {{ t('design.results.druglikeness.noData') }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  countLipinskiViolations,
  evaluateLipinski,
  hasLipinskiData,
  type LipinskiProperties,
  type LipinskiRuleId,
} from '@/domain/molecules/druglikeness'

const props = withDefaults(
  defineProps<{
    properties?: LipinskiProperties | null
    size?: number
  }>(),
  { properties: null, size: 120 }
)

const { t } = useI18n()
const canvasRef = ref<HTMLCanvasElement | null>(null)

const rules = computed(() => evaluateLipinski(props.properties))
const violations = computed(() => countLipinskiViolations(props.properties))
const hasData = computed(() => hasLipinskiData(props.properties))
const canvasSize = computed(() => {
  const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1
  return Math.max(80, Math.round(props.size * dpr))
})

const summary = computed(() => {
  if (!hasData.value) return t('design.results.druglikeness.noData')
  return t('design.results.druglikeness.violations', { count: violations.value })
})

/**
 * 轴标签用缩写（MW / LogP / HBD / HBA / TPSA），完整名称已由明细列表展示。
 * 小尺寸画布上「氢键供体」这类长词会互相压成一团黑块，缩写是唯一能保证可读性的选择。
 */
function axisLabel(id: LipinskiRuleId): string {
  return t(`design.results.druglikeness.axis.${id}`)
}

function draw(): void {
  const canvas = canvasRef.value
  if (!canvas) return

  let context: CanvasRenderingContext2D | null = null
  try {
    context = canvas.getContext('2d')
  } catch {
    context = null
  }
  if (!context) return

  const dpr = window.devicePixelRatio || 1
  const size = props.size
  const center = size / 2
  const count = rules.value.length

  context.setTransform(dpr, 0, 0, dpr, 0, 0)
  context.clearRect(0, 0, size, size)

  if (!hasData.value) {
    return
  }

  // 半径给轴标签留出外圈空间：大图 38px、小图 26px，否则标签会压到五边形或画布边缘。
  const radius = Math.max(24, center - (size >= 180 ? 38 : 26))
  const labelGap = size >= 180 ? 14 : 10
  const labelFontSize = size >= 180 ? 12 : 10

  const pointAt = (index: number, ratio: number): [number, number] => {
    const angle = -Math.PI / 2 + (index / count) * Math.PI * 2
    return [center + Math.cos(angle) * radius * ratio, center + Math.sin(angle) * radius * ratio]
  }

  // 背景网格（4 圈）
  context.strokeStyle = 'rgba(148, 163, 184, 0.35)'
  context.lineWidth = 1
  for (const ring of [0.25, 0.5, 0.75, 1]) {
    context.beginPath()
    for (let index = 0; index < count; index += 1) {
      const [x, y] = pointAt(index, ring)
      if (index === 0) context.moveTo(x, y)
      else context.lineTo(x, y)
    }
    context.closePath()
    context.stroke()
  }

  // 轴线
  for (let index = 0; index < count; index += 1) {
    const [x, y] = pointAt(index, 1)
    context.beginPath()
    context.moveTo(center, center)
    context.lineTo(x, y)
    context.stroke()
  }

  // 数据多边形：有越界时整体偏红，否则偏青
  const hasViolation = rules.value.some(rule => rule.passed === false)
  context.beginPath()
  rules.value.forEach((rule, index) => {
    const [x, y] = pointAt(index, rule.ratio)
    if (index === 0) context.moveTo(x, y)
    else context.lineTo(x, y)
  })
  context.closePath()
  context.fillStyle = hasViolation ? 'rgba(239, 68, 68, 0.28)' : 'rgba(56, 189, 248, 0.28)'
  context.strokeStyle = hasViolation ? '#ef4444' : '#38bdf8'
  context.lineWidth = 1.6
  context.fill()
  context.stroke()

  // 顶点
  rules.value.forEach((rule, index) => {
    const [x, y] = pointAt(index, rule.ratio)
    context.beginPath()
    context.arc(x, y, 2.4, 0, Math.PI * 2)
    context.fillStyle = rule.passed === false ? '#ef4444' : '#38bdf8'
    context.fill()
  })

  // 轴标签：按象限决定对齐方式，保证文字朝外展开、不压到多边形也不互相重叠。
  context.fillStyle = 'rgba(100, 116, 139, 0.95)'
  context.font = `${labelFontSize}px sans-serif`
  rules.value.forEach((rule, index) => {
    const angle = -Math.PI / 2 + (index / count) * Math.PI * 2
    const dx = Math.cos(angle)
    const dy = Math.sin(angle)
    const x = center + dx * (radius + labelGap)
    const y = center + dy * (radius + labelGap)
    context.textAlign = dx > 0.35 ? 'left' : dx < -0.35 ? 'right' : 'center'
    context.textBaseline = dy > 0.35 ? 'top' : dy < -0.35 ? 'bottom' : 'middle'
    context.fillText(axisLabel(rule.id), x, y)
  })
}

onMounted(draw)

watch(
  () => [props.properties, props.size],
  () => {
    draw()
  },
  // canvas 由 v-if="hasData" 控制，必须等 DOM 更新后再取引用。
  { deep: true, flush: 'post' }
)
</script>

<style scoped lang="less">
.druglikeness-radar {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.druglikeness-radar__canvas {
  display: block;
}

.druglikeness-radar__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
  color: @text-tertiary;
  font-size: @font-size-xs;
  text-align: center;
}
</style>
