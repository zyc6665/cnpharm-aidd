<template>
  <div class="pocket-viewer">
    <div ref="containerRef" class="pocket-canvas" :class="{ 'pocket-canvas--hidden': Boolean(error) }" />

    <div v-if="loading" class="pocket-overlay">
      <a-spin />
      <span>正在渲染口袋结构…</span>
    </div>
    <div v-else-if="error" class="pocket-overlay pocket-overlay--error">
      <a-alert type="error" show-icon message="3D 结构加载失败" :description="error" />
    </div>

    <div class="pocket-legend">
      <span class="legend-item"><i class="dot dot--pocket" />口袋残基</span>
      <span class="legend-item"><i class="dot dot--key" />关键残基（球棍）</span>
      <span class="legend-item"><i class="dot dot--focus" />选中残基</span>
      <span class="legend-item"><i class="dot dot--ligand" />共晶配体</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import 'molstar/build/viewer/molstar.css'

import { onMounted, onUnmounted, ref, watch } from 'vue'
import type { Viewer as MolstarViewer } from 'molstar/lib/apps/viewer/app'
import { Asset } from 'molstar/lib/mol-util/assets'
import { Color } from 'molstar/lib/mol-util/color'
import { Sphere3D } from 'molstar/lib/mol-math/geometry'
import { Vec3 } from 'molstar/lib/mol-math/linear-algebra'

const props = withDefaults(
  defineProps<{
    pdbUrl: string
    /** auth_seq_id 列表：需要高亮的口袋残基 */
    resIds: number[]
    /** 关键残基（核心 + 关键分级），以球棍模型单独展示 */
    keyResIds?: number[]
    /** 当前选中的残基（auth_seq_id），可多选，单独高亮 */
    selectedResIds?: number[]
    /** 口袋中心坐标，用于把镜头对焦到口袋 */
    pocketCenter?: [number, number, number] | null
    chain?: string
  }>(),
  { keyResIds: () => [], selectedResIds: () => [], pocketCenter: null, chain: 'A' }
)

const containerRef = ref<HTMLElement | null>(null)
const loading = ref(true)
const error = ref('')

// Mol* 类型非常庞大，这里以 any 方式使用其运行时 builder API。
let viewer: MolstarViewer | null = null
let plugin: any = null
let structureSel: any = null
let focusCells: any[] = []
let localSphere: { center: { x: number; y: number; z: number }; radius: number } | null = null
let resizeObserver: ResizeObserver | null = null

let creating: Promise<void> | null = null

/** 只改选中集时重建高亮，但保留用户当前的视角。 */
let keepCamera = false

async function ensureViewer() {
  if (viewer || !containerRef.value) {
    return
  }
  if (creating) {
    await creating
    return
  }

  creating = (async () => {
    const host = containerRef.value
    if (!host) return
    const { Viewer } = await import('molstar/lib/apps/viewer/app')
    viewer = await Viewer.create(host, {
      layoutIsExpanded: false,
      layoutShowControls: false,
      collapseLeftPanel: true,
      collapseRightPanel: true,
      viewportShowControls: false,
      viewportShowExpand: false,
      viewportShowToggleFullscreen: false,
      viewportShowSettings: false,
      viewportShowSelectionMode: false,
      viewportShowAnimation: false,
      viewportShowTrajectoryControls: false,
      viewportShowScreenshotControls: false
    })
    plugin = viewer.plugin
    try {
      plugin.canvas3d?.setProps({ renderer: { backgroundColor: Color(0x0b1a2e) } })
    } catch {
      /* 背景色设置失败不影响渲染 */
    }
  })()
  await creating
  creating = null
}

async function addComponent(
  MS: any,
  expression: any,
  key: string,
  label: string,
  repr: Record<string, unknown>
) {
  const comp = await plugin.builders.structure.tryCreateComponentFromExpression(
    structureSel,
    expression,
    key,
    { label }
  )
  if (comp) {
    await plugin.builders.structure.representation.addRepresentation(comp, repr)
  }
  return comp
}

