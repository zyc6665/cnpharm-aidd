<template>
  <section class="ligand-artifact" data-testid="ligand-structure-artifact">
    <FileArtifact :artifact="artifact" />
    <StructureArtifactPreview :artifact="artifact" role="ligand" />
  </section>
</template>

<script setup lang="ts">
import FileArtifact from './FileArtifact.vue'
import StructureArtifactPreview from './StructureArtifactPreview.vue'
import type { TypedArtifact } from '@/types/artifacts'

defineProps<{
  artifact: TypedArtifact
}>()
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.ligand-artifact {
  display: flex;
  flex-direction: column;
  gap: @spacing-md;
}
</style>
