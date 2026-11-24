<template>
  <div
    class="molecule-viewer"
    :class="[
      `molecule-viewer--${variant}`,
      `molecule-viewer--bg-${activeBackground}`,
    ]"
    :data-viewer-mode="effectiveMode"
  >
    <div class="viewer-stage">
      <div
        ref="containerRef"
        class="viewer-canvas"
        :class="{ 'viewer-canvas--hidden': Boolean(error) }"
      />

      <div v-if="loading" class="viewer-overlay">
        <a-spin />
        <p>{{ t('tasks.visualizationLoading') }}</p>
      </div>

      <div v-else-if="error" class="viewer-overlay viewer-overlay--error">
        <a-alert
          type="error"
          show-icon
          :message="t('tasks.visualizationFailed')"
          :description="error"
        />
      </div>

      <div class="viewer-toolbar" role="group" :aria-label="t('tasks.visualizationMode')">
        <span class="viewer-mode" :aria-label="t('tasks.visualizationMode')">{{ viewerPreset.mode }}</span>

        <template v-if="!isCompact">
          <select
            v-model="activeRepresentation"
            class="viewer-select"
            data-testid="viewer-representation-select"
            :disabled="loading || Boolean(error)"
            :aria-label="t('tasks.visualizationRepresentation')"
            :title="t('tasks.visualizationRepresentation')"
            @change="handleRepresentationChange"
          >
            <option
              v-for="rep in representationOptions"
              :key="rep"
              :value="rep"
            >
              {{ representationLabel(rep) }}
            </option>
          </select>

          <select
            v-model="activeColorTheme"
            class="viewer-select"
            data-testid="viewer-color-select"
            :disabled="loading || Boolean(error)"
            :aria-label="t('tasks.visualizationColorTheme')"
            :title="t('tasks.visualizationColorTheme')"
            @change="handleColorThemeChange"
          >
            <option
              v-for="theme in colorThemeOptions"
              :key="theme"
              :value="theme"
            >
              {{ colorThemeLabel(theme) }}
            </option>
          </select>

          <button
            class="viewer-tool-btn"
            type="button"
            data-testid="viewer-bg-toggle"
            :disabled="loading || Boolean(error)"
            :title="t('tasks.visualizationToggleBackground')"
            :aria-label="t('tasks.visualizationToggleBackground')"
            @click="toggleBackground"
          >
            {{ activeBackground === 'dark' ? t('tasks.visualizationBgDark') : t('tasks.visualizationBgWhite') }}
          </button>

          <button
            class="viewer-tool-btn"
            :class="{ 'is-active': spinEnabled }"
            type="button"
            data-testid="viewer-spin-toggle"
            :disabled="loading || Boolean(error)"
            :aria-pressed="spinEnabled"
            @click="toggleSpin"
          >
            {{ t('tasks.visualizationSpin') }}
          </button>

          <button
            v-if="availableLayers.receptor"
            class="viewer-tool-btn"
            :class="{ 'is-active': layerVisibility.receptor }"
            type="button"
            data-testid="viewer-layer-receptor"
            :disabled="loading || Boolean(error)"
            :aria-pressed="layerVisibility.receptor"
            @click="toggleLayer('receptor')"
          >
            {{ t('tasks.visualizationLayerReceptor') }}
          </button>

          <button
            v-if="availableLayers.ligand"
            class="viewer-tool-btn"
            :class="{ 'is-active': layerVisibility.ligand }"
            type="button"
            data-testid="viewer-layer-ligand"
            :disabled="loading || Boolean(error)"
            :aria-pressed="layerVisibility.ligand"
            @click="toggleLayer('ligand')"
          >
            {{ t('tasks.visualizationLayerLigand') }}
          </button>

          <button
            v-if="availableLayers.pocket"
            class="viewer-tool-btn"
            :class="{ 'is-active': layerVisibility.pocket }"
            type="button"
            data-testid="viewer-layer-pocket"
            :disabled="loading || Boolean(error)"
            :aria-pressed="layerVisibility.pocket"
            @click="toggleLayer('pocket')"
          >
            {{ t('tasks.visualizationLayerPocket') }}
          </button>

          <button
            v-if="availableLayers.voxels"
            class="viewer-tool-btn"
            :class="{ 'is-active': layerVisibility.voxels }"
            type="button"
            data-testid="viewer-layer-voxels"
            :disabled="loading || Boolean(error)"
            :aria-pressed="layerVisibility.voxels"
            @click="toggleLayer('voxels')"
          >
            {{ t('tasks.visualizationLayerVoxels') }}
          </button>

          <button
            v-if="enableNearbyResidues || effectiveMode === 'docking'"
            class="viewer-tool-btn"
            :class="{ 'is-active': nearbyActive }"
            type="button"
            data-testid="viewer-nearby-residues"
            :disabled="loading || Boolean(error) || !hasReceptorAndLigand"
            :aria-pressed="nearbyActive"
            @click="toggleNearbyResidues"
          >
            {{ t('tasks.visualizationNearbyResidues') }}
          </button>

          <button
            v-if="sequenceChains.length > 0"
            class="viewer-tool-btn"
            :class="{ 'is-active': sequenceOpen }"
            type="button"
            data-testid="viewer-sequence-toggle"
            :disabled="loading || Boolean(error)"
            :aria-pressed="sequenceOpen"
            @click="sequenceOpen = !sequenceOpen"
          >
            {{ t('tasks.visualizationSequence') }}
          </button>

          <button
            class="viewer-tool-btn"
            type="button"
            data-testid="viewer-screenshot"
            :disabled="loading || Boolean(error)"
            @click="exportScreenshot"
          >
            {{ t('tasks.visualizationScreenshot') }}
          </button>
        </template>

        <button
          class="viewer-reset"
          type="button"
          data-testid="viewer-reset"
          :disabled="loading || Boolean(error)"
          @click="resetCamera"
        >
          {{ t('tasks.visualizationResetView') }}
        </button>
      </div>
    </div>

    <SequenceSelectorBar
      v-if="!isCompact && sequenceOpen && sequenceChains.length > 0"
      :chains="sequenceChains"
      :selected-keys="selectedResidueKeys"
      :theme="activeBackground"
      @toggle-residue="handleToggleResidue"
      @focus-selection="focusSelectedResidues"
      @clear-selection="clearResidueSelection"
      @close="sequenceOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import 'molstar/build/viewer/molstar.css'

