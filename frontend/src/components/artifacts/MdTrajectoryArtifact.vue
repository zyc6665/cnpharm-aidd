<template>
  <section class="md-trajectory-artifact" data-testid="md-trajectory-artifact">
    <a-alert type="info" show-icon :message="t('artifactAssets.mdTrajectory.notice')" />
    <FileArtifact :artifact="artifact" />
    <StructureArtifactPreview
      :artifact="artifact"
      role="structure"
      :preferred-file-roles="['topology_pdb', 'structure_file', 'structure_pdb']"
    />
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import type { TypedArtifact } from '@/types/artifacts'

import FileArtifact from './FileArtifact.vue'
import StructureArtifactPreview from './StructureArtifactPreview.vue'

defineProps<{
  artifact: TypedArtifact
}>()

const { t } = useI18n()
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.md-trajectory-artifact {
  display: flex;
  flex-direction: column;
  gap: @spacing-md;
}
</style>
