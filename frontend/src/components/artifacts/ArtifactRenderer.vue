<template>
  <component :is="component" v-if="component" :artifact="artifact" />
  <a-alert
    v-else
    data-testid="artifact-fallback"
    type="info"
    show-icon
    :message="`暂不支持的产物类型：${artifact.artifact_type}`"
    :description="artifact.name"
  />
</template>

<script setup lang="ts">
  import { computed, type Component } from 'vue'
  import type { ArtifactType, TypedArtifact } from '@/types/artifacts'
  import FileArtifact from './FileArtifact.vue'
  import LigandStructureArtifact from './LigandStructureArtifact.vue'
  import PocketResultArtifact from './PocketResultArtifact.vue'
  import ProteinStructureArtifact from './ProteinStructureArtifact.vue'
  import RunReportArtifact from './RunReportArtifact.vue'

  const props = defineProps<{
    artifact: TypedArtifact
  }>()

  const artifactComponents: Record<ArtifactType, Component> = {
    protein_structure: ProteinStructureArtifact,
    binding_pocket: PocketResultArtifact,
    pocket_result: PocketResultArtifact,
    ligand_structure: LigandStructureArtifact,
    molecule_table: FileArtifact,
    file: FileArtifact,
    run_report: RunReportArtifact
  }

  const component = computed(
    () => artifactComponents[props.artifact.artifact_type as ArtifactType] || null
  )
</script>