import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { Viewer as MolstarViewer } from 'molstar/lib/apps/viewer/app'
import { PluginCommands } from 'molstar/lib/mol-plugin/commands'
import { setSubtreeVisibility } from 'molstar/lib/mol-plugin/behavior/static/state'
import { PresetStructureRepresentations } from 'molstar/lib/mol-plugin-state/builder/structure/representation-preset'
import { BoxShape3D } from 'molstar/lib/mol-plugin-state/transforms/shape'
import { ShapeRepresentation3D } from 'molstar/lib/mol-plugin-state/transforms/representation'
import { OrderedSet } from 'molstar/lib/mol-data/int'
import { StructureElement, StructureProperties, Unit } from 'molstar/lib/mol-model/structure'
import { Asset } from 'molstar/lib/mol-util/assets'
import { Vec3 } from 'molstar/lib/mol-math/linear-algebra'
import { Sphere3D } from 'molstar/lib/mol-math/geometry'
import { Color } from 'molstar/lib/mol-util/color'
import {
  createMolstarViewer,
  createRevocableResourceRegistry,
  disposeMolstarViewer,
  downloadMolstarScreenshot,
  setMolstarBackgroundColor,
} from './molstar-viewer-kernel'
import SequenceSelectorBar from './SequenceSelectorBar.vue'

import {
  createNormalizedSdfObjectUrl,
  extractPolymerSequenceFromStructure,
  groupSelectedResiduesByChain,
  residueSelectionKey,
  resolveMolstarColorThemeOptions,
  resolveMolstarEffectiveColorTheme,
  resolveMolstarHierarchyPreset,
  resolveMolstarRepresentationOptions,
  resolveMolstarViewerPreset,
  toggleSequenceResidueSelection,
  type MolstarBackground,
  type MolstarColorTheme,
  type MolstarRepresentation,
  type MolstarViewerMode,
  type SequenceChain,
  type VisualizationScene,
} from '@/domain/tasks'
import type { PocketVoxelGrid } from '@/domain/tasks/pocket-voxel'
import { createProtectedObjectUrl } from '@/utils/protected-file-access'

const defaultMode: MolstarViewerMode = 'molecule'

const props = withDefaults(defineProps<{
  scene: VisualizationScene
  variant?: 'compact' | 'full'
  mode?: MolstarViewerMode
  allowNativeFullscreen?: boolean
  voxelGrid?: PocketVoxelGrid | null
  focusResidue?: { chain?: string; authSeqId: number; insertionCode?: string } | null
  enableNearbyResidues?: boolean
}>(), {
  variant: 'full',
  allowNativeFullscreen: true,
  voxelGrid: null,
  focusResidue: null,
  enableNearbyResidues: false,
})
const emit = defineEmits<{ 'residue-focus-result': [status: 'focused' | 'not-found' | 'ambiguous'] }>()

const { t } = useI18n()
const isCompact = computed(() => props.variant === 'compact')
const effectiveMode = computed<MolstarViewerMode>(() => props.mode ?? defaultMode)
const viewerPreset = computed(() => resolveMolstarViewerPreset(effectiveMode.value))

const activeRepresentation = ref<MolstarRepresentation>(viewerPreset.value.primaryRepresentation)
const activeColorTheme = ref<MolstarColorTheme>('default')
const activeBackground = ref<MolstarBackground>(viewerPreset.value.background)

const representationOptions = computed(() => resolveMolstarRepresentationOptions(effectiveMode.value))
const colorThemeOptions = computed(() => resolveMolstarColorThemeOptions(effectiveMode.value))

const containerRef = ref<HTMLElement | null>(null)
const loading = ref(true)
const error = ref('')

const sequenceChains = ref<SequenceChain[]>([])
const selectedResidueKeys = ref<string[]>([])
const lastAnchorKey = ref<string | null>(null)
const sequenceOpen = ref(false)
const spinEnabled = ref(false)
const nearbyActive = ref(false)
const layerVisibility = reactive<Record<'receptor' | 'ligand' | 'pocket' | 'voxels', boolean>>({
  receptor: true,
  ligand: true,
  pocket: true,
  voxels: true,
})
const hasReceptorAndLigand = computed(() =>
  props.scene.entries.some(entry => entry.role === 'receptor' || entry.role === 'structure') &&
  props.scene.entries.some(entry => entry.role === 'ligand'),
)
const availableLayers = computed(() => ({
  receptor: props.scene.entries.some(entry => entry.role === 'receptor' || entry.role === 'structure'),
  ligand: props.scene.entries.some(entry => entry.role === 'ligand'),
  pocket: props.scene.entries.some(entry => entry.role === 'pocket'),
  voxels: Boolean(props.voxelGrid?.boxes.length),
}))

interface LoadedEntryRecord {
  role: VisualizationScene['entries'][number]['role']
  structureRefKey: string
  isPrimaryTarget: boolean
}

let viewer: MolstarViewer | null = null
let viewerInitPromise: Promise<MolstarViewer> | null = null
let renderSeq = 0
let disposed = false
let mutationQueue: Promise<void> = Promise.resolve()
function enqueueMutation<T>(operation: () => Promise<T>): Promise<T> {
  const result = mutationQueue.then(operation, operation)
  mutationQueue = result.then(() => undefined, () => undefined)
  return result
}
let resizeObserver: ResizeObserver | null = null
const entryResourcesRegistry = createRevocableResourceRegistry()
let removeLayoutSyncListener: (() => void) | null = null
let removeClickListener: (() => void) | null = null
let loadedEntries: LoadedEntryRecord[] = []
let selectionHighlightRefs: string[] = []
let voxelRefs: string[] = []
let nearbyRefs: string[] = []
let focusHighlightRefs: string[] = []
let cachedNearbyResidues: Array<{ chain: string; authSeqId: number }> | null = null

