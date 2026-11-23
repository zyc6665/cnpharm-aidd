<template>
  <div v-if="scene" class="structure-artifact-preview" data-testid="structure-artifact-preview">
    <component :is="MoleculeViewer" :scene="scene" :mode="resolvedMode" />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { buildArtifactVersionDownloadUrl } from '@/api/artifacts'
import {
  createVisualizationScene,
  detectVisualizationFormat,
  resolveMolstarStructureArtifactMode,
  type MolstarViewerMode,
  type VisualizationSceneEntry,
} from '@/domain/tasks'
import type { TypedArtifact } from '@/types/artifacts'

const props = withDefaults(
  defineProps<{
    artifact: TypedArtifact
    role?: VisualizationSceneEntry['role']
    mode?: MolstarViewerMode
    preferredFileRoles?: string[]
  }>(),
  {
    role: 'structure'
  }
)

const MoleculeViewer = defineAsyncComponent(() => import('@/components/tasks/MoleculeViewer.vue'))

const selectedRoleFile = computed(() => {
  const files = props.artifact.latest_version.files ?? []
  if (!files.length) {
    return null
  }

  for (const role of props.preferredFileRoles ?? []) {
    const match = files.find(file => file.role === role && file.download_url)
    if (match) {
      return match
    }
  }

  return files.find(file => file.is_primary && file.download_url) || files[0]
})

const fileRef = computed(() => ({
  id: selectedRoleFile.value?.file_id || props.artifact.latest_version.id,
  filename: selectedRoleFile.value?.filename || props.artifact.latest_version.filename,
  content_type:
    selectedRoleFile.value?.content_type || props.artifact.latest_version.content_type || undefined,
  url:
    selectedRoleFile.value?.download_url ||
    buildArtifactVersionDownloadUrl(props.artifact.id, props.artifact.latest_version.id),
}))

const detectedFormat = computed(() => detectVisualizationFormat(fileRef.value))

const resolvedMode = computed(() =>
  resolveMolstarStructureArtifactMode({
    explicitMode: props.mode,
    role: props.role,
    artifactType: props.artifact.artifact_type,
    format: detectedFormat.value,
  })
)

const scene = computed(() => {
  const format = detectedFormat.value
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
