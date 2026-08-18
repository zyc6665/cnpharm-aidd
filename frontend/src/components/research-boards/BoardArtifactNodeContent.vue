<template>
  <section class="board-artifact-node-content">
    <ArtifactRenderer :artifact="artifact" />
    <button
      v-if="canPrepareProtein"
      data-testid="prepare-protein-action"
      type="button"
      class="prepare-action"
      :disabled="disabled"
      @click.stop="emit('prepare-protein', { artifactId: artifact.id, nodeId })"
    >
      <ThunderboltOutlined />
      <span>准备蛋白</span>
    </button>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ThunderboltOutlined } from '@ant-design/icons-vue'
import ArtifactRenderer from '@/components/artifacts/ArtifactRenderer.vue'
import type { TypedArtifact } from '@/types/artifacts'

const props = withDefaults(defineProps<{
  artifact: TypedArtifact
  nodeId: string
  disabled?: boolean
}>(), { disabled: false })

const emit = defineEmits<{
  (event: 'prepare-protein', value: { artifactId: string; nodeId: string }): void
}>()

const canPrepareProtein = computed(() =>
  props.artifact.artifact_type === 'protein_structure' ||
  props.artifact.semantic_type === 'protein_structure@1' ||
  props.artifact.standard_type === 'protein_structure'
)
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.board-artifact-node-content {
  display: flex;
  flex-direction: column;
  gap: @spacing-sm;
}

.prepare-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 32px;
  border: 1px solid @accent-color-border;
  border-radius: @border-radius-sm;
  background: @accent-color-light;
  color: @accent-color;
  font-weight: @font-weight-medium;
  cursor: pointer;
}

.prepare-action:disabled {
  opacity: .5;
  cursor: not-allowed;
}
</style>
