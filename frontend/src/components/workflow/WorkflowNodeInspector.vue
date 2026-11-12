<template>
  <aside class="workflow-node-inspector">
    <a-empty
      v-if="!node"
      class="inspector-empty"
      :description="t('workflow.inspector.noSelectedNode')"
    />
    <template v-else>
      <div class="inspector-header">
        <span class="inspector-kicker">{{ t(`workflow.nodeType.${node.type}`) }}</span>
        <h3>{{ label(node.titleKey) }}</h3>
        <p v-if="node.descriptionKey">{{ label(node.descriptionKey) }}</p>
        <WorkflowNodeStatusBadge :status="currentStatus" />
      </div>

      <a-tabs v-model:activeKey="activeTabKey" class="inspector-detail-tabs">
        <a-tab-pane key="config" :tab="t('workflow.inspector.configTab')">
          <NodeInputBindingPanel
            v-if="node.type === 'input'"
            :node="node"
            :template="template"
            :requirements="inputRequirements ?? []"
            :selections="inputSelections ?? {}"
            :options-by-semantic-type="inputOptionsBySemanticType ?? {}"
            :loading="inputOptionsLoading"
            :can-upload="canUploadInput"
            :uploading-key="uploadingInputKey"
            @select="relayInputSelect"
            @upload="relayInputUpload"
          />
          <NodeToolPanel
            v-else
            :node="node"
            :project-id="projectId"
            :selected-tool-slug="selectedToolSlug"
            :available-tools="availableTools"
            :recommended-artifacts="inputRecommendations"
            @select-tool="relaySelectTool"
            @update-node="relayNodeUpdate"
          />
        </a-tab-pane>
        <a-tab-pane key="dependencies" :tab="t('workflow.inspector.dependenciesTab')">
          <NodeEdgePanel
            :node="node"
            :template="template"
            :artifacts="artifacts"
            :task-by-node="taskByNode"
            @add-edge="relayAddEdge"
            @delete-edge="relayDeleteEdge"
            @update-edge-branch="relayEdgeBranchUpdate"
          />
        </a-tab-pane>
        <a-tab-pane key="results" :tab="t('workflow.inspector.resultsTab')">
          <NodeResultPanel
            :node="node"
            :task="task"
            :artifacts="artifacts"
            :selected-tool-slug="selectedToolSlug"
            @configure-node="focusConfiguration"
            @view-task-detail="relayViewTaskDetail"
          />
        </a-tab-pane>
      </a-tabs>
    </template>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ArtifactFile } from '@/types/models'
import type {
  WorkflowArtifactSemanticType,
  WorkflowStepStatus,
  WorkflowTaskRef,
} from '@/workflow/artifact-types'
import { recommendArtifactsForNode } from '@/workflow/canvas-artifacts'
import type {
  WorkflowCanvasEdge,
  WorkflowCanvasNode,
  WorkflowCanvasPreset,
} from '@/workflow/canvas-types'
import NodeEdgePanel from './NodeEdgePanel.vue'
import NodeInputBindingPanel from './NodeInputBindingPanel.vue'
import NodeResultPanel from './NodeResultPanel.vue'
import NodeToolPanel from './NodeToolPanel.vue'
import WorkflowNodeStatusBadge from './WorkflowNodeStatusBadge.vue'
import type { WorkflowInputRequirement } from '@/workflow/workflow-definitions'

interface WorkflowAvailableTool {
  id?: string
  slug: string
  name: string
  description?: string
}

const props = defineProps<{
  node: WorkflowCanvasNode | null
  projectId?: string | null
  template?: WorkflowCanvasPreset | null
  artifacts?: ArtifactFile[]
  taskByNode?: Record<string, WorkflowTaskRef>
  availableTools?: WorkflowAvailableTool[]
  status?: WorkflowStepStatus
  selectedToolSlug?: string | null
  task?: WorkflowTaskRef | null
  inputRequirements?: WorkflowInputRequirement[]
  inputSelections?: Record<string, string | undefined>
  inputOptionsBySemanticType?: Record<string, Array<{ value: string; label: string }>>
  inputOptionsLoading?: boolean
  canUploadInput?: boolean
  uploadingInputKey?: string | null
}>()

const emit = defineEmits<{
  (event: 'select-tool', nodeId: string, toolSlug: string): void
  (event: 'update-node', nodeId: string, changes: Partial<WorkflowCanvasNode>): void
  (
    event: 'add-edge',
    input: { source: string; target: string; artifactType: WorkflowArtifactSemanticType }
  ): void
  (event: 'delete-edge', edgeId: string): void
  (event: 'update-edge-branch', edgeId: string, branch: WorkflowCanvasEdge['branch']): void
  (event: 'view-task-detail', nodeId: string): void
  (event: 'select-input', requirementKey: string, artifactId: string | undefined): void
  (event: 'upload-input', requirementKey: string, file: File): void
}>()

const { t, te } = useI18n()
const activeTabKey = ref('config')
const currentStatus = computed<WorkflowStepStatus>(() => props.status ?? 'idle')
const inputRecommendations = computed(() => {
  if (!props.node || !props.template) return []
  return recommendArtifactsForNode({
    template: props.template,
    nodeId: props.node.id,
    artifacts: props.artifacts ?? [],
    taskByNode: props.taskByNode ?? {},
  })
})

function focusConfiguration() {
  activeTabKey.value = 'config'
}

function relaySelectTool(toolSlug: string) {
  if (props.node) emit('select-tool', props.node.id, toolSlug)
}

function relayNodeUpdate(nodeId: string, changes: Partial<WorkflowCanvasNode>) {
  emit('update-node', nodeId, changes)
}

function relayAddEdge(input: {
  source: string
  target: string
  artifactType: WorkflowArtifactSemanticType
}) {
  emit('add-edge', input)
}

function relayDeleteEdge(edgeId: string) {
  emit('delete-edge', edgeId)
}

function relayEdgeBranchUpdate(edgeId: string, branch: WorkflowCanvasEdge['branch']) {
  emit('update-edge-branch', edgeId, branch)
}

function relayViewTaskDetail(nodeId: string) {
  emit('view-task-detail', nodeId)
}

function label(key: string) {
  if (te(key)) return t(key)
  return (key.split('.').pop() ?? key).replace(/([A-Z])/g, ' $1').replace(/[-_]/g, ' ').trim()
}

function relayInputSelect(requirementKey: string, artifactId: string | undefined) {
  emit('select-input', requirementKey, artifactId)
}

function relayInputUpload(requirementKey: string, file: File) {
  emit('upload-input', requirementKey, file)
}

watch(() => props.node?.id, focusConfiguration)

defineExpose({ focusConfiguration })
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.workflow-node-inspector {
  min-width: 0;
  max-height: 720px;
  overflow: auto;
  border: 1px solid @border-color-hover;
  border-radius: @border-radius-md;
  background: @bg-surface;
  box-shadow: @shadow-sm;
}

.inspector-empty {
  min-height: 360px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.inspector-header {
  padding: @spacing-lg;
  border-bottom: 1px solid @border-color-light;
}

h3 {
  margin: 4px 0 @spacing-xs;
  color: @text-color-light-primary;
  font-size: @font-size-lg;
}

p {
  margin: 0 0 @spacing-md;
  color: @text-color-light-secondary;
  font-size: @font-size-sm;
}

.inspector-kicker {
  color: @text-color-light-tertiary;
  font-size: @font-size-xs;
  font-weight: 800;
  text-transform: uppercase;
}
</style>
