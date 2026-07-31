<template>
  <section class="structure-artifact" data-testid="protein-structure-artifact">
    <FileArtifact :artifact="artifact" />
    <div v-if="scene" class="structure-artifact__viewer">
      <component :is="MoleculeViewer" :scene="scene" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { buildArtifactVersionDownloadUrl } from '@/api/artifacts'
import FileArtifact from './FileArtifact.vue'
import {
  createVisualizationScene,
  detectVisualizationFormat,
  type VisualizationSceneEntry,
} from '@/components/tasks/result-visualization'
import type { TypedArtifact } from '@/types/artifacts'

const props = defineProps<{
  artifact: TypedArtifact
}>()

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
    role: 'receptor',
    format,
    extension,
  }

  return createVisualizationScene([], [entry], [])
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.structure-artifact {
  display: flex;
  flex-direction: column;
  gap: @spacing-md;
}

.structure-artifact__viewer {
  min-height: 360px;
}
</style>
