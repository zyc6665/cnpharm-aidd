<template>
  <div v-if="scene" class="structure-artifact-preview" data-testid="structure-artifact-preview">
    <component :is="MoleculeViewer" :scene="scene" />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { buildArtifactVersionDownloadUrl } from '@/api/artifacts'
import {
  createVisualizationScene,
  detectVisualizationFormat,
  type VisualizationSceneEntry,
} from '@/domain/tasks'
import type { TypedArtifact } from '@/types/artifacts'

const props = withDefaults(
  defineProps<{
    artifact: TypedArtifact
    role?: VisualizationSceneEntry['role']
  }>(),
  {
    role: 'structure'
  }
)

const MoleculeViewer = defineAsyncComponent(() => import('@/components/tasks/MoleculeViewer.vue'))

const fileRef = computed(() => ({
  id: props.artifact.latest_version.id,
  filename: props.artifact.latest_version.filename,
  content_type: props.artifact.latest_version.content_type || undefined,
  url: buildArtifactVersionDownloadUrl(props.artifact.id, props.artifact.latest_version.id),
}))

const scene = computed(() => {
  const format = detectVisualizationFormat(fileRef.value)
  if (!format) {
    return null
  }

  const extension = `.${format === 'mmcif' ? 'cif' : format}`
  const entry: VisualizationSceneEntry = {
    key: `artifact-${props.artifact.id}`,
    url: fileRef.value.url,
    label: props.artifact.name,
    source: 'output',
    role: props.role,
    format,
    extension,
  }

  return createVisualizationScene([], [entry], [])
})
</script>

<style scoped lang="less">
.structure-artifact-preview {
  min-height: 360px;
}
</style>