function representationLabel(rep: MolstarRepresentation): string {
  switch (rep) {
    case 'cartoon':
      return t('tasks.visualizationCartoon')
    case 'surface':
      return t('tasks.visualizationSurface')
    case 'ball-and-stick':
      return t('tasks.visualizationBallAndStick')
    case 'spacefill':
      return t('tasks.visualizationSpacefill')
  }
}

function colorThemeLabel(theme: MolstarColorTheme): string {
  switch (theme) {
    case 'default':
      return t('tasks.visualizationColorDefault')
    case 'chain-id':
      return t('tasks.visualizationColorChain')
    case 'element-symbol':
      return t('tasks.visualizationColorElement')
    case 'secondary-structure':
      return t('tasks.visualizationColorSecondary')
    case 'uncertainty':
      return t('tasks.visualizationColorPlddt')
    case 'hydrophobicity':
      return t('tasks.visualizationColorHydrophobicity')
    case 'uniform':
      return t('tasks.visualizationColorUniform')
  }
}

function resolveUniformColor(role: VisualizationScene['entries'][number]['role']): number {
  if (role === 'pocket') return 0xf59e0b
  if (role === 'receptor') return 0x9ca3af
  return 0x38bdf8
}

function resolveColorPresetParams(
  role: VisualizationScene['entries'][number]['role'],
  themeChoice: MolstarColorTheme,
): Record<string, unknown> | undefined {
  // In pocket/docking views, default receptor theme stays neutral gray so pocket/ligand pop out.
  if (themeChoice === 'default' && role === 'receptor' && (effectiveMode.value === 'pocket' || effectiveMode.value === 'docking')) {
    return {
      theme: {
        globalName: 'uniform',
        globalColorParams: { value: Color(0x9ca3af) },
      },
    }
  }
  if (role === 'pocket' && themeChoice === 'default') {
    return {
      theme: {
        globalName: 'uniform',
        globalColorParams: { value: Color(0xf59e0b) },
      },
    }
  }
  const effectiveTheme = resolveMolstarEffectiveColorTheme(effectiveMode.value, themeChoice)
  if (effectiveTheme === 'uniform') {
    return {
      theme: {
        globalName: 'uniform',
        globalColorParams: { value: Color(resolveUniformColor(role)) },
      },
    }
  }
  return {
    theme: {
      globalName: effectiveTheme,
    },
  }
}

function syncFullscreenLayout() {
  if (!viewer || !props.allowNativeFullscreen) {
    return
  }

  const layoutState = viewer.plugin.layout.state

  if (layoutState.expandToFullscreen && !layoutState.isExpanded) {
    void PluginCommands.Layout.Update(viewer.plugin, {
      state: {
        isExpanded: true,
        expandToFullscreen: true,
      },
    })
    return
  }

  if (!layoutState.expandToFullscreen && layoutState.isExpanded) {
    void PluginCommands.Layout.Update(viewer.plugin, {
      state: {
        isExpanded: false,
      },
    })
  }
}

function isPrimaryTargetEntry(role: VisualizationScene['entries'][number]['role']): boolean {
  if (effectiveMode.value === 'molecule') {
    return role === 'ligand' || role === 'structure'
  }
  return role === 'receptor' || role === 'structure'
}

async function applyRepresentationToStructureRef(
  currentViewer: MolstarViewer,
  structureRef: any,
  role: VisualizationScene['entries'][number]['role'],
  rep: MolstarRepresentation,
  themeChoice: MolstarColorTheme,
) {
  const themeParams = resolveColorPresetParams(role, themeChoice) as any
  if (rep === 'spacefill') {
    const { MolScriptBuilder: MS } = await import('molstar/lib/mol-script/language/builder')
    await currentViewer.plugin.managers.structure.component.clear([structureRef])
    const comp = await currentViewer.plugin.builders.structure.tryCreateComponentFromExpression(
      structureRef.cell,
      MS.struct.generator.all(),
      `primary-spacefill-${structureRef.cell.transform.ref}`,
      { label: 'Spacefill' },
    )
    if (comp) {
      const globalTheme = themeParams?.theme
      await currentViewer.plugin.builders.structure.representation.addRepresentation(comp, {
        type: 'spacefill',
        color: globalTheme?.globalName ?? 'element-symbol',
        ...(globalTheme?.globalColorParams ? { colorParams: globalTheme.globalColorParams } : {}),
      } as any)
    }
    return
  }

  const presetKey = resolveMolstarHierarchyPreset(rep)
  const provider = PresetStructureRepresentations[presetKey]
  await currentViewer.plugin.managers.structure.component.applyPreset(
    [structureRef],
    provider,
    themeParams,
  )
}

async function loadEntryStructure(
  currentViewer: MolstarViewer,
  entry: VisualizationScene['entries'][number],
  url: string,
): Promise<LoadedEntryRecord | null> {
  const data = await currentViewer.plugin.builders.data.download(
    {
      url: Asset.Url(url),
      isBinary: false,
      label: entry.label,
    },
    { state: { isGhost: true } },
  )
  const trajectory = await currentViewer.plugin.builders.structure.parseTrajectory(data, entry.format)

  if (entry.role === 'pocket') {
    // 口袋残基也用卡通渲染：球棍（atomic-detail）在每个原子上画球，口袋动辄上百个残基，
    // 叠在卡通蛋白上会糊成一团、把完整蛋白整个盖住。卡通 + 单色反而更容易看出口袋位置。
    const preset = await currentViewer.plugin.builders.structure.hierarchy.applyPreset(trajectory, 'default', {
      representationPreset: 'polymer-cartoon',
      representationPresetParams: {
        theme: { globalName: 'uniform', globalColorParams: { value: Color(0xf59e0b) } },
      },
    })
    const ref = preset?.structure?.ref
    return ref ? { role: entry.role, structureRefKey: ref, isPrimaryTarget: false } : null
  }

  const primaryTarget = isPrimaryTargetEntry(entry.role)
  const initialRep: MolstarRepresentation = primaryTarget
    ? activeRepresentation.value
    : entry.role === 'ligand'
      ? 'ball-and-stick'
      : viewerPreset.value.primaryRepresentation
  const presetName = resolveMolstarHierarchyPreset(initialRep)
  const themeParams = primaryTarget
    ? resolveColorPresetParams(entry.role, activeColorTheme.value)
    : undefined

  const preset = await currentViewer.plugin.builders.structure.hierarchy.applyPreset(trajectory, 'default', {
    representationPreset: presetName,
    ...(themeParams ? { representationPresetParams: themeParams } : {}),
  })

  const structureRefKey = preset?.structure?.ref ?? ''
  if (primaryTarget && initialRep === 'spacefill' && structureRefKey) {
    const structureRef = currentViewer.plugin.managers.structure.hierarchy.current.structures.find(
      s => s.cell.transform.ref === structureRefKey,
    )
    if (structureRef) {
      await applyRepresentationToStructureRef(
        currentViewer,
        structureRef,
        entry.role,
        'spacefill',
        activeColorTheme.value,
      )
    }
  }

  return structureRefKey
    ? { role: entry.role, structureRefKey, isPrimaryTarget: primaryTarget }
    : null
}