async function buildHighlights() {
  if (!structureSel) return
  focusCells = []

  const { MolScriptBuilder: MS } = await import('molstar/lib/mol-script/language/builder')
  const chainTest = MS.core.rel.eq([MS.ammp('auth_asym_id'), props.chain])

  const selected = new Set(props.selectedResIds)
  const keyIds = props.keyResIds
  const keySet = new Set(keyIds)
  const residueExpr = (ids: number[]) =>
    MS.struct.generator.atomGroups({
      'chain-test': chainTest,
      'residue-test': MS.core.set.has([MS.set(...ids), MS.ammp('auth_seq_id')])
    })

  // 球棍只给少数几个残基用：关键残基与选中残基各自成组，互不重叠，
  // 同一个原子不会被画两遍（重叠的球棍会互相穿插，看起来像噪点）。
  const ballAndStick = (color: number) => ({
    type: 'ball-and-stick',
    color: 'uniform',
    colorParams: { value: color }
  })

  // 1) 口袋残基里的外围部分 —— 橙色卡通（与整体蛋白同一种表示法，避免一堆小球把结构盖住）
  const peripheral = props.resIds.filter((id) => !selected.has(id) && !keySet.has(id))
  if (peripheral.length) {
    const comp = await addComponent(MS, residueExpr(peripheral), 'pocket-residues', '口袋残基', {
      type: 'cartoon',
      color: 'uniform',
      colorParams: { value: 0xff7a45 }
    })
    if (comp?.cell) focusCells.push(comp.cell)
  }

  // 2) 关键残基 —— 球棍模型：颜色变化看不出「这是哪几个残基」，球棍能
  const keyOnly = keyIds.filter((id) => !selected.has(id))
  if (keyOnly.length) {
    const comp = await addComponent(MS, residueExpr(keyOnly), 'key-residues', '关键残基', ballAndStick(0xffc53d))
    if (comp?.cell) focusCells.push(comp.cell)
  }

  // 3) 选中残基 —— 同样球棍，换成青色以便和「关键但未选中」区分
  if (props.selectedResIds.length) {
    const comp = await addComponent(
      MS,
      residueExpr(props.selectedResIds),
      'focus-residue',
      '选中残基',
      ballAndStick(0x22d3ee)
    )
    if (comp?.cell) focusCells.push(comp.cell)
  }

  // 4) 共晶配体（AN2, 601）—— 按元素着色
  const ligandExpr = residueExpr([601])
  const lig = await addComponent(MS, ligandExpr, 'co-ligand', '共晶配体', {
    type: 'spacefill',
    color: 'element-symbol',
    size: 'uniform',
    sizeParams: { value: 0.5 }
  })
  if (lig?.cell) focusCells.push(lig.cell)
}

function cellBoundingSphere(cells: any[]) {
  let minx = Infinity, miny = Infinity, minz = Infinity
  let maxx = -Infinity, maxy = -Infinity, maxz = -Infinity
  let any = false
  const pos = { x: 0, y: 0, z: 0 }
  for (const cell of cells) {
    const s = cell?.obj?.data
    if (!s?.units) continue
    for (const unit of s.units) {
      const els = unit.elements
      for (let i = 0; i < els.length; i++) {
        unit.conformation.position(els[i], pos)
        any = true
        if (pos.x < minx) minx = pos.x
        if (pos.y < miny) miny = pos.y
        if (pos.z < minz) minz = pos.z
        if (pos.x > maxx) maxx = pos.x
        if (pos.y > maxy) maxy = pos.y
        if (pos.z > maxz) maxz = pos.z
      }
    }
  }
  if (!any) return null
  const center = { x: (minx + maxx) / 2, y: (miny + maxy) / 2, z: (minz + maxz) / 2 }
  const radius = 0.5 * Math.hypot(maxx - minx, maxy - miny, maxz - minz)
  return { center, radius }
}

async function computePocketSphere(url: string, resIds: number[], chain: string) {
  try {
    const text = await (await fetch(url)).text()
    const set = new Set(resIds.map((n) => String(n)))
    // 共晶配体（601）一并纳入，保证口袋与配体都在视野内
    set.add('601')
    let minx = Infinity, miny = Infinity, minz = Infinity
    let maxx = -Infinity, maxy = -Infinity, maxz = -Infinity
    let any = false
    for (const line of text.split('\n')) {
      if (!line.startsWith('ATOM') && !line.startsWith('HETATM')) continue
      const resSeq = line.slice(22, 26).trim()
      if (!set.has(resSeq)) continue
      const ch = line.slice(21, 22).trim() || 'A'
      if (chain && ch !== chain) continue
      const x = parseFloat(line.slice(30, 38))
      const y = parseFloat(line.slice(38, 46))
      const z = parseFloat(line.slice(46, 54))
      if (Number.isNaN(x) || Number.isNaN(y) || Number.isNaN(z)) continue
      any = true
      if (x < minx) minx = x
      if (y < miny) miny = y
      if (z < minz) minz = z
      if (x > maxx) maxx = x
      if (y > maxy) maxy = y
      if (z > maxz) maxz = z
    }
    if (!any) return null
    const center = { x: (minx + maxx) / 2, y: (miny + maxy) / 2, z: (minz + maxz) / 2 }
    const radius = 0.5 * Math.hypot(maxx - minx, maxy - miny, maxz - minz) * 0.72 + 2
    return { center, radius }
  } catch {
    return null
  }
}

function focusPocket() {
  if (!plugin) return
  try {
    const sphere = localSphere ?? cellBoundingSphere(focusCells)
    if (!sphere) {
      plugin.managers.camera.reset(undefined, 0)
      return
    }
    // 必须包成 Sphere3D：直接传 { center, radius } 会把相机状态写成 NaN，
    // 之后拖拽与滚轮都不再生效（NaN 参与任何运算仍是 NaN）。
    plugin.managers.camera.focusSphere(
      Sphere3D.create(Vec3.create(sphere.center.x, sphere.center.y, sphere.center.z), sphere.radius),
      { durationMs: 0 }
    )
  } catch (cause) {
    console.warn('focusPocket failed', cause)
  }
}

