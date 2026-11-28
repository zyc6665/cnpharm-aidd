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
        <span class="viewer-mode" :aria-label="t('tasks.visualizationMode')">{{ t(`tasks.visualizationModes.${viewerPreset.mode}`) }}</span>

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
          class="viewer-reset"
          type="button"
          data-testid="viewer-reset"
          :disabled="loading || Boolean(error)"
          @click="resetCamera"
        >
          {{ t('tasks.visualizationResetView') }}
        </button>
      </div>

      <div
        v-if="showTrajectoryBar"
        class="viewer-traj-bar"
        role="group"
        :aria-label="t('tasks.visualizationTrajectoryControls')"
        data-testid="viewer-traj-bar"
      >
        <button
          class="viewer-traj-btn viewer-traj-btn--play"
          type="button"
          data-testid="viewer-traj-play"
          :aria-pressed="isPlaying"
          :aria-label="isPlaying ? t('tasks.visualizationTrajectoryPause') : t('tasks.visualizationTrajectoryPlay')"
          :disabled="loading || Boolean(error)"
          @click="togglePlayback"
        >
          {{ isPlaying ? t('tasks.visualizationTrajectoryPause') : t('tasks.visualizationTrajectoryPlay') }}
        </button>
        <button
          class="viewer-traj-btn"
          type="button"
          data-testid="viewer-traj-prev"
          :aria-label="t('tasks.visualizationTrajectoryPrev')"
          :title="t('tasks.visualizationTrajectoryPrev')"
          :disabled="loading || Boolean(error)"
          @click="goPreviousFrame"
        >
          ‹
        </button>
        <input
          ref="trajSliderRef"
          class="viewer-traj-slider"
          type="range"
          data-testid="viewer-traj-slider"
          :min="0"
          :max="Math.max(0, trajectoryFrameCount - 1)"
          step="1"
          :value="currentFrameIndex"
          :disabled="loading || Boolean(error)"
          :aria-label="t('tasks.visualizationTrajectorySlider')"
          @input="handleSliderInput"
        />
        <button
          class="viewer-traj-btn"
          type="button"
          data-testid="viewer-traj-next"
          :aria-label="t('tasks.visualizationTrajectoryNext')"
          :title="t('tasks.visualizationTrajectoryNext')"
          :disabled="loading || Boolean(error)"
          @click="goNextFrame"
        >
          ›
        </button>
        <span class="viewer-traj-counter" data-testid="viewer-traj-counter">{{ trajectoryFrameLabel }}</span>
        <select
          class="viewer-traj-select"
          data-testid="viewer-traj-speed"
          :value="playbackSpeed"
          :disabled="loading || Boolean(error)"
          :aria-label="t('tasks.visualizationTrajectorySpeed')"
          @change="handleSpeedChange"
        >
          <option v-for="speed in playbackSpeeds" :key="speed" :value="speed">{{ speed }}x</option>
        </select>
        <button
          class="viewer-traj-btn"
          :class="{ 'is-active': loopPlayback }"
          type="button"
          data-testid="viewer-traj-loop"
          :aria-pressed="loopPlayback"
          :title="t('tasks.visualizationTrajectoryLoop')"
          @click="toggleLoop"
        >
          {{ t('tasks.visualizationTrajectoryLoop') }}
        </button>
        <button
          v-if="canExportMovie"
          class="viewer-traj-btn viewer-traj-btn--export"
          type="button"
          data-testid="viewer-traj-export"
          @click="emit('export-movie')"
        >
          {{ t('tasks.visualizationTrajectoryExport') }}
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
  clampFrameIndex,
  computeFrameIntervalMs,
  createNormalizedSdfObjectUrl,
  extractPolymerSequenceFromStructure,
  formatTrajectoryFrameLabel,
  groupSelectedResiduesByChain,
  residueSelectionKey,
  resolveMolstarColorThemeOptions,
  resolveMolstarEffectiveColorTheme,
  resolveMolstarHierarchyPreset,
  resolveMolstarRepresentationOptions,
  resolveMolstarViewerPreset,
  stepFrameIndex,
  toggleSequenceResidueSelection,
  TRAJECTORY_PLAYBACK_SPEEDS,
  type MolstarBackground,
  type MolstarColorTheme,
  type MolstarRepresentation,
  type MolstarViewerMode,
  type SequenceChain,
  type TrajectoryPlaybackSpeed,
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
  /** 是否启用底部多帧轨迹播放条（默认开，仅在非 compact 且帧数 > 1 时渲染）。 */
  enableTrajectoryControls?: boolean
  /** 每一 movie 帧对应的物理时间（ps），用于播放条的帧标签。 */
  frameTimesPs?: number[] | null
  /** 是否允许导出/下载 movie（由上层根据是否存在 `trajectory_movie_pdb` 决定）。 */
  canExportMovie?: boolean
}>(), {
  variant: 'full',
  allowNativeFullscreen: true,
  voxelGrid: null,
  focusResidue: null,
  enableNearbyResidues: false,
  enableTrajectoryControls: true,
  frameTimesPs: null,
  canExportMovie: false,
})
const emit = defineEmits<{
  'residue-focus-result': [status: 'focused' | 'not-found' | 'ambiguous']
  'frame-change': [frameIndex: number]
  'export-movie': []
  /** `fallbackOnFailure` 条目加载失败（空文件/404/内容损坏）时通知上层换个候选。 */
  'entry-unavailable': [entryKey: string]
}>()

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
// 用户拖走的原生 range 值不会被 Vue 在 `currentFrameIndex` 未变时回写，失败路径需手动回弹。
const trajSliderRef = ref<HTMLInputElement | null>(null)
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

