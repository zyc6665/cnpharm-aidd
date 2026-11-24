<template>
  <div class="pocket-viewer">
    <div ref="containerRef" class="pocket-canvas" :class="{ 'pocket-canvas--hidden': Boolean(error) }" />
    <div v-if="loading" class="pocket-overlay"><a-spin /><span>{{ t('tasks.visualizationLoading') }}</span></div>
    <div v-else-if="error" class="pocket-overlay pocket-overlay--error"><a-alert type="error" show-icon :message="t('tasks.visualizationFailed')" :description="error" /></div>
    <div class="pocket-controls" role="group" :aria-label="t('tasks.visualizationPocketControls')">
      <label class="pocket-control"><span>{{ t('tasks.visualizationProteinRepresentation') }}</span>
        <select v-model="pocketRepresentation" :disabled="loading || Boolean(error)" :aria-label="t('tasks.visualizationProteinRepresentation')"><option value="cartoon">{{ t('tasks.visualizationCartoon') }}</option><option value="surface">{{ t('tasks.visualizationSurface') }}</option></select>
      </label>
      <button class="pocket-reset" type="button" :disabled="loading || Boolean(error)" @click="focusPocket">{{ t('tasks.visualizationResetView') }}</button>
    </div>
    <div class="pocket-legend"><span class="legend-item"><i class="dot dot--pocket" />{{ t('tasks.pocketResiduesOverlay') }}</span><span class="legend-item"><i class="dot dot--focus" />{{ t('tasks.selectedResidue') }}</span><span class="legend-item"><i class="dot dot--ligand" />{{ t('tasks.coLigand') }}</span></div>
  </div>
</template>

<script setup lang="ts">
import 'molstar/build/viewer/molstar.css'
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MolstarRepresentation } from '@/domain/tasks'
import type { Viewer as MolstarViewer } from 'molstar/lib/apps/viewer/app'
import { Asset } from 'molstar/lib/mol-util/assets'
import { createMolstarViewer, createRevocableResourceRegistry, disposeMolstarViewer } from './molstar-viewer-kernel'
import { DEFAULT_CO_LIGAND_RESIDUE_ID, resolveMolstarPocketSelection, resolveMolstarViewerPreset } from '@/domain/tasks'
import { Sphere3D } from 'molstar/lib/mol-math/geometry'
import { Vec3 } from 'molstar/lib/mol-math/linear-algebra'

const { t } = useI18n()
const pocketPreset = resolveMolstarViewerPreset('pocket')
const coLigandResidueId = DEFAULT_CO_LIGAND_RESIDUE_ID
const pocketRepresentation = ref<MolstarRepresentation>(pocketPreset.primaryRepresentation)
const renderResourcesRegistry = createRevocableResourceRegistry()
const props = withDefaults(defineProps<{ pdbUrl: string; resIds: number[]; selectedResIds?: number[]; pocketCenter?: [number, number, number] | null; chain?: string }>(), { selectedResIds: () => [], pocketCenter: null, chain: 'A' })
const containerRef = ref<HTMLElement | null>(null)
const loading = ref(true)
const error = ref('')
let viewer: MolstarViewer | null = null
let plugin: any = null
let structureSel: any = null
let focusCells: any[] = []
let localSphere: { center: { x: number; y: number; z: number }; radius: number } | null = null
let resizeObserver: ResizeObserver | null = null
let creating: Promise<void> | null = null
let renderSeq = 0
let disposed = false
let keepCamera = false
let renderRunning = false
let renderQueued = false

