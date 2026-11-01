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
import { computed } from 'vue'

import type { TypedArtifact } from '@/types/artifacts'

import { resolveArtifactComponent } from './registry'

const props = defineProps<{
  artifact: TypedArtifact
}>()

const component = computed(() => resolveArtifactComponent(String(props.artifact.artifact_type)))
</script>
