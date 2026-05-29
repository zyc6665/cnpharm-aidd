<template>
  <div class="smiles-cell">
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
import { computed, onMounted, ref, watch } from 'vue'
import SmilesDrawer from 'smiles-drawer'

const props = defineProps<{
  smiles: string
}>()

interface SmilesDrawerModule {
  parse(
    smiles: string,
    onSuccess: (tree: unknown) => void,
    onError: (error: unknown) => void
  ): void
  SvgDrawer: new (options?: Record<string, unknown>) => {
    draw(
      tree: unknown,
      target: SVGSVGElement,
      theme?: string,
      infoOnly?: boolean
    ): void
  }
}

const smilesDrawer = SmilesDrawer as SmilesDrawerModule
const svgRef = ref<SVGSVGElement | null>(null)
const renderFailed = ref(false)
const normalizedSmiles = computed(() => props.smiles.trim())

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

  try {
    const tree = await new Promise<unknown>((resolve, reject) => {
      smilesDrawer.parse(normalizedSmiles.value, resolve, reject)
    })

    const drawer = new smilesDrawer.SvgDrawer({
      width: 132,
      height: 84,
      compactDrawing: true,
      padding: 10
    })

    drawer.draw(tree, svgElement, 'light', false)
  } catch {
    svgElement.innerHTML = ''
    renderFailed.value = true
  }
}

watch(
  () => props.smiles,
  () => {
    void renderSmiles()
  }
)

onMounted(() => {
  void renderSmiles()
})
</script>

<style scoped>
.smiles-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 148px;
  min-width: 148px;
  height: 96px;
  border-radius: 14px;
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.08), transparent 48%),
    linear-gradient(180deg, #f8fafc, #eef2ff);
  border: 1px solid #dbe4ff;
  overflow: hidden;
}

.smiles-cell__canvas {
  width: 132px;
  height: 84px;
}

.smiles-cell__fallback {
  max-width: 132px;
  padding: 0 8px;
  font-size: 12px;
  line-height: 1.5;
  color: #64748b;
  text-align: center;
  word-break: break-all;
}
</style>