async function ensureViewer() {
  if (viewer || disposed || !containerRef.value) return
  if (!creating) {
    creating = createMolstarViewer(containerRef.value, { allowNativeFullscreen: false, showControls: pocketPreset.showControls, backgroundColor: pocketPreset.background === 'white' ? 0xffffff : 0x0b1a2e })
      .then(created => { viewer = created; plugin = created.plugin })
      .catch(cause => { creating = null; throw cause })
  }
  await creating
}
async function addComponent(MS: any, expression: any, key: string, label: string, repr: Record<string, unknown>) {
  const comp = await plugin.builders.structure.tryCreateComponentFromExpression(structureSel, expression, key, { label })
  if (comp) await plugin.builders.structure.representation.addRepresentation(comp, repr)
  return comp
}
async function buildHighlights(selection = resolveMolstarPocketSelection({ chain: props.chain, residueIds: props.resIds, selectedResidueIds: props.selectedResIds })) {
  if (!structureSel) return
  focusCells = []
  const { MolScriptBuilder: MS } = await import('molstar/lib/mol-script/language/builder')
  const chainTest = MS.core.rel.eq([MS.ammp('auth_asym_id'), selection.chain])
  const selected = new Set(selection.selectedResidueIds)
  const residueExpr = (ids: number[]) => MS.struct.generator.atomGroups({ 'chain-test': chainTest, 'residue-test': MS.core.set.has([MS.set(...ids), MS.ammp('auth_seq_id')]) })
  const peripheral = selection.residueIds.filter((id) => !selected.has(id))
  if (peripheral.length) { const comp = await addComponent(MS, residueExpr(peripheral), 'pocket-residues', t('tasks.pocketResiduesOverlay'), { type: pocketRepresentation.value, color: 'uniform', colorParams: { value: 0xff7a45 } }); if (comp?.cell) focusCells.push(comp.cell) }
  // 图例：选中残基（球棍）
  if (selection.selectedResidueIds.length) { const comp = await addComponent(MS, residueExpr([...selection.selectedResidueIds]), 'focus-residue', t('tasks.selectedResidue'), { type: 'ball-and-stick', color: 'uniform', colorParams: { value: 0x22d3ee } }); if (comp?.cell) focusCells.push(comp.cell) }
  const lig = await addComponent(MS, residueExpr([coLigandResidueId]), 'co-ligand', t('tasks.coLigand'), { type: 'spacefill', color: 'element-symbol', size: 'uniform', sizeParams: { value: 0.5 } })
  if (lig?.cell) focusCells.push(lig.cell)
}
async function computePocketSphere(url: string, selection: { chain: string; residueIds: readonly number[] }) {
  try {
    const response = await fetch(url)
    if (!response.ok) return null
    const text = await response.text()
    const allowed = new Set(selection.residueIds)
    allowed.add(coLigandResidueId)
    let minx = Infinity, miny = Infinity, minz = Infinity, maxx = -Infinity, maxy = -Infinity, maxz = -Infinity
    for (const line of text.split(/\r?\n/)) {
      if (!line.startsWith('ATOM') && !line.startsWith('HETATM')) continue
      const ch = line.slice(21, 22).trim() || 'A'
      if (selection.chain && ch !== selection.chain) continue
      if (!allowed.has(Number(line.slice(22, 26).trim()))) continue
      const x = Number(line.slice(30, 38)), y = Number(line.slice(38, 46)), z = Number(line.slice(46, 54))
      if (![x, y, z].every(Number.isFinite)) continue
      minx = Math.min(minx, x); miny = Math.min(miny, y); minz = Math.min(minz, z); maxx = Math.max(maxx, x); maxy = Math.max(maxy, y); maxz = Math.max(maxz, z)
    }
    if (!Number.isFinite(minx)) return null
    return { center: { x: (minx + maxx) / 2, y: (miny + maxy) / 2, z: (minz + maxz) / 2 }, radius: 0.5 * Math.hypot(maxx - minx, maxy - miny, maxz - minz) * 0.72 + 2 }
  } catch { return null }
}
function cellBoundingSphere(cells: any[]) {
  let minx = Infinity, miny = Infinity, minz = Infinity, maxx = -Infinity, maxy = -Infinity, maxz = -Infinity
  let any = false
  const pos = Vec3.zero()
  for (const cell of cells) {
    const data = cell?.obj?.data
    if (!data?.units) continue
    for (const unit of data.units) {
      const elements = unit.elements
      for (let i = 0; i < elements.length; i += 1) {
        unit.conformation.position(elements[i], pos)
        any = true
        minx = Math.min(minx, pos[0]!); miny = Math.min(miny, pos[1]!); minz = Math.min(minz, pos[2]!)
        maxx = Math.max(maxx, pos[0]!); maxy = Math.max(maxy, pos[1]!); maxz = Math.max(maxz, pos[2]!)
      }
    }
  }
  if (!any) return null
  return { center: { x: (minx + maxx) / 2, y: (miny + maxy) / 2, z: (minz + maxz) / 2 }, radius: 0.5 * Math.hypot(maxx - minx, maxy - miny, maxz - minz) }
}
function focusPocket() {
  if (!plugin) return
  try {
    const sphere = localSphere ?? cellBoundingSphere(focusCells)
    if (!sphere || ![sphere.center.x, sphere.center.y, sphere.center.z, sphere.radius].every(Number.isFinite) || sphere.radius <= 0) {
      plugin.managers.camera.reset(undefined, 0)
      return
    }
    plugin.managers.camera.focusSphere(Sphere3D.create(Vec3.create(sphere.center.x, sphere.center.y, sphere.center.z), sphere.radius), { durationMs: 0 })
  } catch { /* camera focus is best-effort */ }
}
async function recolorCartoon() {
  try {
    const structures = plugin.managers.structure.hierarchy.current?.structures ?? []
    for (const structure of structures) {
      await plugin.managers.structure.component.updateRepresentationsTheme(structure.components, { color: 'uniform', colorParams: { value: 0x8b9bb4 } })
    }
  } catch { /* best-effort */ }
}
async function fadeCartoon() {
  try {
    const { setStructureTransparency } = await import('molstar/lib/mol-plugin-state/helpers/structure-transparency')
    const { StructureElement } = await import('molstar/lib/mol-model/structure')
    const structures = plugin.managers.structure.hierarchy.current?.structures ?? []
    for (const structure of structures) {
      await setStructureTransparency(plugin, structure.components, 0.62, async (root: any) => StructureElement.Loci.all(root), ['cartoon'])
    }
  } catch { /* best-effort */ }
}
async function render(options: { keepCamera?: boolean } = {}) {
  const seq = ++renderSeq
  keepCamera = Boolean(options.keepCamera)
  if (renderRunning) { renderQueued = true; return }
  renderRunning = true
  if (!keepCamera) loading.value = true
  error.value = ''
  renderResourcesRegistry.clear()
  const savedCamera = keepCamera ? plugin?.canvas3d?.camera.state : null
  try {
    if (!props.pdbUrl) { if (plugin) await plugin.clear(); return }
    await ensureViewer()
    if (seq !== renderSeq || disposed) return
    if (!plugin) throw new Error(t('tasks.visualizationFailed'))
    await plugin.clear()
    const data = await plugin.builders.data.download({ url: Asset.Url(props.pdbUrl), isBinary: false, label: 'Pocket receptor' }, { state: { isGhost: true } })
    if (seq !== renderSeq || disposed) return
    const trajectory = await plugin.builders.structure.parseTrajectory(data, 'pdb')
    const preset = await plugin.builders.structure.hierarchy.applyPreset(trajectory, 'default', { representationPreset: 'polymer-cartoon' })
    structureSel = preset?.structure ?? null
    const selection = resolveMolstarPocketSelection({ chain: props.chain, residueIds: props.resIds, selectedResidueIds: props.selectedResIds })
    localSphere = await computePocketSphere(props.pdbUrl, selection)
    if (seq !== renderSeq || disposed) return
    await recolorCartoon()
    await buildHighlights(selection)
    if (pocketRepresentation.value === 'cartoon') await fadeCartoon()
    if (seq !== renderSeq || disposed) return
    viewer?.handleResize()
    if (savedCamera) plugin.canvas3d?.camera.setState(savedCamera, 0)
    else {
      const focusSoon = window.setTimeout(() => { if (seq === renderSeq && !disposed) focusPocket() }, 400)
      const focusLater = window.setTimeout(() => { if (seq === renderSeq && !disposed) focusPocket() }, 1500)
      renderResourcesRegistry.add(() => window.clearTimeout(focusSoon))
      renderResourcesRegistry.add(() => window.clearTimeout(focusLater))
    }
  } catch (cause) { if (seq === renderSeq) error.value = cause instanceof Error ? cause.message : t('tasks.visualizationFailed') }
  finally { loading.value = false; renderRunning = false; if (renderQueued && !disposed) { renderQueued = false; void render({ keepCamera }) } }
}
onMounted(async () => { if (containerRef.value) { resizeObserver = new ResizeObserver(() => viewer?.handleResize()); resizeObserver.observe(containerRef.value) }; await render() })
watch(() => [props.pdbUrl, props.resIds, props.chain], () => { void render() }, { deep: true })
watch(pocketRepresentation, () => { if (plugin) void render({ keepCamera: true }) })
watch(() => props.selectedResIds, () => { if (plugin) void render({ keepCamera: true }) }, { deep: true })