// —— 多帧轨迹播放状态 ——
const playbackSpeeds = TRAJECTORY_PLAYBACK_SPEEDS
const trajectoryFrameCount = ref(1)
const currentFrameIndex = ref(0)
const isPlaying = ref(false)
const playbackSpeed = ref<TrajectoryPlaybackSpeed>(1)
const loopPlayback = ref(true)
const showTrajectoryBar = computed(
  () => !isCompact.value && props.enableTrajectoryControls && trajectoryFrameCount.value > 1,
)
const trajectoryFrameLabel = computed(() =>
  formatTrajectoryFrameLabel(currentFrameIndex.value, trajectoryFrameCount.value, props.frameTimesPs ?? undefined),
)
// 单飞防堆积：一次状态树 remap 在途时，只记录最新请求，完成后再追一次。
let frameUpdateInFlight = false
let pendingFrameRequest: FrameRequest | null = null
// 所有可播放（`frameCount > 1` 且拿到 `ModelFromTrajectory.model.ref`）的条目。
let activeTrajectoryModels: TrajectoryModelTarget[] = []
let playbackTimer: ReturnType<typeof setInterval> | null = null
// 播放代次：暂停/调速/关循环/手动换帧/场景切换/卸载都递增，用于丢弃排队中的旧自动帧。
let playbackToken = 0
// 场景代次：卸载或切换场景时递增，延迟 resolve 的异步更新不得落到已销毁/已替换的 viewer 上。
let sceneEpoch = 0

/** 把非法/非正帧数统一收敛为 1（单帧）。 */
function normalizeFrameCount(value: unknown): number {
  const count = Math.floor(Number(value))
  return Number.isFinite(count) && count > 0 ? count : 1
}

type FrameRequestSource = 'auto' | 'manual'

interface FrameRequest {
  frameIndex: number
  source: FrameRequestSource
  playbackToken: number
  sceneEpoch: number
}

interface TrajectoryModelTarget {
  modelRef: string
  /** 由该 model 派生出的 structure 节点 ref，用于检查换帧后是否进入 error cell。 */
  structureRefKey: string
  /** 该结构的 representation 节点 ref；换帧后任一进入 error 也算本次换帧失败。 */
  representationRefs: string[]
  frameCount: number
}

interface LoadedEntryRecord {
  role: VisualizationScene['entries'][number]['role']
  structureRefKey: string
  isPrimaryTarget: boolean
  /** `ModelFromTrajectory` 节点 ref（多帧原地 remap 用）；单帧/无轨迹时为 undefined。 */
  modelRef?: string
  /** 该结构的 representation 节点 ref；换帧后任一进入 error 也算本次换帧失败。 */
  representationRefs: string[]
  /** 该结构实际帧数（从 trajectory.obj.data.frameCount 读取，容错缺省 1）。 */
  frameCount: number
  /** 上层是否显式标记该条目为多帧 movie（严格 `=== true`）。 */
  preferComplexRepresentation: boolean
  /** 主目标在 cartoon 表示下是否应使用 `polymer-and-ligand`（保留配体/小分子）。 */
  preferComplexRepresentationForCartoon: boolean
}

