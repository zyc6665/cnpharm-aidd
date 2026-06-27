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
        <h3>{{ resolveLabel(node.titleKey) }}</h3>
        <p v-if="node.descriptionKey">{{ resolveLabel(node.descriptionKey) }}</p>
        <WorkflowNodeStatusBadge :status="status" />
      </div>

      <a-tabs class="inspector-detail-tabs">
        <a-tab-pane key="config" :tab="t('workflow.inspector.configTab')">
          <section class="inspector-section">
            <div class="section-title">{{ t('workflow.inspector.toolSelector') }}</div>
            <a-select
              v-if="node.type === 'tool'"
              class="tool-selector"
              :value="selectedToolSlug"
              :options="toolOptions"
              :placeholder="t('workflow.inspector.selectTool')"
              @change="handleToolChange"
            />
            <a-alert
              v-else
              type="info"
              show-icon
              :message="t('workflow.inspector.noToolRequired')"
            />
          </section>

          <section v-if="node.type === 'tool'" class="inspector-section">
            <div class="section-title">{{ t('workflow.inspector.nodeExecution') }}</div>
            <WorkflowNodeRunPanel
              :node-id="node.id"
              :selected-tool-slug="selectedToolSlug"
              :available-tools="availableTools"
              :recommended-artifacts="inputRecommendations"
              @task-submitted="$emit('task-submitted', $event)"
            />
          </section>

          <div v-else class="inspector-actions">
            <a-button type="primary" block :disabled="!canRun" @click="$emit('run-node', node.id)">
              <PlayCircleOutlined />
              {{ t('workflow.inspector.runCurrentNode') }}
            </a-button>
          </div>
        </a-tab-pane>

        <a-tab-pane key="dependencies" :tab="t('workflow.inspector.dependenciesTab')">
          <section v-if="node.type !== 'input'" class="inspector-section">
            <div class="section-title">{{ t('workflow.inspector.recommendedEdges') }}</div>
            <div v-if="edgeSuggestions.length" class="edge-suggestion-list">
              <div
                v-for="suggestion in edgeSuggestions"
                :key="`${suggestion.sourceNodeId}-${suggestion.semanticType}`"
                class="edge-suggestion-item"
              >
                <span class="edge-suggestion-copy">
                  <strong>{{ suggestion.sourceNodeTitle }}</strong>
                  <small>{{ suggestion.semanticType }}</small>
                </span>
                <a-button size="small" type="primary" ghost @click="handleAddSuggestedEdge(suggestion)">
                  {{ t('workflow.inspector.addEdge') }}
                </a-button>
              </div>
            </div>
            <a-empty v-else :description="t('workflow.inspector.noRecommendedEdges')" />
          </section>

          <section v-if="node.type !== 'input'" class="inspector-section">
            <div class="section-title">{{ t('workflow.inspector.upstreamEdge') }}</div>
            <div v-if="upstreamEdges.length" class="upstream-edge-list">
              <div v-for="edge in upstreamEdges" :key="edge.id" class="upstream-edge-item">
                <span class="upstream-edge-copy">
                  <strong>{{ formatNodeTitle(edge.source) }}</strong>
                  <small>{{ edge.artifactType ?? t('workflow.inspector.artifactFallback') }}</small>
                </span>
                <a-button size="small" danger @click="handleDeleteEdge(edge.id)">
                  {{ t('workflow.inspector.deleteEdge') }}
                </a-button>
              </div>
            </div>
            <div class="edge-editor">
              <a-select
                v-model:value="edgeSourceNodeId"
                class="edge-select"
                :placeholder="t('workflow.inspector.sourceNode')"
                :options="sourceNodeOptions"
              />
              <a-select
                v-model:value="edgeArtifactType"
                class="edge-select"
                :placeholder="t('workflow.inspector.artifactType')"
                :options="artifactTypeOptions"
              />
              <a-button block :disabled="!edgeSourceNodeId || !edgeArtifactType" @click="handleAddEdge">
                {{ t('workflow.inspector.addEdge') }}
              </a-button>
            </div>
          </section>

          <section class="inspector-section">
            <div class="section-title">{{ t('workflow.inspector.requiredInput') }}</div>
            <div v-if="inputRecommendations.length" class="input-recommendation-list">
              <div
                v-for="recommendation in inputRecommendations"
                :key="`${recommendation.edgeId}-${recommendation.semanticType}`"
                class="input-recommendation"
              >
                <a-tag color="blue">{{ recommendation.semanticType }}</a-tag>
                <span v-if="recommendation.artifact" class="artifact-name">
                  {{ recommendation.artifact.filename }}
                </span>
                <span v-else class="artifact-missing">{{ t('workflow.inspector.missingArtifact') }}</span>
              </div>
            </div>
            <div v-else-if="node.requiredInputTypes?.length" class="semantic-list">
              <a-tag v-for="inputType in node.requiredInputTypes" :key="inputType" color="blue">
                {{ inputType }}
              </a-tag>
            </div>
            <a-empty v-else :description="t('workflow.inspector.noRequiredInput')" />
          </section>

          <section class="inspector-section">
            <div class="section-title">{{ t('workflow.inspector.producedOutput') }}</div>
            <div v-if="node.producedOutputTypes?.length" class="semantic-list">
              <a-tag v-for="outputType in node.producedOutputTypes" :key="outputType" color="green">
                {{ outputType }}
              </a-tag>
            </div>
            <a-empty v-else :description="t('workflow.inspector.noProducedOutput')" />
          </section>
        </a-tab-pane>

        <a-tab-pane key="results" :tab="t('workflow.inspector.resultsTab')">
          <section class="inspector-section">
            <div class="section-title">{{ t('workflow.inspector.taskResult') }}</div>
            <div v-if="node.type === 'tool'" class="result-actions">
              <a-button size="small" type="primary" :disabled="!canRerun" @click="$emit('run-node', node.id)">
                {{ t('workflow.inspector.rerunCurrentNode') }}
              </a-button>
              <a-button size="small" :disabled="!task" @click="$emit('rerun-downstream', node.id)">
                {{ t('workflow.inspector.rerunDownstream') }}
              </a-button>
              <a-button size="small" :disabled="!task" @click="$emit('view-task-detail', node.id)">
                {{ t('workflow.inspector.viewTaskDetail') }}
              </a-button>
            </div>
            <div v-if="task" class="task-result">
              <span class="task-id">{{ task.id }}</span>
              <a-tag>{{ task.status }}</a-tag>
              <a-progress
                v-if="task.status === 'running' || task.status === 'pending'"
                :percent="task.progress ?? 0"
                size="small"
              />
              <p v-if="task.error_message" class="task-error">{{ task.error_message }}</p>
            </div>
            <a-empty v-else :description="t('workflow.inspector.noTaskResult')" />
          </section>

          <section class="inspector-section">
            <div class="section-title">{{ t('workflow.inspector.outputFiles') }}</div>
            <div v-if="outputArtifacts.length" class="output-artifact-list">
              <div v-for="artifact in outputArtifacts" :key="artifact.id" class="output-artifact-item">
                <span class="output-artifact-copy">
                  <strong>{{ artifact.filename }}</strong>
                  <small>{{ artifact.semantic_type || t('workflow.inspector.artifactFallback') }}</small>
                </span>
                <a-button size="small" @click="handleDownloadOutput(artifact)">
                  {{ t('workflow.inspector.downloadOutput') }}
                </a-button>
              </div>
            </div>
            <a-empty v-else :description="t('workflow.inspector.noOutputFiles')" />
          </section>
        </a-tab-pane>
      </a-tabs>
    </template>
  </aside>