async function recolorCartoon() {
  try {
    const structures = plugin.managers.structure.hierarchy.current?.structures ?? []
    for (const structure of structures) {
      await plugin.managers.structure.component.updateRepresentationsTheme(structure.components, {
        color: 'uniform',
        colorParams: { value: 0x8b9bb4 }
      })
    }
  } catch (cause) {
    console.warn('recolor failed', cause)
  }
}

async function fadeCartoon() {
  try {
    const { setStructureTransparency } = await import('molstar/lib/mol-plugin-state/helpers/structure-transparency')
    const { StructureElement } = await import('molstar/lib/mol-model/structure')
    const structures = plugin.managers.structure.hierarchy.current?.structures ?? []
    for (const structure of structures) {
      await setStructureTransparency(
        plugin,
        structure.components,
        0.62,
        async (root: any) => StructureElement.Loci.all(root),
        ['cartoon']
      )
    }
  } catch (cause) {
    console.warn('fade failed', cause)
  }
}

let renderRunning = false
let renderQueued = false

async function render(options: { keepCamera?: boolean } = {}) {
  keepCamera = Boolean(options.keepCamera)
  if (renderRunning) {
    renderQueued = true
    return
  }
  renderRunning = true
  const silent = keepCamera
  if (!silent) {
    loading.value = true
  }
  error.value = ''
  const savedCamera = silent ? plugin?.canvas3d?.camera.state : null
  try {
    if (!props.pdbUrl) {
      loading.value = false
      return
    }
    await ensureViewer()
    if (!plugin) throw new Error('Mol* viewer unavailable')

    await plugin.clear()

    const data = await plugin.builders.data.download(
      { url: Asset.Url(props.pdbUrl), isBinary: false, label: 'GRK4' },
      { state: { isGhost: true } }
    )
    const trajectory = await plugin.builders.structure.parseTrajectory(data, 'pdb')
    const preset = await plugin.builders.structure.hierarchy.applyPreset(trajectory, 'default', {
      representationPreset: 'polymer-cartoon'
    })
    structureSel = preset?.structure ?? null
    localSphere = await computePocketSphere(props.pdbUrl, props.resIds, props.chain)

    await recolorCartoon()
    await buildHighlights()
    await fadeCartoon()
    viewer?.handleResize()
    if (savedCamera) {
      // 选中集变化时相机原样恢复：用户刚拖到的角度不该被一次高亮刷新夺走
      plugin.canvas3d?.camera.setState(savedCamera, 0)
    } else {
      window.setTimeout(focusPocket, 400)
      window.setTimeout(focusPocket, 1500)
    }
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    loading.value = false
    renderRunning = false
    if (renderQueued) {
      renderQueued = false
      void render({ keepCamera })
    }
  }
}

onMounted(async () => {
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(() => viewer?.handleResize())
    resizeObserver.observe(containerRef.value)
  }
  await render()
})

// 结构、口袋残基集合或关键残基集合变了才重建场景；只改选中集时重建高亮并保留视角
watch(
  () => [props.pdbUrl, props.resIds, props.keyResIds, props.chain],
  () => {
    void render()
  },
  { deep: true }
)

watch(
  () => props.selectedResIds,
  () => {
    if (!plugin) return
    void render({ keepCamera: true })
  },
  { deep: true }
)

onUnmounted(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  viewer?.dispose()
  viewer = null
  plugin = null
  structureSel = null
})
</script>

<style scoped>
.pocket-viewer {
  position: relative;
  height: 460px;
  border-radius: 0 0 10px 10px;
  overflow: hidden;
  background:
    radial-gradient(circle at 70% 10%, rgba(87, 181, 231, 0.16), transparent 42%),
    linear-gradient(150deg, #06101d, #0d2038 60%, #16325b);
}

.pocket-canvas {
  width: 100%;
  height: 100%;
}

.pocket-canvas--hidden {
  visibility: hidden;
}

.pocket-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(6, 16, 29, 0.7);
  color: #dbe9ff;
  font-size: 13px;
}

.pocket-overlay--error {
  background: rgba(6, 16, 29, 0.9);
  padding: 24px;
}

.pocket-legend {
  position: absolute;
  right: 12px;
  bottom: 12px;
  display: flex;
  gap: 14px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(8, 20, 36, 0.72);
  backdrop-filter: blur(4px);
  font-size: 12px;
  color: #cfe0f7;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  display: inline-block;
}

.dot--pocket {
  background: #ff7a45;
}

.dot--key {
  background: #ffc53d;
}

.dot--focus {
  background: #22d3ee;
}

.dot--ligand {
  background: #f4d03f;
}

.pocket-viewer :deep(.msp-plugin),
.pocket-viewer :deep(.msp-plugin-content),
.pocket-viewer :deep(.msp-layout-region),
.pocket-viewer :deep(.msp-layout-static) {
  width: 100%;
  height: 100%;
}

.pocket-viewer :deep(.msp-viewport) {
  background: transparent;
}
</style>