let viewer: MolstarViewer | null = null
let viewerInitPromise: Promise<MolstarViewer | null> | null = null
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
  preferComplexRepresentation = false,
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

  // cartoon + 上层显式要求保留配体/小分子时用 polymer-and-ligand，
  // 避免 polymer-cartoon 只画聚合物、把配体藏掉。
  const presetKey =
    rep === 'cartoon' && preferComplexRepresentation
      ? ('polymer-and-ligand' as const)
      : resolveMolstarHierarchyPreset(rep)
  const provider = PresetStructureRepresentations[presetKey]
  await currentViewer.plugin.managers.structure.component.applyPreset(
    [structureRef],
    provider,
    themeParams,
  )
}

/**
 * 收集 `hierarchy.applyPreset` 返回的 representation 节点 ref。
 * Mol* 5.9 的预设结果包在 `representation.representations` 下
 * （`StructureRepresentationPresetProvider.Result`），值是 selector，其 `.ref`
 * 是状态树节点 key。换帧时 structure 更新会级联重算这些节点，其中任一个进入
 * error 都说明新帧没有完整渲染出来，不能只检查 model/structure 两个节点。
 */
function collectRepresentationRefs(preset: unknown): string[] {
  const result = (preset as { representation?: { representations?: unknown } } | null | undefined)
    ?.representation
  const representations = result?.representations
  if (!representations || typeof representations !== 'object') return []
  const refs: string[] = []
  for (const value of Object.values(representations as Record<string, unknown>)) {
    const ref = (value as { ref?: unknown } | null | undefined)?.ref
    if (typeof ref === 'string' && ref) refs.push(ref)
  }
  return refs
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
  // 容错读取帧数：真实 trajectory 在 `.obj.data.frameCount`，mock/异常/非有限值统一退化为 1（单帧）。
  const frameCount = normalizeFrameCount((trajectory as any)?.obj?.data?.frameCount)

  if (entry.role === 'pocket') {
    // 口袋残基也用卡通渲染：球棍（atomic-detail）在每个原子上画球，口袋动辄上百个残基，
    // 叠在卡通蛋白上会糊成一团、把整个蛋白整个盖住。卡通 + 单色反而更容易看出口袋位置。
    const preset = await currentViewer.plugin.builders.structure.hierarchy.applyPreset(trajectory, 'default', {
      representationPreset: 'polymer-cartoon',
      representationPresetParams: {
        theme: { globalName: 'uniform', globalColorParams: { value: Color(0xf59e0b) } },
      },
    })
    const ref = preset?.structure?.ref
    return ref
      ? {
          role: entry.role,
          structureRefKey: ref,
          isPrimaryTarget: false,
          modelRef: preset?.model?.ref,
          representationRefs: collectRepresentationRefs(preset),
          frameCount,
          preferComplexRepresentation: false,
          preferComplexRepresentationForCartoon: false,
        }
      : null
  }

  const primaryTarget = isPrimaryTargetEntry(entry.role)
  const initialRep: MolstarRepresentation = primaryTarget
    ? activeRepresentation.value
    : entry.role === 'ligand'
      ? 'ball-and-stick'
      : viewerPreset.value.primaryRepresentation
  // 仅当上层显式标记 `preferComplexRepresentation`（如去溶剂的 trajectory_movie_pdb）时，
  // 主目标卡通才用 polymer-and-ligand 保住配体/小分子；多帧但未标记的既有 protein/docking
  // 结构（含多帧含水 PDB）保持原 polymer-cartoon 外观，不因帧数改变渲染。
  const preferComplexRepresentation = entry.preferComplexRepresentation === true
  const preferComplexRepresentationForCartoon = primaryTarget && preferComplexRepresentation
  const presetName =
    initialRep === 'cartoon' && preferComplexRepresentationForCartoon
      ? ('polymer-and-ligand' as const)
      : resolveMolstarHierarchyPreset(initialRep)
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
        preferComplexRepresentationForCartoon,
      )
    }
  }

  return structureRefKey
    ? {
        role: entry.role,
        structureRefKey,
        isPrimaryTarget: primaryTarget,
        modelRef: preset?.model?.ref,
        representationRefs: collectRepresentationRefs(preset),
        frameCount,
        preferComplexRepresentation,
        preferComplexRepresentationForCartoon,
      }
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
      record.preferComplexRepresentationForCartoon,
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
      if (disposed) {
        disposeMolstarViewer(created)
        return null
      }
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

