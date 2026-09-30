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

  <section v-if="node.type === 'condition'" class="inspector-section control-node-fields">
    <div class="section-title">{{ t('workflow.inspector.conditionSettings') }}</div>
    <label class="control-field">
      <span>{{ t('workflow.inspector.conditionOperator') }}</span>
      <a-select v-model:value="conditionOperator" :options="conditionOperatorOptions" />
    </label>
    <label class="control-field">
      <span>{{ t('workflow.inspector.conditionLeft') }}</span>
      <a-input v-model:value="conditionLeft" />
    </label>
    <label class="control-field">
      <span>{{ t('workflow.inspector.conditionRight') }}</span>
      <a-input v-model:value="conditionRight" />
    </label>
  </section>

  <section v-if="node.type === 'map'" class="inspector-section control-node-fields">
    <div class="section-title">{{ t('workflow.inspector.mapSettings') }}</div>
    <label class="control-field">
      <span>{{ t('workflow.inspector.mapSource') }}</span>
      <a-input v-model:value="mapSource" placeholder="workflow_input:smiles_csv" />
    </label>
    <label class="control-field">
      <span>{{ t('workflow.inspector.mapParallelism') }}</span>
      <a-input-number v-model:value="mapParallelism" :min="1" :max="100" />
    </label>
  </section>

  <section v-if="node.type === 'tool'" class="inspector-section">
    <div class="section-title">{{ t('workflow.inspector.nodeParameters') }}</div>
    <WorkflowNodeRunPanel
      :node-id="node.id"
      :project-id="projectId"
      :selected-tool-slug="selectedToolSlug"
      :available-tools="availableTools"
      :recommended-artifacts="recommendedArtifacts"
    />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type {
  WorkflowCanvasNode,
  WorkflowConditionExpression,
} from '@/workflow/canvas-types'
import type { WorkflowNodeArtifactRecommendation } from '@/workflow/canvas-artifacts'
import WorkflowNodeRunPanel from './WorkflowNodeRunPanel.vue'

interface WorkflowAvailableTool {
  id?: string
  slug: string
  name: string
  description?: string
}
const props = defineProps<{
  node: WorkflowCanvasNode
  projectId?: string | null
  selectedToolSlug?: string | null
  availableTools?: WorkflowAvailableTool[]
  recommendedArtifacts: WorkflowNodeArtifactRecommendation[]
}>()
const emit = defineEmits<{
  (event: 'select-tool', toolSlug: string): void
  (event: 'update-node', nodeId: string, changes: Partial<WorkflowCanvasNode>): void
}>()
const { t } = useI18n()
const toolOptions = computed(() => {
  const tools = props.availableTools?.length
    ? props.availableTools
    : (props.node.toolSlugs ?? []).map(slug => ({ slug, name: slug }))
  return tools.map(tool => ({ value: tool.slug, label: tool.name || tool.slug }))
})

function selectTool(value: unknown) {
  if (typeof value === 'string') emit('select-tool', value)
}

const conditionOperatorOptions = ['==', '!=', '>', '<', '>=', '<=', 'in', 'contains'].map(
  value => ({ value, label: value })
)

function updateExpression(changes: Partial<WorkflowConditionExpression>) {
  emit('update-node', props.node.id, {
    expression: {
      op: props.node.expression?.op ?? '==',
      left: true,
      right: true,
      ...props.node.expression,
      ...changes,
    },
  })
}

function parseOperand(value: string): unknown {
  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

function operandText(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value ?? '')
}

const conditionOperator = computed({
  get: () => props.node.expression?.op ?? '==',
  set: value => updateExpression({ op: value as WorkflowConditionExpression['op'] })
})
const conditionLeft = computed({
  get: () => operandText(props.node.expression?.left ?? true),
  set: value => updateExpression({ left: parseOperand(value) })
})
const conditionRight = computed({
  get: () => operandText(props.node.expression?.right ?? true),
  set: value => updateExpression({ right: parseOperand(value) })
})
const mapSource = computed({
  get: () => props.node.over ?? '',
  set: value => emit('update-node', props.node.id, { over: value })
})
const mapParallelism = computed({
  get: () => props.node.max_parallelism ?? 4,
  set: value => emit('update-node', props.node.id, { max_parallelism: Number(value) || 1 })
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';
.inspector-section { padding: @spacing-md @spacing-lg; border-bottom: 1px solid @border-color-light; }
.section-title { color: @text-color-light-tertiary; font-size: @font-size-xs; font-weight: 800; letter-spacing: 0; text-transform: uppercase; }
.tool-selector { width: 100%; margin-top: @spacing-sm; }
.control-node-fields { display: grid; gap: @spacing-sm; }
.control-field { display: grid; gap: @spacing-xs; color: @text-color-light-secondary; font-size: @font-size-sm; }
.control-field :deep(.ant-input-number) { width: 100%; }
</style>
