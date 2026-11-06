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
  </div>
</template>

<script setup lang="ts">
import 'molstar/build/viewer/molstar.css'

import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Viewer as MolstarViewer } from 'molstar/lib/apps/viewer/app'
import { PluginCommands } from 'molstar/lib/mol-plugin/commands'
import { Asset } from 'molstar/lib/mol-util/assets'
import { Vec3 } from 'molstar/lib/mol-math/linear-algebra'
import { Sphere3D } from 'molstar/lib/mol-math/geometry'
import { Color } from 'molstar/lib/mol-util/color'
import { BoxShape3D } from 'molstar/lib/mol-plugin-state/transforms/shape'
import { ShapeRepresentation3D } from 'molstar/lib/mol-plugin-state/transforms/representation'

import type { VisualizationScene } from '@/domain/tasks'
import type { PocketVoxelGrid } from '@/domain/tasks/pocket-voxel'
import { createNormalizedSdfObjectUrl } from '@/domain/tasks'
import { createProtectedObjectUrl } from '@/utils/protected-file-access'

const props = withDefaults(defineProps<{
  scene: VisualizationScene
  variant?: 'compact' | 'full'
  allowNativeFullscreen?: boolean
  voxelGrid?: PocketVoxelGrid | null
}>(), {
  variant: 'full',
  allowNativeFullscreen: true,
  voxelGrid: null,
})

const { t } = useI18n()

const containerRef = ref<HTMLElement | null>(null)
const loading = ref(true)
const error = ref('')

let viewer: MolstarViewer | null = null
let resizeObserver: ResizeObserver | null = null
let revokeEntryUrls: Array<() => void> = []
let removeLayoutSyncListener: (() => void) | null = null

function cleanupEntryUrls() {
  revokeEntryUrls.forEach(revoke => revoke())
  revokeEntryUrls = []
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
  representationPreset: 'polymer-cartoon' | 'atomic-detail',
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
            theme: { globalName: 'uniform', globalParams: { value: Color(color) } },
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

  const { Viewer } = await import('molstar/lib/apps/viewer/app')
  viewer = await Viewer.create(containerRef.value, {
    layoutIsExpanded: false,
    layoutShowControls: false,
    collapseLeftPanel: true,
    collapseRightPanel: true,
    viewportShowControls: false,
    viewportShowExpand: false,
    viewportShowToggleFullscreen: true,
    viewportShowSettings: false,
    viewportShowSelectionMode: false,
    viewportShowAnimation: false,
    viewportShowTrajectoryControls: false,
    viewportShowScreenshotControls: false
  })

  const subscription = viewer.plugin.layout.events.updated.subscribe(() => {
    syncFullscreenLayout()
  })
  removeLayoutSyncListener = () => subscription.unsubscribe()
}

async function renderScene() {
  loading.value = true
  error.value = ''
  cleanupEntryUrls()

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

    const entryResources = await Promise.all(
      props.scene.entries.map(async entry => ({
        entry,
        resource: entry.format === 'sdf'
          ? await createNormalizedSdfObjectUrl(entry.url)
          : await createProtectedObjectUrl(entry.url)
      }))
    )

    try {
      for (const { entry, resource } of entryResources) {
        if (entry.role === 'receptor') {
          await loadPresetStructure(viewer, entry, resource.url, 'polymer-cartoon', 0x9ca3af)
          continue
        }

        if (entry.role === 'pocket') {
          await loadPresetStructure(viewer, entry, resource.url, 'atomic-detail', 0xf59e0b)
          continue
        }

        await viewer.loadStructureFromUrl(resource.url, entry.format, false, {
          label: entry.label
        })
      }

      if (props.voxelGrid?.boxes.length) {
        await addVoxelGrid(viewer, props.voxelGrid)
      }

      revokeEntryUrls = entryResources.map(({ resource }) => resource.revoke)
    } catch (cause) {
      entryResources.forEach(({ resource }) => resource.revoke())
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
  () => [props.scene.entries, props.voxelGrid],
  () => {
    void renderScene()
  },
  { deep: true }
)

onUnmounted(() => {
  cleanupEntryUrls()
  resizeObserver?.disconnect()
  removeLayoutSyncListener?.()
  removeLayoutSyncListener = null
  viewer?.dispose()
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
