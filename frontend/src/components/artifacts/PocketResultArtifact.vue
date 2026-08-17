<template>
  <section class="pocket-artifact" data-testid="pocket-result-artifact">
    <FileArtifact :artifact="artifact" />
    <StructureArtifactPreview :artifact="artifact" />
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

.pocket-artifact {
  display: flex;
  flex-direction: column;
  gap: @spacing-md;
}
</style>
