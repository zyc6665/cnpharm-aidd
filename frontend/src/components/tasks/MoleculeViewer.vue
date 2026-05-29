<template>
  <div class="molecule-viewer">
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

import type { VisualizationScene } from './result-visualization'
import { createProtectedObjectUrl } from '@/utils/protected-file-access'

const props = defineProps<{
  scene: VisualizationScene
}>()

const { t } = useI18n()

const containerRef = ref<HTMLElement | null>(null)
const loading = ref(true)
const error = ref('')

let viewer: MolstarViewer | null = null
let resizeObserver: ResizeObserver | null = null
let revokeEntryUrls: Array<() => void> = []

function cleanupEntryUrls() {
  revokeEntryUrls.forEach(revoke => revoke())
  revokeEntryUrls = []
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
    viewportShowSettings: false,
    viewportShowSelectionMode: false,
    viewportShowAnimation: false,
    viewportShowTrajectoryControls: false,
    viewportShowScreenshotControls: false
  })
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
        resource: await createProtectedObjectUrl(entry.url)
      }))
    )

    try {
      for (const { entry, resource } of entryResources) {
        await viewer.loadStructureFromUrl(resource.url, entry.format, false, {
          label: entry.label
        })
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
  () => props.scene.entries,
  () => {
    void renderScene()
  },
  { deep: true }
)

onUnmounted(() => {
  cleanupEntryUrls()
  resizeObserver?.disconnect()
  viewer?.dispose()
  viewer = null
})
</script>

<style scoped>
.molecule-viewer {
  position: relative;
  min-height: 520px;
  border-radius: 20px;
  overflow: hidden;
  background:
    radial-gradient(circle at top left, rgba(87, 181, 231, 0.22), transparent 38%),
    linear-gradient(145deg, #07111f, #10233f 58%, #17345f);
}

.viewer-canvas {
  width: 100%;
  min-height: 520px;
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
  height: 520px;
}

.molecule-viewer :deep(.msp-viewport) {
  background: transparent;
}
</style>
