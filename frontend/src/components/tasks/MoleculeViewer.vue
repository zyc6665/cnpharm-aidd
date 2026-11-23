<template>
  <div class="molecule-viewer" :class="`molecule-viewer--${variant}`">
    <div ref="containerRef" class="viewer-canvas" :class="{ 'viewer-canvas--hidden': Boolean(error) }" />

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
      <button class="viewer-reset" type="button" :disabled="loading || Boolean(error)" @click="resetCamera">{{ t('tasks.visualizationResetView') }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import 'molstar/build/viewer/molstar.css'

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Viewer as MolstarViewer } from 'molstar/lib/apps/viewer/app'
import { PluginCommands } from 'molstar/lib/mol-plugin/commands'
import { Asset } from 'molstar/lib/mol-util/assets'
import { Vec3 } from 'molstar/lib/mol-math/linear-algebra'
import { Sphere3D } from 'molstar/lib/mol-math/geometry'
import { Color } from 'molstar/lib/mol-util/color'
import { createMolstarViewer, createRevocableResourceRegistry, disposeMolstarViewer } from './molstar-viewer-kernel'
import { BoxShape3D } from 'molstar/lib/mol-plugin-state/transforms/shape'
import { ShapeRepresentation3D } from 'molstar/lib/mol-plugin-state/transforms/representation'

import { resolveMolstarHierarchyPreset, resolveMolstarViewerPreset, type VisualizationScene } from '@/domain/tasks'
import type { PocketVoxelGrid } from '@/domain/tasks/pocket-voxel'
import { createNormalizedSdfObjectUrl } from '@/domain/tasks'
import { createProtectedObjectUrl } from '@/utils/protected-file-access'

const defaultMode = 'molecule' as const

const props = withDefaults(defineProps<{
  scene: VisualizationScene
  variant?: 'compact' | 'full'
  mode?: 'molecule' | 'protein' | 'docking'
  allowNativeFullscreen?: boolean
  voxelGrid?: PocketVoxelGrid | null
}>(), {
  variant: 'full',
  allowNativeFullscreen: true,
  voxelGrid: null,
})

const { t } = useI18n()
const viewerPreset = computed(() => resolveMolstarViewerPreset(props.mode ?? defaultMode))

const containerRef = ref<HTMLElement | null>(null)
const loading = ref(true)
const error = ref('')

let viewer: MolstarViewer | null = null
let resizeObserver: ResizeObserver | null = null
const entryResourcesRegistry = createRevocableResourceRegistry()
let removeLayoutSyncListener: (() => void) | null = null

function syncFullscreenLayout() {
  if (!viewer || !props.allowNativeFullscreen) {
    return
  }

  const layoutState = viewer.plugin.layout.state

  if (layoutState.expandToFullscreen && !layoutState.isExpanded) {
    void PluginCommands.Layout.Update(viewer.plugin, {
      state: {
        isExpanded: true,
        expandToFullscreen: true
      }
    })
    return
  }

  if (!layoutState.expandToFullscreen && layoutState.isExpanded) {
    void PluginCommands.Layout.Update(viewer.plugin, {
      state: {
        isExpanded: false
      }
    })
  }
}

async function loadPresetStructure(
  currentViewer: MolstarViewer,
  entry: VisualizationScene['entries'][number],
  url: string,
  representationPreset: 'polymer-cartoon' | 'molecular-surface' | 'atomic-detail',
  color?: number,
) {
  const data = await currentViewer.plugin.builders.data.download(
    {
      url: Asset.Url(url),
      isBinary: false,
      label: entry.label
    },
    { state: { isGhost: true } }
  )
  const trajectory = await currentViewer.plugin.builders.structure.parseTrajectory(data, entry.format)

  await currentViewer.plugin.builders.structure.hierarchy.applyPreset(trajectory, 'default', {
    representationPreset,
    ...(color === undefined
      ? {}
      : {
          representationPresetParams: {
            theme: { globalName: 'uniform', globalColorParams: { value: Color(color) } },
          },
        }),
  })
}

