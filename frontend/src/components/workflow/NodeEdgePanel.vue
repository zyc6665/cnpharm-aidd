<template>
  <section v-if="node.type !== 'input'" class="inspector-section">
    <div class="section-title">{{ t('workflow.inspector.recommendedEdges') }}</div>
    <div v-if="edgeSuggestions.length" class="edge-list">
      <div
        v-for="suggestion in edgeSuggestions"
        :key="`${suggestion.sourceNodeId}-${suggestion.semanticType}`"
        class="edge-item"
      >
        <span
          ><strong>{{ suggestion.sourceNodeTitle }}</strong
          ><small>{{ suggestion.semanticType }}</small></span
        ><a-button size="small" type="primary" ghost @click="addSuggestedEdge(suggestion)">{{
          t('workflow.inspector.addEdge')
        }}</a-button>
      </div>
    </div>
    <a-empty v-else :description="t('workflow.inspector.noRecommendedEdges')" />
  </section>
  <section v-if="node.type !== 'input'" class="inspector-section">
    <div class="section-title">{{ t('workflow.inspector.upstreamEdge') }}</div>
    <div v-if="upstreamEdges.length" class="edge-list">
      <div v-for="edge in upstreamEdges" :key="edge.id" class="edge-item">
        <span
          ><strong>{{ nodeTitleById[edge.source] ?? edge.source }}</strong
          ><small>{{ edge.artifactType ?? t('workflow.inspector.artifactFallback') }}</small></span
        ><a-button size="small" danger @click="$emit('delete-edge', edge.id)">{{
          t('workflow.inspector.deleteEdge')
        }}</a-button>
      </div>
    </div>
    <div class="edge-editor">
      <a-select
        v-model:value="sourceNodeId"
        :placeholder="t('workflow.inspector.sourceNode')"
        :options="sourceNodeOptions"
      /><a-select
        v-model:value="artifactType"
        :placeholder="t('workflow.inspector.artifactType')"
        :options="artifactTypeOptions"
      /><a-button block :disabled="!sourceNodeId || !artifactType" @click="addEdge">{{
        t('workflow.inspector.addEdge')
      }}</a-button>
    </div>
  </section>
  <section class="inspector-section">
    <div class="section-title">{{ t('workflow.inspector.requiredInput') }}</div>
    <div v-if="inputSlotLabels.length" class="slot-list">
      <a-tag v-for="slot in inputSlotLabels" :key="slot" color="blue">{{ slot }}</a-tag>
    </div>
    <div v-else-if="recommendations.length" class="input-list">
      <div v-for="recommendation in recommendations" :key="recommendation.edgeId">
        <a-tag color="blue">{{ recommendation.semanticType }}</a-tag
        ><span>{{
          recommendation.artifact?.filename ?? t('workflow.inspector.missingArtifact')
        }}</span>
      </div>
    </div>
    <div v-else-if="node.requiredInputTypes?.length">
      <a-tag v-for="inputType in node.requiredInputTypes" :key="inputType" color="blue">{{
        inputType
      }}</a-tag>
    </div>
    <a-empty v-else :description="t('workflow.inspector.noRequiredInput')" />
  </section>
  <section class="inspector-section">
    <div class="section-title">{{ t('workflow.inspector.producedOutput') }}</div>
    <div v-if="outputSlotLabels.length" class="slot-list">
      <a-tag v-for="slot in outputSlotLabels" :key="slot" color="green">{{ slot }}</a-tag>
    </div>
    <div v-else-if="node.producedOutputTypes?.length">
      <a-tag v-for="outputType in node.producedOutputTypes" :key="outputType" color="green">{{
        outputType
      }}</a-tag>
    </div>
    <a-empty v-else :description="t('workflow.inspector.noProducedOutput')" />
  </section>