</template>

<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import { PlayCircleOutlined } from '@ant-design/icons-vue'
  import {
    WORKFLOW_ARTIFACT_SEMANTIC_TYPES,
    type WorkflowArtifactSemanticType,
    type WorkflowStepStatus,
    type WorkflowTaskRef
  } from '@/workflow/artifact-types'
  import {
    recommendArtifactsForNode,
    suggestWorkflowEdgesForNode,
    type WorkflowEdgeSuggestion
  } from '@/workflow/template-artifacts'
  import type { WorkflowCanvasNode } from '@/workflow/template-types'
  import type { WorkflowTemplate } from '@/workflow/template-types'
  import type { ArtifactFile } from '@/types/models'
  import { triggerProtectedFileDownload } from '@/utils/protected-file-access'
  import WorkflowNodeRunPanel from './WorkflowNodeRunPanel.vue'
  import WorkflowNodeStatusBadge from './WorkflowNodeStatusBadge.vue'

  interface WorkflowAvailableTool {
    id?: string
    slug: string
    name: string
    description?: string
  }

  const props = defineProps<{
    node: WorkflowCanvasNode | null
    template?: WorkflowTemplate | null
    artifacts?: ArtifactFile[]
    taskByNode?: Record<string, WorkflowTaskRef>
    availableTools?: WorkflowAvailableTool[]
    status?: WorkflowStepStatus
    selectedToolSlug?: string | null
    task?: WorkflowTaskRef | null
  }>()

  const emit = defineEmits<{
    (event: 'select-tool', nodeId: string, toolSlug: string): void
    (event: 'add-edge', input: { source: string; target: string; artifactType: WorkflowArtifactSemanticType }): void
    (event: 'delete-edge', edgeId: string): void
    (event: 'run-node', nodeId: string): void
    (event: 'rerun-downstream', nodeId: string): void
    (event: 'view-task-detail', nodeId: string): void
    (event: 'task-submitted', taskId: string): void
  }>()

  const edgeSourceNodeId = ref<string | undefined>()
  const edgeArtifactType = ref<WorkflowArtifactSemanticType | undefined>()
  const status = computed<WorkflowStepStatus>(() => props.status ?? 'idle')
  const { t, te } = useI18n()

  const toolOptions = computed(() => {
    const tools = props.availableTools?.length
      ? props.availableTools
      : (props.node?.toolSlugs ?? []).map(toolSlug => ({ slug: toolSlug, name: toolSlug }))

    return tools.map(tool => ({
      value: tool.slug,
      label: tool.name || tool.slug
    }))
  })

  const sourceNodeOptions = computed(() => {
    return (props.template?.nodes ?? [])
      .filter(item => item.id !== props.node?.id)
      .map(item => ({
        value: item.id,
        label: resolveLabel(item.titleKey)
      }))
  })

  const nodeTitleById = computed(() => {
    return (props.template?.nodes ?? []).reduce<Record<string, string>>((titles, item) => {
      titles[item.id] = resolveLabel(item.titleKey)
      return titles
    }, {})
  })

  const upstreamEdges = computed(() => {
    if (!props.node || !props.template) {
      return []
    }

    return props.template.edges.filter(edge => edge.target === props.node?.id)
  })

  const artifactTypeOptions = computed(() => {
    return WORKFLOW_ARTIFACT_SEMANTIC_TYPES.map(semanticType => ({
      value: semanticType,
      label: semanticType
    }))
  })

  const inputRecommendations = computed(() => {
    if (!props.node || !props.template) {
      return []
    }

    return recommendArtifactsForNode({
      template: props.template,
      nodeId: props.node.id,
      artifacts: props.artifacts ?? [],
      taskByNode: props.taskByNode ?? {}
    })
  })

  const edgeSuggestions = computed(() => {
    if (!props.node || !props.template) {
      return []
    }

    return suggestWorkflowEdgesForNode({
      template: props.template,
      nodeId: props.node.id
    })
  })

  const canRun = computed(() => {
    if (!props.node || props.node.type !== 'tool') {
      return false
    }

    return status.value === 'ready' || status.value === 'failed' || status.value === 'invalidated'
  })

  const canRerun = computed(() => {
    if (!props.node || props.node.type !== 'tool') {
      return false
    }

    return Boolean(props.selectedToolSlug || props.node.recommendedToolSlug || props.node.toolSlugs?.[0])
  })

  const outputArtifacts = computed(() => {
    if (!props.task?.id) {
      return []
    }

    return (props.artifacts ?? []).filter((artifact) => artifact.task_id === props.task?.id)
  })

  function handleToolChange(toolSlug: unknown) {
    if (!props.node || typeof toolSlug !== 'string') {
      return
    }

    emit('select-tool', props.node.id, toolSlug)
  }

  function handleAddEdge() {
    if (!props.node || !edgeSourceNodeId.value || !edgeArtifactType.value) {
      return
    }

    emit('add-edge', {
      source: edgeSourceNodeId.value,
      target: props.node.id,
      artifactType: edgeArtifactType.value
    })
  }

  function handleAddSuggestedEdge(suggestion: WorkflowEdgeSuggestion) {
    emit('add-edge', {
      source: suggestion.sourceNodeId,
      target: suggestion.targetNodeId,
      artifactType: suggestion.semanticType
    })
  }

  function handleDeleteEdge(edgeId: string) {
    emit('delete-edge', edgeId)
  }

  function formatNodeTitle(nodeId: string): string {
    return nodeTitleById.value[nodeId] ?? nodeId
  }

  async function handleDownloadOutput(artifact: ArtifactFile) {
    try {
      await triggerProtectedFileDownload({
        url: artifact.download_url,
        filename: artifact.filename,
        original_name: artifact.filename,
      })
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('common.error'))
    }
  }

  watch(
    () => props.node?.id,
    () => {
      edgeSourceNodeId.value = undefined
      edgeArtifactType.value = undefined
    }
  )

  function resolveLabel(key: string): string {
    if (te(key)) {
      return t(key)
    }

    const segments = key.split('.')
    const lastSegment = segments[segments.length - 1] ?? key
    return lastSegment
      .replace(/([A-Z])/g, ' $1')
      .replace(/[-_]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-node-inspector {
    min-width: 0;
    max-height: 720px;
    overflow: auto;
    border: 1px solid @border-color-hover;
    border-radius: @border-radius-md;
    background: @bg-light-secondary;
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

  .inspector-header h3 {
    margin: 4px 0 @spacing-xs;
    color: @text-color-light-primary;
    font-size: @font-size-lg;
    font-weight: 800;
  }

  .inspector-header p {
    margin: 0 0 @spacing-md;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: 1.5;
  }

  .inspector-kicker,
  .section-title {
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: 800;
    letter-spacing: 0;
    text-transform: uppercase;
  }

  .inspector-section {
    padding: @spacing-md @spacing-lg;
    border-bottom: 1px solid @border-color-light;
  }

  .tool-selector {
    width: 100%;
    margin-top: @spacing-sm;
  }

  .edge-editor {
    display: grid;
    gap: @spacing-sm;
    margin-top: @spacing-sm;
  }

  .edge-suggestion-list,
  .upstream-edge-list {
    display: grid;
    gap: @spacing-xs;
    margin-top: @spacing-sm;
  }

  .edge-suggestion-item,
  .upstream-edge-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-sm;
    padding: @spacing-xs @spacing-sm;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-sm;
    background: rgba(255, 255, 255, 0.74);
  }

  .edge-suggestion-item {
    border-color: @accent-color-border;
    background: @accent-color-light;
  }

  .edge-suggestion-copy,
  .upstream-edge-copy {
    min-width: 0;
    display: grid;
    gap: 2px;
  }

  .edge-suggestion-copy strong,
  .edge-suggestion-copy small,
  .upstream-edge-copy strong,
  .upstream-edge-copy small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .edge-suggestion-copy strong,
  .upstream-edge-copy strong {
    color: @text-color-light-primary;
    font-size: @font-size-xs;
  }

  .edge-suggestion-copy small,
  .upstream-edge-copy small {
    color: @text-color-light-secondary;
  }

  .edge-select {
    width: 100%;
  }

  .semantic-list {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-xs;
    margin-top: @spacing-sm;
  }

  .input-recommendation-list {
    display: grid;
    gap: @spacing-sm;
    margin-top: @spacing-sm;
  }

  .input-recommendation {
    display: flex;
    align-items: center;
    gap: @spacing-xs;
    min-width: 0;
  }

  .artifact-name,
  .artifact-missing {
    min-width: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .artifact-missing {
    color: @warning-color;
  }

  .task-result {
    display: grid;
    gap: @spacing-sm;
    margin-top: @spacing-sm;
  }

  .result-actions,
  .output-artifact-list {
    display: grid;
    gap: @spacing-sm;
    margin-top: @spacing-sm;
  }

  .result-actions {
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  }

  .output-artifact-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-sm;
    padding: @spacing-xs @spacing-sm;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-sm;
    background: rgba(255, 255, 255, 0.74);
  }

  .output-artifact-copy {
    min-width: 0;
    display: grid;
    gap: 2px;
  }

  .output-artifact-copy strong,
  .output-artifact-copy small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .output-artifact-copy strong {
    color: @text-color-light-primary;
    font-size: @font-size-xs;
  }

  .output-artifact-copy small {
    color: @text-color-light-secondary;
  }

  .task-id {
    color: @text-color-light-secondary;
    font-family: @font-family-mono;
    font-size: @font-size-xs;
  }

  .task-error {
    margin: 0;
    color: @error-color;
    font-size: @font-size-sm;
  }

  .inspector-actions {
    padding: @spacing-lg;
  }
</style>
