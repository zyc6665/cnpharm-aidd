<template>
  <section class="inspector-section">
    <div class="section-title">{{ t('workflow.inspector.toolSelector') }}</div>
    <a-select
      v-if="node.type === 'tool'"
      class="tool-selector"
      :value="selectedToolSlug"
      :options="toolOptions"
      :placeholder="t('workflow.inspector.selectTool')"
      @change="selectTool"
    />
    <a-alert v-else type="info" show-icon :message="t('workflow.inspector.noToolRequired')" />
  </section>

  <section v-if="node.type === 'tool'" class="inspector-section">
    <div class="section-title">{{ t('workflow.inspector.nodeParameters') }}</div>
    <WorkflowNodeRunPanel
      :node-id="node.id"
      :selected-tool-slug="selectedToolSlug"
      :available-tools="availableTools"
      :recommended-artifacts="recommendedArtifacts"
    />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { WorkflowCanvasNode } from '@/workflow/template-types'
import type { WorkflowNodeArtifactRecommendation } from '@/workflow/template-artifacts'
import WorkflowNodeRunPanel from './WorkflowNodeRunPanel.vue'

interface WorkflowAvailableTool { id?: string; slug: string; name: string; description?: string }
const props = defineProps<{
  node: WorkflowCanvasNode
  selectedToolSlug?: string | null
  availableTools?: WorkflowAvailableTool[]
  recommendedArtifacts: WorkflowNodeArtifactRecommendation[]
}>()
const emit = defineEmits<{ (event: 'select-tool', toolSlug: string): void }>()
const { t } = useI18n()
const toolOptions = computed(() => (props.availableTools?.length ? props.availableTools : (props.node.toolSlugs ?? []).map(slug => ({ slug, name: slug }))).map(tool => ({ value: tool.slug, label: tool.name || tool.slug })))
function selectTool(value: unknown) { if (typeof value === 'string') emit('select-tool', value) }
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';
.inspector-section { padding: @spacing-md @spacing-lg; border-bottom: 1px solid @border-color-light; }
.section-title { color: @text-color-light-tertiary; font-size: @font-size-xs; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.tool-selector { width: 100%; margin-top: @spacing-sm; }
</style>