onUnmounted(() => { disposed = true; renderSeq++; renderResourcesRegistry.clear(); resizeObserver?.disconnect(); resizeObserver = null; void Promise.resolve(creating).finally(() => { disposeMolstarViewer(viewer); viewer = null; plugin = null; structureSel = null }) })
</script>

<style scoped>
.pocket-viewer { position: relative; height: 460px; border-radius: 0 0 10px 10px; overflow: hidden; background: radial-gradient(circle at 70% 10%, rgba(87,181,231,.16), transparent 42%), linear-gradient(150deg,#06101d,#0d2038 60%,#16325b); }
.pocket-canvas { width:100%; height:100%; }
.pocket-canvas--hidden { visibility:hidden; }
.pocket-overlay { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; flex-direction:column; gap:12px; background:rgba(6,16,29,.7); color:#dbe9ff; font-size:13px; }
.pocket-overlay--error { background:rgba(6,16,29,.9); padding:24px; }
.pocket-controls { position:absolute; top:12px; right:12px; z-index:2; display:flex; align-items:center; gap:8px; }
.pocket-control, .pocket-reset { border:1px solid rgba(207,224,247,.28); border-radius:6px; background:rgba(8,20,36,.72); color:#cfe0f7; padding:5px 10px; font-size:12px; backdrop-filter:blur(4px); }
.pocket-control { display:inline-flex; align-items:center; gap:6px; }
.pocket-control select { border:0; background:transparent; color:inherit; font:inherit; }
.pocket-control option { color:#10233d; }
.pocket-reset { cursor:pointer; }
.pocket-reset:hover:not(:disabled) { border-color:#22d3ee; color:#fff; }
.pocket-reset:disabled { cursor:not-allowed; opacity:.5; }
.pocket-legend { position:absolute; right:12px; bottom:12px; display:flex; gap:14px; padding:6px 12px; border-radius:999px; background:rgba(8,20,36,.72); backdrop-filter:blur(4px); font-size:12px; color:#cfe0f7; }
.legend-item { display:inline-flex; align-items:center; gap:6px; }
.dot { width:9px; height:9px; border-radius:50%; display:inline-block; }
.dot--pocket { background:#ff7a45; } .dot--focus { background:#22d3ee; } .dot--ligand { background:#f4d03f; }
.pocket-viewer :deep(.msp-plugin), .pocket-viewer :deep(.msp-plugin-content), .pocket-viewer :deep(.msp-layout-region), .pocket-viewer :deep(.msp-layout-static) { width:100%; height:100%; }
.pocket-viewer :deep(.msp-viewport) { background:transparent; }
</style>
