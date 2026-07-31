<template>
  <section class="run-report-artifact" data-testid="run-report-artifact">
    <FileArtifact :artifact="artifact" />
  </section>
</template>

<script setup lang="ts">
import FileArtifact from './FileArtifact.vue'
import type { TypedArtifact } from '@/types/artifacts'

defineProps<{
  artifact: TypedArtifact
}>()
</script>
