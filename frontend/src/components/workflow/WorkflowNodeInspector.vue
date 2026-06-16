<template>
  <aside class="workflow-node-inspector">
    <a-empty
      v-if="!node"
      class="inspector-empty"
      description="No selected node"
    />

    <template v-else>
      <div class="inspector-header">
        <span class="inspector-kicker">{{ node.type }}</span>
        <h3>{{ formatKey(node.titleKey) }}</h3>
        <p v-if="node.descriptionKey">{{ formatKey(node.descriptionKey) }}</p>
        <WorkflowNodeStatusBadge :status="status" />
      </div>

      <section class="inspector-section">
        <div class="section-title">Tool selector</div>
        <a-select
          v-if="node.toolSlugs?.length"
          class="tool-selector"
          :value="selectedToolSlug"
          :options="toolOptions"
          placeholder="Select tool"
          @change="handleToolChange"
        />
        <a-alert
          v-else
          type="info"
          show-icon
          message="This node does not require a tool."
        />
      </section>

      <section class="inspector-section">
        <div class="section-title">Required input</div>
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
            <span v-else class="artifact-missing">Missing upstream artifact</span>
          </div>
        </div>
        <div v-else-if="node.requiredInputTypes?.length" class="semantic-list">
          <a-tag v-for="inputType in node.requiredInputTypes" :key="inputType" color="blue">
            {{ inputType }}
          </a-tag>
        </div>
        <a-empty v-else :image="null" description="No required input" />
      </section>

      <section class="inspector-section">
        <div class="section-title">Produced output</div>
        <div v-if="node.producedOutputTypes?.length" class="semantic-list">
          <a-tag v-for="outputType in node.producedOutputTypes" :key="outputType" color="green">
            {{ outputType }}
          </a-tag>
        </div>
        <a-empty v-else :image="null" description="No produced output" />
      </section>

      <section class="inspector-section">
        <div class="section-title">Task result</div>
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
        <a-empty v-else :image="null" description="No task result" />
      </section>

      <div class="inspector-actions">
        <a-button type="primary" block :disabled="!canRun" @click="$emit('run-node', node.id)">
          <PlayCircleOutlined />
          Run current node
        </a-button>
      </div>
    </template>
  </aside>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { PlayCircleOutlined } from '@ant-design/icons-vue'
  import type { WorkflowStepStatus, WorkflowTaskRef } from '@/workflow/artifact-types'
  import { recommendArtifactsForNode } from '@/workflow/template-artifacts'
  import type { WorkflowCanvasNode } from '@/workflow/template-types'
  import type { WorkflowTemplate } from '@/workflow/template-types'
  import type { ArtifactFile } from '@/types/models'
  import WorkflowNodeStatusBadge from './WorkflowNodeStatusBadge.vue'

  const props = defineProps<{
    node: WorkflowCanvasNode | null
    template?: WorkflowTemplate | null
    artifacts?: ArtifactFile[]
    taskByNode?: Record<string, WorkflowTaskRef>
    status?: WorkflowStepStatus
    selectedToolSlug?: string | null
    task?: WorkflowTaskRef | null
  }>()

  const emit = defineEmits<{
    (event: 'select-tool', nodeId: string, toolSlug: string): void
    (event: 'run-node', nodeId: string): void
  }>()

  const status = computed<WorkflowStepStatus>(() => props.status ?? 'idle')

  const toolOptions = computed(() => {
    return (props.node?.toolSlugs ?? []).map(toolSlug => ({
      value: toolSlug,
      label: toolSlug
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

  const canRun = computed(() => {
    if (!props.node || props.node.type !== 'tool') {
      return false
    }

    return status.value === 'ready' || status.value === 'failed' || status.value === 'invalidated'
  })

  function handleToolChange(toolSlug: unknown) {
    if (!props.node || typeof toolSlug !== 'string') {
      return
    }

    emit('select-tool', props.node.id, toolSlug)
  }

  function formatKey(key: string): string {
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
    border: 1px solid rgba(24, 144, 255, 0.12);
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