// —— 多帧轨迹播放控制 ——

/** 递增播放代次：使所有已排队的自动帧立即失效（暂停/调速/关循环/手动换帧/场景切换/卸载）。 */
function invalidatePlayback() {
  playbackToken += 1
  if (pendingFrameRequest?.source === 'auto') {
    pendingFrameRequest = null
  }
}

function stopPlayback() {
  invalidatePlayback()
  if (playbackTimer !== null) {
    clearInterval(playbackTimer)
    playbackTimer = null
  }
  isPlaying.value = false
}

/** 请求是否已过期：场景/卸载变化一律丢弃；自动帧还要额外确认仍在播放且代次未变。 */
function isFrameRequestStale(request: FrameRequest): boolean {
  if (disposed || request.sceneEpoch !== sceneEpoch) return true
  if (!viewer || !activeTrajectoryModels.length) return true
  if (request.source === 'auto' && (!isPlaying.value || request.playbackToken !== playbackToken)) return true
  return false
}

/** 把原生 range 控件的值回弹到当前已提交帧（Vue 不会在帧号未变时改写被用户拖走的 DOM 值）。 */
function syncSliderToCommittedFrame() {
  const slider = trajSliderRef.value
  if (slider) slider.value = String(currentFrameIndex.value)
}

/** 请求是否已不应再提交到 Mol* 状态树（场景/卸载/自动播放代次）。 */
function isAutoFrameRequestStale(request: FrameRequest): boolean {
  return request.source === 'auto' && (!isPlaying.value || request.playbackToken !== playbackToken)
}

/**
 * `PluginCommands.State.Update` 在部分错误下仍会 resolve，但目标 cell 会进入 `error`。
 * 只要被更新的 model/structure 节点任一处于 error，就视为本次换帧失败。
 */
function hasFailedUpdateCells(currentViewer: MolstarViewer, refs: string[]): boolean {
  const cells = currentViewer.plugin.state.data.cells as unknown as
    | ReadonlyMap<string, { status?: string }>
    | undefined
  if (!cells || typeof cells.get !== 'function') return false
  return refs.some(ref => cells.get(ref)?.status === 'error')
}

/** 把所有可播放轨迹写回指定帧号（每条按自身帧数夹紧），用于过期自动帧的状态树回滚。 */
async function writeTrajectoryFrameIndex(currentViewer: MolstarViewer, frameIndex: number): Promise<void> {
  const state = currentViewer.plugin.state.data
  const update = state.build()
  for (const trajectoryModel of activeTrajectoryModels) {
    update.to(trajectoryModel.modelRef).update({
      modelIndex: Math.min(Math.max(0, frameIndex), trajectoryModel.frameCount - 1),
    })
  }
  await PluginCommands.State.Update(currentViewer.plugin, { state, tree: update, options: { doNotLogTiming: true } })
}

function hasActivePendingFrameRequest(): boolean {
  if (pendingFrameRequest && isFrameRequestStale(pendingFrameRequest)) {
    pendingFrameRequest = null
  }
  return pendingFrameRequest !== null
}

/**
 * 原地 remap 到指定帧：修改每条可播放 `ModelFromTrajectory` 节点的 `modelIndex`，
 * 不重建插件、不复位相机，保留图层显隐/配色/序列高亮与焦点残基。
 * 单飞 + pending 合并高频拖动；**只有状态树更新真正 resolve 且目标 cell 未报错后才提交帧号与事件**，
 * 失败时将状态树回写到最后一次成功帧（确保 Mol* 参数复位、重选同一帧可再次触发转换）。
 */
