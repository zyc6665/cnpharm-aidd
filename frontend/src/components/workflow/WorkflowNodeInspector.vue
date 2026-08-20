<template>
  <aside class="workflow-node-inspector">
    <a-empty v-if="!node" class="inspector-empty" :description="t('workflow.inspector.noSelectedNode')" />
    <template v-else>
      <div class="inspector-header"><span class="inspector-kicker">{{ t(`workflow.nodeType.${node.type}`) }}</span><h3>{{ label(node.titleKey) }}</h3><p v-if="node.descriptionKey">{{ label(node.descriptionKey) }}</p><WorkflowNodeStatusBadge :status="currentStatus" /></div>
      <a-tabs class="inspector-detail-tabs">
        <a-tab-pane key="config" :tab="t('workflow.inspector.configTab')"><NodeToolPanel :node="node" :project-id="projectId" :selected-tool-slug="selectedToolSlug" :available-tools="availableTools" :recommended-artifacts="inputRecommendations" @select-tool="$emit('select-tool', node.id, $event)" /></a-tab-pane>
        <a-tab-pane key="dependencies" :tab="t('workflow.inspector.dependenciesTab')"><NodeEdgePanel :node="node" :template="template" :artifacts="artifacts" :task-by-node="taskByNode" @add-edge="$emit('add-edge', $event)" @delete-edge="$emit('delete-edge', $event)" /></a-tab-pane>
        <a-tab-pane key="results" :tab="t('workflow.inspector.resultsTab')"><NodeResultPanel :node="node" :task="task" :artifacts="artifacts" :selected-tool-slug="selectedToolSlug" @run-node="$emit('run-node', $event)" @view-task-detail="$emit('view-task-detail', $event)" /></a-tab-pane>
      </a-tabs>
    </template>
  </aside>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ArtifactFile } from '@/types/models'
import type { WorkflowArtifactSemanticType, WorkflowStepStatus, WorkflowTaskRef } from '@/workflow/artifact-types'
import type { WorkflowCanvasNode, WorkflowCanvasPreset } from '@/workflow/canvas-types'
import { recommendArtifactsForNode } from '@/workflow/canvas-artifacts'
import NodeEdgePanel from './NodeEdgePanel.vue'
import NodeResultPanel from './NodeResultPanel.vue'
import NodeToolPanel from './NodeToolPanel.vue'
import WorkflowNodeStatusBadge from './WorkflowNodeStatusBadge.vue'
interface WorkflowAvailableTool { id?: string; slug: string; name: string; description?: string }
const props = defineProps<{ node: WorkflowCanvasNode | null; projectId?: string | null; template?: WorkflowCanvasPreset | null; artifacts?: ArtifactFile[]; taskByNode?: Record<string, WorkflowTaskRef>; availableTools?: WorkflowAvailableTool[]; status?: WorkflowStepStatus; selectedToolSlug?: string | null; task?: WorkflowTaskRef | null }>()
defineEmits<{ (event: 'select-tool', nodeId: string, toolSlug: string): void; (event: 'add-edge', input: { source: string; target: string; artifactType: WorkflowArtifactSemanticType }): void; (event: 'delete-edge', edgeId: string): void; (event: 'run-node', nodeId: string): void; (event: 'view-task-detail', nodeId: string): void }>()
const { t, te } = useI18n(); const currentStatus = computed<WorkflowStepStatus>(() => props.status ?? 'idle')
const inputRecommendations = computed(() => props.node && props.template ? recommendArtifactsForNode({ template: props.template, nodeId: props.node.id, artifacts: props.artifacts ?? [], taskByNode: props.taskByNode ?? {} }) : [])
function label(key: string) { if (te(key)) return t(key); return (key.split('.').pop() ?? key).replace(/([A-Z])/g, ' $1').replace(/[-_]/g, ' ').trim() }
</script>
<style scoped lang="less">@import '@/assets/styles/variables.less'; .workflow-node-inspector { min-width:0; max-height:720px; overflow:auto; border:1px solid @border-color-hover; border-radius:@border-radius-md; background:@bg-surface; box-shadow:@shadow-sm; } .inspector-empty { min-height:360px; display:flex; align-items:center; justify-content:center; } .inspector-header { padding:@spacing-lg; border-bottom:1px solid @border-color-light; } h3 { margin:4px 0 @spacing-xs; color:@text-color-light-primary; font-size:@font-size-lg; } p { margin:0 0 @spacing-md; color:@text-color-light-secondary; font-size:@font-size-sm; } .inspector-kicker { color:@text-color-light-tertiary; font-size:@font-size-xs; font-weight:800; text-transform:uppercase; }</style>