async function addVoxelGrid(currentViewer: MolstarViewer, grid: PocketVoxelGrid) {
  const state = currentViewer.plugin.state.data.build()
  const color = Color(grid.color ?? 0x22d3ee)
  const radius = grid.radius ?? 0.05

  for (const box of grid.boxes) {
    const [x, y, z] = box.center
    const half = box.halfSize
    const shape = state.toRoot().apply(BoxShape3D, {
      bottomLeft: Vec3.create(x - half, y - half, z - half),
      topRight: Vec3.create(x + half, y + half, z + half),
      radius,
      color,
    })
    shape.apply(ShapeRepresentation3D, {})
  }

  await state.commit()

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

async function ensureViewer() {
  if (viewer || !containerRef.value) {
    return
  }

  viewer = await createMolstarViewer(containerRef.value, {
    allowNativeFullscreen: props.allowNativeFullscreen,
    showControls: viewerPreset.value.showControls,
  })

  const subscription = viewer.plugin.layout.events.updated.subscribe(() => {
    syncFullscreenLayout()
  })
  removeLayoutSyncListener = () => subscription.unsubscribe()
}

function resetCamera() {
  if (!viewer) return
  viewer.plugin.managers.camera.reset(undefined, 300)
}

async function renderScene() {
  loading.value = true
  error.value = ''
  entryResourcesRegistry.clear()

  try {
    if (!props.scene.entries.length) {
      loading.value = false
      return
    }

    await ensureViewer()

    if (!viewer) {
      throw new Error('Mol* viewer unavailable')
    }

    await viewer.plugin.clear()

    const entryResourcesList = await Promise.all(
      props.scene.entries.map(async entry => ({
        entry,
        resource: entry.format === 'sdf'
          ? await createNormalizedSdfObjectUrl(entry.url)
          : await createProtectedObjectUrl(entry.url)
      }))
    )

    try {
      for (const { entry, resource } of entryResourcesList) {
        if (entry.role === 'receptor') {
          await loadPresetStructure(viewer, entry, resource.url, 'polymer-cartoon', 0x9ca3af)
          continue
        }

        if (entry.role === 'pocket') {
          // 口袋残基也用卡通渲染：球棍（atomic-detail）在每个原子上画球，口袋动辄上百个残基，
          // 叠在卡通蛋白上会糊成一团、把完整蛋白整个盖住。卡通 + 单色反而更容易看出口袋位置。
          await loadPresetStructure(viewer, entry, resource.url, 'polymer-cartoon', 0xf59e0b)
          continue
        }

        if (entry.role === 'ligand' && viewerPreset.value.primaryRepresentation === 'ball-and-stick') {
          await loadPresetStructure(viewer, entry, resource.url, resolveMolstarHierarchyPreset(viewerPreset.value.primaryRepresentation))
          continue
        }

        await viewer.loadStructureFromUrl(resource.url, entry.format, false, {
          label: entry.label
        })
      }

      if (props.voxelGrid?.boxes.length) {
        await addVoxelGrid(viewer, props.voxelGrid)
      }

      entryResourcesList.forEach(({ resource }) => entryResourcesRegistry.add(resource.revoke))
    } catch (cause) {
      entryResourcesList.forEach(({ resource }) => resource.revoke())
      throw cause
    }

    viewer.handleResize()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  if (containerRef.value) {
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
  { deep: true }
)

onUnmounted(() => {
  entryResourcesRegistry.clear()
  resizeObserver?.disconnect()
  removeLayoutSyncListener?.()
  removeLayoutSyncListener = null
  disposeMolstarViewer(viewer)
  viewer = null
})
</script>

<style scoped>
.molecule-viewer {
  position: relative;
  min-height: 520px;
  height: 520px;
  border-radius: 20px;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(87, 181, 231, 0.22), transparent 38%),
    linear-gradient(145deg, #07111f, #10233f 58%, #17345f);
}

.molecule-viewer--compact {
  width: 100%;
  height: 100%;
  min-height: 100%;
  border-radius: 8px;
}

.molecule-viewer--full {
  min-height: 520px;
  height: 520px;
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
  align-items: center;
  gap: @spacing-xs;
}

.viewer-mode {
  padding: 2px 6px;
  border: 1px solid rgba(255, 255, 255, 0.24);
  border-radius: 4px;
  color: rgba(255, 255, 255, 0.82);
  background: rgba(8, 15, 30, 0.72);
  font-size: 11px;
  text-transform: capitalize;
}

.viewer-reset {
  position: static;
  z-index: auto;
  padding: 5px 10px;
  border: 1px solid rgba(207, 224, 247, 0.28);
  border-radius: 6px;
  background: rgba(8, 20, 36, 0.72);
  color: #cfe0f7;
  cursor: pointer;
  font-size: 12px;
  backdrop-filter: blur(4px);
}

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