async function applyFrameIndex(request: FrameRequest) {
  if (isFrameRequestStale(request)) return
  const frameCount = trajectoryFrameCount.value
  if (frameCount <= 1) return
  const target = clampFrameIndex(request.frameIndex, frameCount)
  if (target === currentFrameIndex.value && !frameUpdateInFlight) return
  const normalizedRequest: FrameRequest = { ...request, frameIndex: target }
  if (frameUpdateInFlight) {
    pendingFrameRequest = normalizedRequest
    return
  }
  frameUpdateInFlight = true
  const epoch = sceneEpoch
  try {
    const applied = await enqueueMutation(async () => {
      if (disposed || epoch !== sceneEpoch || !viewer || !activeTrajectoryModels.length) return false
      // 已经进入队列但尚未提交的自动帧，若期间已暂停/调速/关循环，直接丢弃。
      if (isAutoFrameRequestStale(request)) return false
      const currentViewer = viewer
      const updatedRefs: string[] = []
      const state = currentViewer.plugin.state.data
      const update = state.build()
      for (const trajectoryModel of activeTrajectoryModels) {
        update.to(trajectoryModel.modelRef).update({
          modelIndex: Math.min(target, trajectoryModel.frameCount - 1),
        })
        updatedRefs.push(trajectoryModel.modelRef)
        if (trajectoryModel.structureRefKey) updatedRefs.push(trajectoryModel.structureRefKey)
        // representation 节点由 structure 更新级联重算；任一报错说明该帧没有完整渲染。
        updatedRefs.push(...trajectoryModel.representationRefs)
      }
      await PluginCommands.State.Update(currentViewer.plugin, {
        state,
        tree: update,
        options: { doNotLogTiming: true },
      })
      const failedCells = hasFailedUpdateCells(currentViewer, updatedRefs)
      if (disposed || epoch !== sceneEpoch) return false
      if (failedCells) {
        // 自动播放遇到持续失败的帧只会一遍遍重试同一位置，直接停下并停在最后成功帧。
        stopPlayback()
      }
      // 无论是目标 cell 报错（modelIndex 已被写入，不回写会导致重选同帧被 Mol* 短路），
      // 还是在途自动帧已被暂停/调速/关循环，都需要立刻把状态树写回最后一次已提交帧。
      if (failedCells || isAutoFrameRequestStale(request)) {
        try {
          await writeTrajectoryFrameIndex(currentViewer, currentFrameIndex.value)
        } catch {
          // 回写失败不阻断控制流；计数仍停在最后一次成功帧。
        }
        return false
      }
      return true
    })
    // 更新被丢弃/已过期/已卸载：不得推进帧号，也不得发出 frame-change。
    if (!applied || isFrameRequestStale(request)) {
      if (!hasActivePendingFrameRequest()) syncSliderToCommittedFrame()
      return
    }
    currentFrameIndex.value = target
    emit('frame-change', target)
  } catch {
    // 自动帧抛错时停止播放，避免定时器对同一失败位置反复重试；帧号保持最后一次成功值，
    // 用户仍可再次选择同一帧手动重试。
    if (request.source === 'auto') stopPlayback()
    if (!hasActivePendingFrameRequest()) syncSliderToCommittedFrame()
  } finally {
    frameUpdateInFlight = false
    const pending = pendingFrameRequest
    pendingFrameRequest = null
    if (pending && !isFrameRequestStale(pending)) void applyFrameIndex(pending)
  }
}

function createFrameRequest(frameIndex: number, source: FrameRequestSource = 'manual'): FrameRequest {
  return { frameIndex, source, playbackToken, sceneEpoch }
}

function togglePlayback() {
  if (isPlaying.value) {
    stopPlayback()
    return
  }
  if (trajectoryFrameCount.value <= 1) return
  isPlaying.value = true
  const interval = computeFrameIntervalMs(playbackSpeed.value)
  playbackTimer = setInterval(() => {
    if (!isPlaying.value || disposed) {
      stopPlayback()
      return
    }
    const next = stepFrameIndex(currentFrameIndex.value, 1, trajectoryFrameCount.value, loopPlayback.value)
    if (next === null) {
      stopPlayback()
      return
    }
    void applyFrameIndex(createFrameRequest(next, 'auto'))
  }, interval)
}