async function addVoxelGrid(currentViewer: MolstarViewer, grid: PocketVoxelGrid) {
  const state = currentViewer.plugin.state.data.build()
  const color = Color(grid.color ?? 0x22d3ee)
  const radius = grid.radius ?? 0.05
  const createdRefs: string[] = []

  for (const box of grid.boxes) {
    const [x, y, z] = box.center
    const half = box.halfSize
    const shape = state.toRoot().apply(BoxShape3D, {
      bottomLeft: Vec3.create(x - half, y - half, z - half),
      topRight: Vec3.create(x + half, y + half, z + half),
      radius,
      color,
    })
    createdRefs.push(shape.ref)
    shape.apply(ShapeRepresentation3D, {})
  }

  await state.commit()
  voxelRefs = createdRefs

  let minX = Number.POSITIVE_INFINITY
  let minY = Number.POSITIVE_INFINITY
  let minZ = Number.POSITIVE_INFINITY
  let maxX = Number.NEGATIVE_INFINITY
  let maxY = Number.NEGATIVE_INFINITY
  let maxZ = Number.NEGATIVE_INFINITY
  for (const box of grid.boxes) {
    const [x, y, z] = box.center
    minX = Math.min(minX, x)
    minY = Math.min(minY, y)
    minZ = Math.min(minZ, z)
    maxX = Math.max(maxX, x)
    maxY = Math.max(maxY, y)
    maxZ = Math.max(maxZ, z)
  }

  if (Number.isFinite(minX)) {
    const center = Vec3.create((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2)
    const radius = Math.max(maxX - minX, maxY - minY, maxZ - minZ) / 2 + 8
    currentViewer.plugin.managers.camera.focusSphere(Sphere3D.create(center, radius), { durationMs: 0 })
  }
}

function collectPolymerSequences(currentViewer: MolstarViewer): SequenceChain[] {
  const structures = currentViewer.plugin.managers.structure.hierarchy.current.structures
  const primaryRefs = new Set(
    loadedEntries.filter(record => record.isPrimaryTarget).map(record => record.structureRefKey),
  )

  const chainsById = new Map<string, SequenceChain>()
  const chainOrder: string[] = []

  for (const sRef of structures) {
    if (primaryRefs.size > 0 && !primaryRefs.has(sRef.cell.transform.ref)) {
      continue
    }
    const structureData = sRef.cell.obj?.data
    if (!structureData) {
      continue
    }
    const extracted = extractPolymerSequenceFromStructure(structureData)
    for (const chain of extracted) {
      if (!chainsById.has(chain.chain)) {
        chainsById.set(chain.chain, { chain: chain.chain, residues: [...chain.residues] })
        chainOrder.push(chain.chain)
      }
    }
  }

  return chainOrder.map(chainId => chainsById.get(chainId)!)
}

async function clearSelectionHighlights(currentViewer: MolstarViewer) {
  if (!selectionHighlightRefs.length) {
    return
  }
  const update = currentViewer.plugin.state.data.build()
  for (const ref of selectionHighlightRefs) {
    update.delete(ref)
  }
  selectionHighlightRefs = []
  await update.commit()
}

async function syncSelectedResiduesHighlight() {
  if (!viewer) {
    return
  }
  const currentViewer = viewer
  const savedCamera = currentViewer.plugin.canvas3d?.camera.getSnapshot()
  await clearSelectionHighlights(currentViewer)

  const groups = groupSelectedResiduesByChain(selectedResidueKeys.value)
  if (!groups.length) {
    if (savedCamera) {
      currentViewer.plugin.managers.camera.setSnapshot(savedCamera, 0)
    }
    return
  }

  const { MolScriptBuilder: MS } = await import('molstar/lib/mol-script/language/builder')
  const primaryRefs = new Set(
    loadedEntries.filter(record => record.isPrimaryTarget).map(record => record.structureRefKey),
  )
  const targetStructures = currentViewer.plugin.managers.structure.hierarchy.current.structures.filter(
    sRef => primaryRefs.size === 0 || primaryRefs.has(sRef.cell.transform.ref),
  )

  const createdRefs: string[] = []
  for (const sRef of targetStructures) {
    for (const group of groups) {
      const expr = MS.struct.generator.atomGroups({
        'chain-test': MS.core.rel.eq([MS.ammp('auth_asym_id'), group.chain]),
        'residue-test': MS.core.set.has([MS.set(...group.seqIds), MS.ammp('auth_seq_id')]),
      })
      const comp = await currentViewer.plugin.builders.structure.tryCreateComponentFromExpression(
        sRef.cell,
        expr,
        `seq-selection-${sRef.cell.transform.ref}-${group.chain}`,
        { label: `Selected ${group.chain}` },
      )
      if (comp) {
        createdRefs.push(comp.ref)
        await currentViewer.plugin.builders.structure.representation.addRepresentation(comp, {
          type: 'ball-and-stick',
          color: 'uniform',
          colorParams: { value: Color(0x22d3ee) },
        } as any)
      }
    }
  }
  selectionHighlightRefs = createdRefs

  if (savedCamera) {
    currentViewer.plugin.managers.camera.setSnapshot(savedCamera, 0)
  }
}

function focusSelectedResidues() {
  if (!viewer || !selectionHighlightRefs.length) {
    return
  }
  const state = viewer.plugin.state.data
  let minX = Infinity
  let minY = Infinity
  let minZ = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  let maxZ = -Infinity
  let found = false
  const pos = Vec3.zero()

  for (const ref of selectionHighlightRefs) {
    const cell = state.cells.get(ref)
    const structureData = cell?.obj?.data
    if (!structureData?.units) {
      continue
    }
    for (const unit of structureData.units) {
      const elements = unit.elements
      for (let i = 0; i < elements.length; i += 1) {
        unit.conformation.position(elements[i]!, pos)
        const px = pos[0] ?? 0
        const py = pos[1] ?? 0
        const pz = pos[2] ?? 0
        found = true
        if (px < minX) minX = px
        if (py < minY) minY = py
        if (pz < minZ) minZ = pz
        if (px > maxX) maxX = px
        if (py > maxY) maxY = py
        if (pz > maxZ) maxZ = pz
      }
    }
  }

  if (!found) {
    return
  }

  const center = Vec3.create((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2)
  const radius = Math.max(0.5 * Math.hypot(maxX - minX, maxY - minY, maxZ - minZ) + 4, 6)
  viewer.plugin.managers.camera.focusSphere(Sphere3D.create(center, radius), { durationMs: 250 })
}

function handleToggleResidue(payload: { chain: string; seqId: number; shiftKey: boolean }) {
  const next = toggleSequenceResidueSelection({
    chains: sequenceChains.value,
    currentSelectedKeys: selectedResidueKeys.value,
    clickedChain: payload.chain,
    clickedSeqId: payload.seqId,
    lastAnchorKey: lastAnchorKey.value,
    shiftKey: payload.shiftKey,
  })
  selectedResidueKeys.value = next.selectedKeys
  lastAnchorKey.value = next.anchorKey
  void syncSelectedResiduesHighlight()
}

function clearResidueSelection() {
  if (!selectedResidueKeys.value.length) {
    return
  }
  selectedResidueKeys.value = []
  lastAnchorKey.value = null
  void syncSelectedResiduesHighlight()
}

async function handleRepresentationChange() {
  if (!viewer || !loadedEntries.length) {
    return
  }
  const currentViewer = viewer
  const savedCamera = currentViewer.plugin.canvas3d?.camera.getSnapshot()
  const targetRecords = loadedEntries.filter(record => record.isPrimaryTarget)
  nearbyRefs = []
  nearbyActive.value = false
  focusHighlightRefs = []

  for (const record of targetRecords) {
    const structureRef = currentViewer.plugin.managers.structure.hierarchy.current.structures.find(
      s => s.cell.transform.ref === record.structureRefKey,
    )
    if (!structureRef) {
      continue
    }
    await applyRepresentationToStructureRef(
      currentViewer,
      structureRef,
      record.role,
      activeRepresentation.value,
      activeColorTheme.value,
    )
  }

  await syncSelectedResiduesHighlight()
  if (savedCamera) {
    currentViewer.plugin.managers.camera.setSnapshot(savedCamera, 0)
  }
}

async function handleColorThemeChange() {
  if (!viewer || !loadedEntries.length) {
    return
  }
  const currentViewer = viewer
  const savedCamera = currentViewer.plugin.canvas3d?.camera.getSnapshot()
  const targetRecords = loadedEntries.filter(record => record.isPrimaryTarget)

  for (const record of targetRecords) {
    const structureRef = currentViewer.plugin.managers.structure.hierarchy.current.structures.find(
      s => s.cell.transform.ref === record.structureRefKey,
    )
    if (!structureRef) {
      continue
    }
    const themeParams = resolveColorPresetParams(record.role, activeColorTheme.value) as
      | { theme?: { globalName?: string; globalColorParams?: unknown } }
      | undefined
    const globalTheme = themeParams?.theme
    if (globalTheme?.globalName) {
      await currentViewer.plugin.managers.structure.component.updateRepresentationsTheme(
        structureRef.components,
        {
          color: globalTheme.globalName as any,
          ...(globalTheme.globalColorParams ? { colorParams: globalTheme.globalColorParams } : {}),
        },
      )
    }
  }

  await syncSelectedResiduesHighlight()
  if (savedCamera) {
    currentViewer.plugin.managers.camera.setSnapshot(savedCamera, 0)
  }
}

function toggleBackground() {
  activeBackground.value = activeBackground.value === 'dark' ? 'white' : 'dark'
  setMolstarBackgroundColor(viewer, activeBackground.value)
}

function toggleSpin() {
  spinEnabled.value = !spinEnabled.value
  if (!viewer) return
  try {
    viewer.plugin.canvas3d?.setProps({
      trackball: {
        animate: spinEnabled.value
          ? { name: 'spin', params: { speed: 1 } }
          : { name: 'off', params: {} },
      },
    } as any)
  } catch {
    // Trackball spin is best-effort and must not reset camera.
  }
}

function toggleLayer(layer: 'receptor' | 'ligand' | 'pocket' | 'voxels') {
  layerVisibility[layer] = !layerVisibility[layer]
  if (!viewer) return
  const hidden = !layerVisibility[layer]
  const refs = layer === 'voxels'
    ? voxelRefs
    : loadedEntries
        .filter(record =>
          layer === 'receptor'
            ? record.role === 'receptor' || record.role === 'structure'
            : record.role === layer,
        )
        .map(record => record.structureRefKey)
  for (const ref of refs) {
    if (viewer.plugin.state.data?.transforms?.get?.(ref)) {
      setSubtreeVisibility(viewer.plugin.state.data, ref, hidden)
    }
  }
}

function isHeavyAtom(unit: any, element: any): boolean {
  try {
    if (Unit.isAtomic(unit)) {
      const idx = unit.model.atomicHierarchy.atoms.type_symbol
      const sym = idx?.value?.(element)
      if (typeof sym === 'string') return sym.toUpperCase() !== 'H' && sym.toUpperCase() !== 'D'
    }
  } catch { /* fall through */ }
  return true
}

function computeNearbyResidues(currentViewer: MolstarViewer): Array<{ chain: string; authSeqId: number }> {
  const structures = currentViewer.plugin.managers.structure.hierarchy.current.structures
  const receptorKeys = new Set(loadedEntries.filter(r => r.role === 'receptor' || r.role === 'structure').map(r => r.structureRefKey))
  const ligandKeys = new Set(loadedEntries.filter(r => r.role === 'ligand').map(r => r.structureRefKey))
  const ligandCoords: Array<[number, number, number]> = []
  const pos = Vec3.zero()

  for (const sRef of structures) {
    if (!ligandKeys.has(sRef.cell.transform.ref)) continue
    const data = sRef.cell.obj?.data
    if (!data?.units) continue
    for (const unit of data.units) {
      const elements = unit.elements
      for (let i = 0; i < elements.length; i += 1) {
        if (!isHeavyAtom(unit, elements[i])) continue
        unit.conformation.position(elements[i]!, pos)
        ligandCoords.push([pos[0] ?? 0, pos[1] ?? 0, pos[2] ?? 0])
      }
    }
  }
  if (!ligandCoords.length) return []

  const matched = new Map<string, { chain: string; authSeqId: number }>()
  const limitSq = 25
  for (const sRef of structures) {
    if (!receptorKeys.has(sRef.cell.transform.ref)) continue
    const data = sRef.cell.obj?.data
    if (!data?.units) continue
    for (const unit of data.units) {
      if (!Unit.isAtomic(unit)) continue
      const elements = unit.elements
      for (let i = 0; i < elements.length; i += 1) {
        const el = elements[i]!
        if (!isHeavyAtom(unit, el)) continue
        const loc = StructureElement.Location.create(data, unit, el)
        if (StructureProperties.entity.type(loc) !== 'polymer') continue
        unit.conformation.position(el, pos)
        const px = pos[0] ?? 0
        const py = pos[1] ?? 0
        const pz = pos[2] ?? 0
        for (const [lx, ly, lz] of ligandCoords) {
          const dx = px - lx
          const dy = py - ly
          const dz = pz - lz
          if (dx * dx + dy * dy + dz * dz <= limitSq) {
            const chain = StructureProperties.chain.auth_asym_id(loc) || StructureProperties.chain.label_asym_id(loc) || 'A'
            const authSeqId = StructureProperties.residue.auth_seq_id(loc)
            matched.set(`${chain}:${authSeqId}`, { chain, authSeqId })
            break
          }
        }
      }
    }
  }
  return Array.from(matched.values())
}

async function toggleNearbyResidues() {
  if (!viewer || !hasReceptorAndLigand.value) {
    message.warning(t('tasks.visualizationNearbyUnavailable'))
    return
  }
  nearbyActive.value = !nearbyActive.value
  const visible = nearbyActive.value
  await enqueueMutation(async () => {
    if (!viewer || disposed) return
    if (nearbyRefs.length) {
      for (const ref of nearbyRefs) {
        if (viewer.plugin.state.data?.transforms?.get?.(ref)) {
          setSubtreeVisibility(viewer.plugin.state.data, ref, !visible)
        }
      }
      return
    }
    if (!visible) return
    if (cachedNearbyResidues === null) cachedNearbyResidues = computeNearbyResidues(viewer)
    if (!cachedNearbyResidues.length) {
      nearbyActive.value = false
      message.info(t('tasks.visualizationNearbyEmpty'))
      return
    }
    const { MolScriptBuilder: MS } = await import('molstar/lib/mol-script/language/builder')
    const receptorRefs = new Set(loadedEntries.filter(r => r.role === 'receptor' || r.role === 'structure').map(r => r.structureRefKey))
    const byChain = new Map<string, number[]>()
    for (const item of cachedNearbyResidues) byChain.set(item.chain, [...(byChain.get(item.chain) ?? []), item.authSeqId])
    const createdRefs: string[] = []
    for (const sRef of viewer.plugin.managers.structure.hierarchy.current.structures) {
      if (!receptorRefs.has(sRef.cell.transform.ref)) continue
      for (const [chain, ids] of byChain.entries()) {
        const expr = MS.struct.generator.atomGroups({
          'chain-test': MS.core.rel.eq([MS.ammp('auth_asym_id'), chain]),
          'residue-test': MS.core.set.has([MS.set(...ids), MS.ammp('auth_seq_id')]),
        })
        const comp = await viewer.plugin.builders.structure.tryCreateComponentFromExpression(
          sRef.cell, expr, `nearby-${sRef.cell.transform.ref}-${chain}`, { label: `Nearby ${chain}` },
        )
        if (comp) {
          createdRefs.push(comp.ref)
          await viewer.plugin.builders.structure.representation.addRepresentation(comp, {
            type: 'ball-and-stick', color: 'uniform', colorParams: { value: Color(0xfbbf24) },
          } as any)
        }
      }
    }
    nearbyRefs = createdRefs
  })
}

async function applyFocusResidue(target: { chain?: string; authSeqId: number; insertionCode?: string } | null) {
  await enqueueMutation(async () => {
    if (!viewer || disposed) return
    if (focusHighlightRefs.length) {
      const update = viewer.plugin.state.data.build()
      for (const ref of focusHighlightRefs) update.delete(ref)
      focusHighlightRefs = []
      await update.commit()
    }
    if (!target) return
    const receptorRefs = new Set(loadedEntries.filter(r => r.role === 'receptor' || r.role === 'structure').map(r => r.structureRefKey))
    const candidates = new Map<string, { chain: string; authSeqId: number; points: Array<[number, number, number]>; sRef: any }>()
    const pos = Vec3.zero()
    for (const sRef of viewer.plugin.managers.structure.hierarchy.current.structures) {
      if (receptorRefs.size > 0 && !receptorRefs.has(sRef.cell.transform.ref)) continue
      const data = sRef.cell.obj?.data
      if (!data?.units) continue
      for (const unit of data.units) {
        if (!Unit.isAtomic(unit)) continue
        for (let i = 0; i < unit.elements.length; i += 1) {
          const el = unit.elements[i]!
          const loc = StructureElement.Location.create(data, unit, el)
          if (StructureProperties.entity.type(loc) !== 'polymer') continue
          const seqId = StructureProperties.residue.auth_seq_id(loc)
          if (seqId !== target.authSeqId) continue
          const chain = StructureProperties.chain.auth_asym_id(loc) || StructureProperties.chain.label_asym_id(loc) || 'A'
          if (target.chain && chain !== target.chain) continue
          const ins = StructureProperties.residue.pdbx_PDB_ins_code(loc) || ''
          if (target.insertionCode && ins !== target.insertionCode) continue
          unit.conformation.position(el, pos)
          const key = `${sRef.cell.transform.ref}:${chain}:${seqId}:${ins}`
          const entry = candidates.get(key) ?? { chain, authSeqId: seqId, points: [], sRef }
          entry.points.push([pos[0] ?? 0, pos[1] ?? 0, pos[2] ?? 0])
          candidates.set(key, entry)
        }
      }
    }
    if (candidates.size === 0) { emit('residue-focus-result', 'not-found'); return }
    if (candidates.size > 1) { emit('residue-focus-result', 'ambiguous'); return }
    const hit = Array.from(candidates.values())[0]!
    const { MolScriptBuilder: MS } = await import('molstar/lib/mol-script/language/builder')
    const expr = MS.struct.generator.atomGroups({
      'chain-test': MS.core.rel.eq([MS.ammp('auth_asym_id'), hit.chain]),
      'residue-test': MS.core.rel.eq([MS.ammp('auth_seq_id'), hit.authSeqId]),
    })
    const comp = await viewer.plugin.builders.structure.tryCreateComponentFromExpression(
      hit.sRef.cell, expr, `focus-residue-${hit.chain}-${hit.authSeqId}`, { label: `Focus ${hit.chain}:${hit.authSeqId}` },
    )
    if (comp) {
      focusHighlightRefs = [comp.ref]
      await viewer.plugin.builders.structure.representation.addRepresentation(comp, {
        type: 'ball-and-stick', color: 'uniform', colorParams: { value: Color(0x22d3ee) },
      } as any)
    }
    let minX = Infinity, minY = Infinity, minZ = Infinity, maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity
    for (const [px, py, pz] of hit.points) {
      minX = Math.min(minX, px); minY = Math.min(minY, py); minZ = Math.min(minZ, pz)
      maxX = Math.max(maxX, px); maxY = Math.max(maxY, py); maxZ = Math.max(maxZ, pz)
    }
    if (Number.isFinite(minX)) {
      const center = Vec3.create((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2)
      const radius = Math.max(0.5 * Math.hypot(maxX - minX, maxY - minY, maxZ - minZ) + 4, 6)
      viewer.plugin.managers.camera.focusSphere(Sphere3D.create(center, radius), { durationMs: 250 })
    }
    emit('residue-focus-result', 'focused')
  })
}

async function exportScreenshot() {
  const firstLabel = props.scene.entries[0]?.label || 'structure'
  const safeName = firstLabel.replace(/[^a-zA-Z0-9._-]+/g, '_')
  const ok = await downloadMolstarScreenshot(viewer, `${safeName}.png`)
  if (ok) {
    message.success(t('tasks.visualizationScreenshotSuccess'))
  } else {
    message.warning(t('tasks.visualizationScreenshotFailed'))
  }
}

async function ensureViewer(): Promise<MolstarViewer | null> {
  if (viewer) return viewer
  if (disposed || !containerRef.value) return null
  if (!viewerInitPromise) {
    viewerInitPromise = createMolstarViewer(containerRef.value, {
      allowNativeFullscreen: props.allowNativeFullscreen,
      showControls: viewerPreset.value.showControls,
      backgroundColor: activeBackground.value === 'white' ? 0xffffff : 0x0b1a2e,
    }).then(created => {
      viewer = created
      const layoutSub = created.plugin.layout.events.updated.subscribe(syncFullscreenLayout)
      removeLayoutSyncListener = () => layoutSub.unsubscribe()
      const clickSub = created.plugin.behaviors.interaction.click.subscribe(event => {
        if (isCompact.value || !sequenceChains.value.length) return
        const loci = event.current.loci
        if (!StructureElement.Loci.is(loci) || loci.elements.length === 0) return
        const first = loci.elements[0]!
        if (!Unit.isAtomic(first.unit) || OrderedSet.size(first.indices) === 0) return
        const elementIndex = OrderedSet.getAt(first.indices, 0)
        const element = first.unit.elements[elementIndex]
        if (element === undefined) return
        const loc = StructureElement.Location.create(loci.structure, first.unit, element)
        if (StructureProperties.entity.type(loc) !== 'polymer') return
        const chain = StructureProperties.chain.auth_asym_id(loc) || StructureProperties.chain.label_asym_id(loc) || 'A'
        const seqId = StructureProperties.residue.auth_seq_id(loc)
        const key = residueSelectionKey(chain, seqId)
        if (!sequenceChains.value.some(c => c.chain === chain && c.residues.some(r => r.key === key))) return
        handleToggleResidue({ chain, seqId, shiftKey: Boolean((event.modifiers as { shift?: boolean } | undefined)?.shift) })
      })
      removeClickListener = () => clickSub.unsubscribe()
      return created
    }).catch(cause => { viewerInitPromise = null; throw cause })
  }
  return viewerInitPromise
}

function resetCamera() {
  if (!viewer) return
  viewer.plugin.managers.camera.reset(undefined, 300)
}

async function renderScene() {
  const seq = ++renderSeq
  loading.value = true
  error.value = ''
  entryResourcesRegistry.clear()
  loadedEntries = []
  selectionHighlightRefs = []
  voxelRefs = []
  nearbyRefs = []
  focusHighlightRefs = []
  cachedNearbyResidues = null
  nearbyActive.value = false
  layerVisibility.receptor = true
  layerVisibility.ligand = true
  layerVisibility.pocket = true
  layerVisibility.voxels = true
  sequenceChains.value = []
  selectedResidueKeys.value = []
  lastAnchorKey.value = null
  try {
    await enqueueMutation(async () => {
      if (seq !== renderSeq || disposed) return
      const currentViewer = await ensureViewer()
      if (seq !== renderSeq || disposed) return
      if (!props.scene.entries.length) {
        if (currentViewer) await currentViewer.plugin.clear()
        return
      }
      if (!currentViewer) throw new Error('Mol* viewer unavailable')
      await currentViewer.plugin.clear()
      if (seq !== renderSeq || disposed) return
      setMolstarBackgroundColor(currentViewer, activeBackground.value)
      for (const entry of props.scene.entries) {
        const resource = entry.format === 'sdf'
          ? await createNormalizedSdfObjectUrl(entry.url, entry.sdfRecordIndex !== undefined && !entry.sdfRecordScoped ? { recordIndex: entry.sdfRecordIndex } : {})
          : await createProtectedObjectUrl(entry.url)
        entryResourcesRegistry.add(resource.revoke)
        if (seq !== renderSeq || disposed) return
        const loaded = await loadEntryStructure(currentViewer, entry, resource.url)
        if (seq !== renderSeq || disposed) return
        if (loaded) loadedEntries.push(loaded)
      }
      if (props.voxelGrid?.boxes.length) await addVoxelGrid(currentViewer, props.voxelGrid)
      if (seq !== renderSeq || disposed) return
      sequenceChains.value = collectPolymerSequences(currentViewer)
      if (!isCompact.value && sequenceChains.value.length) sequenceOpen.value = true
      currentViewer.handleResize()
    })
  } catch (cause) {
    if (seq === renderSeq) error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    if (seq === renderSeq) loading.value = false
  }
}

watch(effectiveMode, nextMode => {
  const preset = resolveMolstarViewerPreset(nextMode)
  activeRepresentation.value = preset.primaryRepresentation
  activeColorTheme.value = 'default'
})

onMounted(async () => {
  if (containerRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      viewer?.handleResize()
    })
    resizeObserver.observe(containerRef.value)
  }

  await renderScene()
})

watch(
  () => [props.scene.entries, props.voxelGrid, props.mode],
  () => {
    void renderScene()
  },
  { deep: true },
)

watch(
  () => props.focusResidue,
  next => {
    void applyFocusResidue(next ?? null)
  },
  { deep: true },
)

onUnmounted(() => {
  disposed = true
  renderSeq += 1
  entryResourcesRegistry.clear()
  resizeObserver?.disconnect()
  removeLayoutSyncListener?.()
  removeLayoutSyncListener = null
  removeClickListener?.()
  removeClickListener = null
  void Promise.resolve(viewerInitPromise).finally(() => {
    disposeMolstarViewer(viewer)
    viewer = null
  })
})
</script>

<style scoped lang="less">
.molecule-viewer {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 520px;
  height: 520px;
  border-radius: 20px;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(87, 181, 231, 0.22), transparent 38%),
    linear-gradient(145deg, #07111f, #10233f 58%, #17345f);
}

.molecule-viewer--bg-white {
  background: #ffffff;
  border: 1px solid rgba(15, 23, 42, 0.12);
}

.molecule-viewer--compact {
  width: 100%;
  height: 100%;
  min-height: 100%;
  border-radius: 8px;
}

.molecule-viewer--full {
  min-height: 540px;
  height: 540px;
}

.viewer-stage {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  width: 100%;
}

.viewer-canvas {
  width: 100%;
  min-height: 100%;
  height: 100%;
}

.viewer-canvas--hidden {
  visibility: hidden;
}

.viewer-toolbar {
  position: absolute;
  top: @spacing-sm;
  right: @spacing-sm;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-items: center;
  gap: @spacing-xs;
  max-width: calc(100% - 16px);
}

.viewer-mode {
  padding: 3px 8px;
  border: 1px solid rgba(255, 255, 255, 0.24);
  border-radius: 6px;
  color: rgba(255, 255, 255, 0.9);
  background: rgba(8, 15, 30, 0.72);
  font-size: 11px;
  font-weight: 600;
  text-transform: capitalize;
  backdrop-filter: blur(4px);
}

.viewer-select,
.viewer-tool-btn,
.viewer-reset {
  height: 26px;
  padding: 0 8px;
  border: 1px solid rgba(207, 224, 247, 0.28);
  border-radius: 6px;
  background: rgba(8, 20, 36, 0.76);
  color: #e2e8f0;
  cursor: pointer;
  font-size: 12px;
  line-height: 24px;
  backdrop-filter: blur(4px);
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.viewer-select {
  padding-right: 6px;
}

.viewer-tool-btn.is-active {
  border-color: #38bdf8;
  background: rgba(14, 116, 144, 0.85);
  color: #ffffff;
}

.molecule-viewer--bg-white .viewer-mode,
.molecule-viewer--bg-white .viewer-select,
.molecule-viewer--bg-white .viewer-tool-btn,
.molecule-viewer--bg-white .viewer-reset {
  border-color: rgba(15, 23, 42, 0.18);
  background: rgba(255, 255, 255, 0.92);
  color: #0f172a;
}

.molecule-viewer--bg-white .viewer-tool-btn.is-active {
  border-color: #0284c7;
  background: #0284c7;
  color: #ffffff;
}

.viewer-select:disabled,
.viewer-tool-btn:disabled,
.viewer-reset:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.viewer-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  background: rgba(7, 17, 31, 0.68);
  color: #f3f7ff;
  text-align: center;
}

.viewer-overlay--error {
  background: rgba(7, 17, 31, 0.86);
}

.viewer-overlay p {
  margin: 0;
  font-size: 14px;
}

.molecule-viewer :deep(.msp-plugin),
.molecule-viewer :deep(.msp-plugin-content),
.molecule-viewer :deep(.msp-layout-region),
.molecule-viewer :deep(.msp-layout-static) {
  width: 100%;
  min-height: 100%;
  height: 100%;
}

.molecule-viewer :deep(.msp-layout-expanded),
.molecule-viewer :deep(.msp-layout-expanded .msp-layout-main),
.molecule-viewer :deep(.msp-layout-expanded .msp-layout-static),
.molecule-viewer :deep(.msp-viewport-expanded) {
  min-height: 100dvh;
  height: 100dvh;
  z-index: 1100;
}

.molecule-viewer :deep(.msp-viewport) {
  background: transparent;
}
</style>