</template>
<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import {
    WORKFLOW_ARTIFACT_SEMANTIC_TYPES,
    type WorkflowArtifactSemanticType,
    type WorkflowTaskRef
  } from '@/workflow/artifact-types'
  import {
    recommendArtifactsForNode,
    suggestWorkflowEdgesForNode,
    type WorkflowEdgeSuggestion
  } from '@/workflow/template-artifacts'
  import type { WorkflowCanvasNode, WorkflowCanvasPreset } from '@/workflow/template-types'
  import type { ArtifactFile } from '@/types/models'
  const props = defineProps<{
    node: WorkflowCanvasNode
    template?: WorkflowCanvasPreset | null
    artifacts?: ArtifactFile[]
    taskByNode?: Record<string, WorkflowTaskRef>
  }>()
  const emit = defineEmits<{
    (
      event: 'add-edge',
      input: { source: string; target: string; artifactType: WorkflowArtifactSemanticType }
    ): void
    (event: 'delete-edge', edgeId: string): void
  }>()
  const { t, te } = useI18n()
  const sourceNodeId = ref<string>()
  const artifactType = ref<WorkflowArtifactSemanticType>()
  const sourceNodeOptions = computed(() =>
    (props.template?.nodes ?? [])
      .filter(item => item.id !== props.node.id)
      .map(item => ({ value: item.id, label: label(item.titleKey) }))
  )
  const nodeTitleById = computed(() =>
    Object.fromEntries((props.template?.nodes ?? []).map(item => [item.id, label(item.titleKey)]))
  )
  const upstreamEdges = computed(() =>
    (props.template?.edges ?? []).filter(edge => edge.target === props.node.id)
  )
  const artifactTypeOptions = computed(() =>
    WORKFLOW_ARTIFACT_SEMANTIC_TYPES.map(value => ({ value, label: value }))
  )
  const recommendations = computed(() =>
    props.template
      ? recommendArtifactsForNode({
          template: props.template,
          nodeId: props.node.id,
          artifacts: props.artifacts ?? [],
          taskByNode: props.taskByNode ?? {}
        })
      : []
  )
  const edgeSuggestions = computed(() =>
    props.template
      ? suggestWorkflowEdgesForNode({ template: props.template, nodeId: props.node.id })
      : []
  )
  const inputSlotLabels = computed(() =>
    (props.node.inputArtifactSlots ?? []).map(slot => `${slot.name}: ${slot.type}`)
  )
  const outputSlotLabels = computed(() =>
    (props.node.outputArtifactSlots ?? []).map(slot => `${slot.name}: ${slot.type}`)
  )
  function addEdge() {
    if (sourceNodeId.value && artifactType.value)
      emit('add-edge', {
        source: sourceNodeId.value,
        target: props.node.id,
        artifactType: artifactType.value
      })
  }
  function addSuggestedEdge(suggestion: WorkflowEdgeSuggestion) {
    emit('add-edge', {
      source: suggestion.sourceNodeId,
      target: suggestion.targetNodeId,
      artifactType: suggestion.semanticType
    })
  }
  function label(key: string) {
    if (te(key)) return t(key)
    return (key.split('.').pop() ?? key)
      .replace(/([A-Z])/g, ' $1')
      .replace(/[-_]/g, ' ')
      .trim()
  }
  watch(
    () => props.node.id,
    () => {
      sourceNodeId.value = undefined
      artifactType.value = undefined
    }
  )
</script>
<style scoped lang="less">
  @import '@/assets/styles/variables.less';
  .inspector-section {
    padding: @spacing-md @spacing-lg;
    border-bottom: 1px solid @border-color-light;
  }
  .section-title {
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: 800;
    text-transform: uppercase;
  }
  .edge-list,
  .input-list,
  .edge-editor,
  .slot-list {
    display: grid;
    gap: @spacing-sm;
    margin-top: @spacing-sm;
  }
  .edge-item {
    display: flex;
    justify-content: space-between;
    gap: @spacing-sm;
    padding: @spacing-xs @spacing-sm;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-sm;
    background: @bg-elevated;
  }
  .edge-item span {
    display: grid;
  }
  small,
  span {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }
</style>