function handleSliderInput(event: Event) {
  const value = Number((event.target as HTMLInputElement | null)?.value ?? 0)
  // 手动换帧同样推进播放代次：丢弃暂停/播放中排队但未提交的自动帧。
  stopPlayback()
  void applyFrameIndex(createFrameRequest(value, 'manual'))
}

function handleSpeedChange(event: Event) {
  const raw = Number((event.target as HTMLSelectElement | null)?.value ?? 1)
  const speed = (TRAJECTORY_PLAYBACK_SPEEDS as readonly number[]).includes(raw)
    ? (raw as TrajectoryPlaybackSpeed)
    : 1
  playbackSpeed.value = speed
  const wasPlaying = isPlaying.value
  stopPlayback()
  if (wasPlaying) togglePlayback()
}

function toggleLoop() {
  loopPlayback.value = !loopPlayback.value
  // 循环开关变化立即作废已排队的自动帧（旧回绕/不回头帧不得再提交）。
  invalidatePlayback()
}

function goPreviousFrame() {
  stopPlayback()
  const next = stepFrameIndex(currentFrameIndex.value, -1, trajectoryFrameCount.value, loopPlayback.value)
  if (next !== null) void applyFrameIndex(createFrameRequest(next, 'manual'))
}

function goNextFrame() {
  stopPlayback()
  const next = stepFrameIndex(currentFrameIndex.value, 1, trajectoryFrameCount.value, loopPlayback.value)
  if (next !== null) void applyFrameIndex(createFrameRequest(next, 'manual'))
}

/**
 * 渲染完成后重置轨迹状态：收集**所有**可播放条目（`frameCount > 1` 且拿到 modelRef），
 * 不因列表首条恰好缺 `modelRef` 就丢弃后续有效条目。
 *
 * 主控制条目（决定播放条帧数与 `frameTimesPs` 的对应关系）优先级：
 * 1. 显式标记 `preferComplexRepresentation === true` 的 movie（外部时间数组属于它）；
 * 2. 主目标条目；
 * 3. 首条有效可播放条目。
 * 其余条目各自按自身 `frameCount - 1` 夹紧同步，不会把较小轨迹的帧数套到别的轨迹上。
 */
function resetTrajectoryStateFromEntries() {
  const playableRecords = loadedEntries.filter(
    record => record.frameCount > 1 && Boolean(record.modelRef),
  )
  activeTrajectoryModels = playableRecords.map(record => ({
    modelRef: record.modelRef as string,
    structureRefKey: record.structureRefKey,
    representationRefs: record.representationRefs,
    frameCount: record.frameCount,
  }))
  const primaryPlayableRecord =
    playableRecords.find(record => record.preferComplexRepresentation === true)
    ?? playableRecords.find(record => record.isPrimaryTarget)
    ?? playableRecords[0]
  trajectoryFrameCount.value = normalizeFrameCount(primaryPlayableRecord?.frameCount ?? 1)
  currentFrameIndex.value = 0
  pendingFrameRequest = null
  // `frameUpdateInFlight` 交给在途更新的 finally 复位，避免旧场景的延迟回包与新场景状态互相覆盖。
}

