<template>
  <section class="workflow-column workspace-column">
    <div class="column-card">
      <h2 class="column-title">{{ t('workflow.columns.workspace') }}</h2>
      <p class="column-subtitle">{{ t('workflow.columns.workspaceHint') }}</p>

      <div class="active-step-banner">
        <span class="active-step-label">{{ t('workflow.columns.tools') }}</span>
        <strong class="active-step-value">{{ t(`workflow.steps.${step.key}.title`) }}</strong>
      </div>

      <div class="placeholder-list">
        <div class="placeholder-card">
          <h3 class="placeholder-title">{{ t('workflow.placeholders.inputSummary.title') }}</h3>
          <div v-if="sessionArtifacts.length" class="artifact-list">
            <div v-for="artifact in sessionArtifacts" :key="artifact.id" class="artifact-item">
              <div class="artifact-copy">
                <strong class="artifact-name">{{ artifact.name }}</strong>
                <p class="artifact-meta">
                  {{ artifact.semanticType }} · {{ t(`workflow.steps.${artifact.stepKey}.title`) }}
                </p>
              </div>
              <div class="artifact-tags">
                <a-tag v-if="isInvalidArtifact(artifact.id)">{{ t('workflow.artifacts.invalidated') }}</a-tag>
                <a-tag v-else color="green">{{ t('workflow.artifacts.ready') }}</a-tag>
              </div>
            </div>
          </div>
          <p v-else class="placeholder-desc">{{ t('workflow.placeholders.inputSummary.description') }}</p>
        </div>
        <div class="placeholder-card">
          <h3 class="placeholder-title">{{ t('workflow.placeholders.resultPreview.title') }}</h3>
          <div v-if="activeTask" class="task-summary">
            <div class="task-summary-row">
              <span class="task-summary-label">{{ t('tasks.status') }}</span>
              <span class="task-summary-value">{{ activeTask.status }}</span>
            </div>
            <div class="task-summary-row">
              <span class="task-summary-label">{{ t('tasks.progress') }}</span>
              <span class="task-summary-value">{{ activeTask.progress }}%</span>
            </div>
          </div>
          <p v-else class="placeholder-desc">{{ t('workflow.placeholders.resultPreview.description') }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { useWorkflowStore } from '@/stores'
  import type { WorkflowStepCatalogItem } from '@/workflow/aidd-catalog'

  const props = defineProps<{
    step: WorkflowStepCatalogItem
  }>()

  const { t } = useI18n()
  const workflowStore = useWorkflowStore()

  const sessionArtifacts = computed(() => {
    return [...workflowStore.artifacts].sort((left, right) => {
      return Date.parse(right.createdAt) - Date.parse(left.createdAt)
    })
  })

  const activeTask = computed(() => workflowStore.taskByStep[props.step.key] ?? null)

  function isInvalidArtifact(artifactId: string): boolean {
    return workflowStore.invalidArtifactIds.includes(artifactId)
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-column {
    min-width: 0;
  }

  .column-card {
    .card();
    height: 100%;
  }

  .column-title {
    font-size: @font-size-xl;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-xs;
  }

  .column-subtitle {
    color: @text-color-light-secondary;
    margin-bottom: @spacing-lg;
  }

  .active-step-banner {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    padding: @spacing-sm @spacing-md;
    margin-bottom: @spacing-md;
    background: @bg-card-light;
  }

  .active-step-label {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .active-step-value {
    color: @text-color-primary;
    font-size: @font-size-md;
  }

  .placeholder-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-md;
  }

  .placeholder-card {
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    padding: @spacing-md;
    background: @bg-card-light;
  }

  .artifact-list,
  .task-summary {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .artifact-item,
  .task-summary-row {
    display: flex;
    justify-content: space-between;
    gap: @spacing-sm;
    align-items: flex-start;
  }

  .artifact-copy {
    min-width: 0;
  }

  .artifact-name {
    display: block;
    font-size: @font-size-sm;
    margin-bottom: @spacing-xs;
  }

  .artifact-meta,
  .task-summary-label,
  .task-summary-value {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .artifact-tags {
    flex-shrink: 0;
  }

  .placeholder-title {
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-xs;
  }

  .placeholder-desc {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
  }
</style>
