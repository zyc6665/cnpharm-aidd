<template>
  <div ref="hostRef" class="smiles-cell" :class="{ 'smiles-cell--block': block }">
    <svg
      v-if="normalizedSmiles && !renderFailed"
      ref="svgRef"
      class="smiles-cell__canvas"
      :aria-label="normalizedSmiles"
      role="img"
    />
    <span v-else class="smiles-cell__fallback">{{ normalizedSmiles || '-' }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    smiles: string
    /**
     * 表格单元格用 132×84 的紧凑尺寸（一行能放下、不撑高行高）；
     * 详情页传 `block` 让它铺满容器宽度，按实际像素重绘。
     */
    block?: boolean
    /** 紧凑模式下的绘图尺寸，单位 px。 */
    width?: number
    height?: number
  }>(),
  { block: false, width: 132, height: 84 }
)

interface SmilesDrawerModule {
  parse(
    smiles: string,
    onSuccess: (tree: unknown) => void,
    onError: (error: unknown) => void
  ): void
  SvgDrawer: new (options?: Record<string, unknown>) => {
    draw(tree: unknown, target: SVGSVGElement, theme?: string, infoOnly?: boolean): void
  }
}

let smilesDrawerPromise: Promise<SmilesDrawerModule> | null = null

async function loadSmilesDrawer(): Promise<SmilesDrawerModule> {
  if (!smilesDrawerPromise) {
    smilesDrawerPromise = (async () => {
      const module = await import('smiles-drawer')
      return module.default as SmilesDrawerModule
    })()
  }

  return smilesDrawerPromise
}

const hostRef = ref<HTMLDivElement | null>(null)
const svgRef = ref<SVGSVGElement | null>(null)
const renderFailed = ref(false)
const measuredWidth = ref(0)
const activeTheme = ref<'light' | 'dark'>('dark')
let resizeObserver: ResizeObserver | null = null
let themeObserver: MutationObserver | null = null

const normalizedSmiles = computed(() => props.smiles.trim())

/**
 * 绘图尺寸。
 *
 * 原来写死 132×84 且固定传 `'light'` 主题——在深色卡片上等于用深色线条画白色背景，
 * 屏幕上的结果是分子骨架几乎看不见（评审时化合物详情页只看到几个点）。
 * 现在按容器实际宽度重绘，主题跟随全局 `data-theme`。
 */
const drawingSize = computed(() => {
  if (!props.block) {
    return { width: props.width, height: props.height }
  }

  const width = Math.max(measuredWidth.value, 200)
  return { width, height: Math.round(width * 0.6) }
})

/**
 * 主题从 `document.documentElement` 的 `data-theme` 读，而不是从 store 读。
 *
 * 主题的唯一真源就是那个属性（`App.vue:51` 与 `stores/app.ts:57` 都只改它），
 * 直接读 DOM 让本组件不必依赖 store —— 依赖 store 会把 `@/locales` 整条链
 * （`vue-i18n` 实例）拉进单测的模块图里，而多个 spec 都 mock 了 `vue-i18n`。
 */
function readTheme(): 'light' | 'dark' {
  if (typeof document === 'undefined') {
    return 'dark'
  }

  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark'
}

const drawingTheme = computed(() => activeTheme.value)

async function renderSmiles() {
  const svgElement = svgRef.value

  if (!svgElement) {
    return
  }

  svgElement.innerHTML = ''
  renderFailed.value = false

  if (!normalizedSmiles.value) {
    renderFailed.value = true
    return
  }

  const { width, height } = drawingSize.value

  try {
    const smilesDrawer = await loadSmilesDrawer()
    const tree = await new Promise<unknown>((resolve, reject) => {
      smilesDrawer.parse(normalizedSmiles.value, resolve, reject)
    })

    const drawer = new smilesDrawer.SvgDrawer({
      width,
      height,
      // 紧凑绘制会压短键长、省略部分氢，表格里够用，详情页就糊了
      compactDrawing: !props.block,
      padding: props.block ? 12 : 6,
      bondThickness: props.block ? 1.1 : 0.8,
      bondLength: props.block ? 24 : 14,
      fontSizeLarge: props.block ? 10 : 6,
      fontSizeSmall: props.block ? 7 : 4,
    })

    drawer.draw(tree, svgElement, drawingTheme.value, false)
  } catch {
    svgElement.innerHTML = ''
    renderFailed.value = true
  }
}

function measure() {
  const host = hostRef.value
  if (!host || !props.block) {
    return
  }

  const next = Math.round(host.clientWidth)
  if (next > 0 && next !== measuredWidth.value) {
    measuredWidth.value = next
  }
}

watch(
  () => [props.smiles, props.block, props.width, props.height, drawingTheme.value],
  () => {
    measure()
    void renderSmiles()
  }
)

onMounted(() => {
  activeTheme.value = readTheme()
  measure()
  void renderSmiles()

  if (props.block && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      const before = measuredWidth.value
      measure()
      if (measuredWidth.value !== before) {
        void renderSmiles()
      }
    })
    if (hostRef.value) {
      resizeObserver.observe(hostRef.value)
    }
  }

  // 主题切换时重绘：smiles-drawer 的深/浅两套配色是绘制期决定的，不会随 CSS 变
  if (typeof MutationObserver !== 'undefined') {
    themeObserver = new MutationObserver(() => {
      const next = readTheme()
      if (next !== activeTheme.value) {
        // 只改 ref，重绘交给上面的 watch，避免同一次切换画两遍
        activeTheme.value = next
      }
    })
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  themeObserver?.disconnect()
  themeObserver = null
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.smiles-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 148px;
  min-width: 148px;
  height: 96px;
  /* 用主题变量而不是写死浅色底：深色下是几乎透明的浅层，浅色下是极淡的蓝灰 */
  border: 1px solid @border-color;
  border-radius: @border-radius-lg;
  background:
    radial-gradient(circle at top left, @accent-color-light, transparent 55%),
    @bg-hover;
  overflow: hidden;
}

.smiles-cell--block {
  width: 100%;
  min-width: 0;
  height: auto;
  aspect-ratio: 5 / 3;
}

.smiles-cell__canvas {
  width: 100%;
  height: 100%;
}

.smiles-cell__fallback {
  padding: 0 @spacing-sm;
  color: @text-tertiary;
  font-family: @font-family-mono;
  font-size: @font-size-xs;
  overflow-wrap: anywhere;
  text-align: center;
}
</style>