async function renderScene() {
  const seq = ++renderSeq
  loading.value = true
  error.value = ''
  // 场景代次递增：上一场景排队中的异步帧更新在 resume 后会被丢弃，不污染新场景。
  sceneEpoch += 1
  stopPlayback()
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
  activeTrajectoryModels = []
  trajectoryFrameCount.value = 1
  currentFrameIndex.value = 0
  pendingFrameRequest = null
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
        try {
          const resource = entry.format === 'sdf'
            ? await createNormalizedSdfObjectUrl(entry.url, entry.sdfRecordIndex !== undefined && !entry.sdfRecordScoped ? { recordIndex: entry.sdfRecordIndex } : {})
            : await createProtectedObjectUrl(entry.url)
          if (seq !== renderSeq || disposed) {
            resource.revoke()
            return
          }
          entryResourcesRegistry.add(resource.revoke)
          const loaded = await loadEntryStructure(currentViewer, entry, resource.url)
          if (seq !== renderSeq || disposed) return
          if (loaded) {
            loadedEntries.push(loaded)
          } else if (entry.fallbackOnFailure) {
            // 解析成功但拿不到 structure ref：同样视为该候选不可用。
            emit('entry-unavailable', entry.key)
          }
        } catch (cause) {
          if (seq !== renderSeq || disposed) return
          // 允许回退的条目（如 PDB-movie → topology）单条失败不得中断整场景，
          // 由上层把该文件标记失败并换下一个候选；其他条目保持原有整场景报错语义。
          if (!entry.fallbackOnFailure) throw cause
          emit('entry-unavailable', entry.key)
        }
      }
      if (props.voxelGrid?.boxes.length) await addVoxelGrid(currentViewer, props.voxelGrid)
      if (seq !== renderSeq || disposed) return
      sequenceChains.value = collectPolymerSequences(currentViewer)
      if (!isCompact.value && sequenceChains.value.length) sequenceOpen.value = true
      currentViewer.handleResize()
    })
    if (seq === renderSeq && !disposed) resetTrajectoryStateFromEntries()
    if (seq === renderSeq && !disposed && loadedEntries.length && props.focusResidue) {
      await applyFocusResidue(props.focusResidue)
    }
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
  // 卸载代次递增：延迟 resolve 的 Mol* 更新不得再提交帧号或 emit。
  sceneEpoch += 1
  stopPlayback()
  activeTrajectoryModels = []
  pendingFrameRequest = null
  entryResourcesRegistry.clear()
  resizeObserver?.disconnect()
  removeLayoutSyncListener?.()
  removeLayoutSyncListener = null
  removeClickListener?.()
  removeClickListener = null
  // 等待在途状态树 mutation 结束（以及 viewer 初始化完成）再销毁，
  // 防止 `PluginCommands.State.Update` 与 `viewer.dispose()` 撞车。
  const pendingMutations = mutationQueue
  void Promise.allSettled([Promise.resolve(viewerInitPromise), pendingMutations]).finally(() => {
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

.viewer-select option {
  background: #0b1a2e;
  color: #e2e8f0;
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

.viewer-traj-bar {
  position: absolute;
  left: @spacing-sm;
  right: @spacing-sm;
  bottom: @spacing-sm;
  z-index: 3;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: @spacing-xs;
  padding: 6px 8px;
  border: 1px solid rgba(207, 224, 247, 0.28);
  border-radius: 8px;
  background: rgba(8, 20, 36, 0.82);
  backdrop-filter: blur(6px);
}

.viewer-traj-btn,
.viewer-traj-select {
  height: 26px;
  padding: 0 8px;
  border: 1px solid rgba(207, 224, 247, 0.28);
  border-radius: 6px;
  background: rgba(8, 20, 36, 0.76);
  color: #e2e8f0;
  cursor: pointer;
  font-size: 12px;
  line-height: 24px;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}

.viewer-traj-btn.is-active {
  border-color: #38bdf8;
  background: rgba(14, 116, 144, 0.85);
  color: #ffffff;
}

.viewer-traj-btn--play {
  min-width: 52px;
  font-weight: 600;
}

.viewer-traj-btn--export {
  border-color: #22c55e;
  color: #bbf7d0;
}

.viewer-traj-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.viewer-traj-slider {
  flex: 1 1 120px;
  min-width: 80px;
  height: 4px;
  accent-color: #38bdf8;
  cursor: pointer;
}

.viewer-traj-counter {
  min-width: 68px;
  color: #e2e8f0;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  text-align: center;
  white-space: nowrap;
}

.molecule-viewer--bg-white .viewer-traj-bar {
  border-color: rgba(15, 23, 42, 0.18);
  background: rgba(255, 255, 255, 0.92);
}

.molecule-viewer--bg-white .viewer-traj-btn,
.molecule-viewer--bg-white .viewer-traj-select {
  border-color: rgba(15, 23, 42, 0.18);
  background: rgba(255, 255, 255, 0.96);
  color: #0f172a;
}

.molecule-viewer--bg-white .viewer-traj-btn.is-active {
  border-color: #0284c7;
  background: #0284c7;
  color: #ffffff;
}

.molecule-viewer--bg-white .viewer-traj-counter {
  color: #0f172a;
}
</style>
