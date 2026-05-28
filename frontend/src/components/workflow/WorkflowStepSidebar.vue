<template>
  <section class="workflow-column steps-column">
    <div class="column-card">
      <h2 class="column-title">{{ t('workflow.columns.steps') }}</h2>
      <p class="column-subtitle">{{ t('workflow.columns.stepsHint') }}</p>

      <div class="step-list">
        <div
          v-for="(step, index) in steps"
          :key="step.key"
          :class="['step-card', { 'step-card-active': isActiveStep(step.key, index) }]"
          @click="selectStep(step.key)"
        >
          <div class="step-index">0{{ index + 1 }}</div>
          <div class="step-copy">
            <h3 class="step-title">{{ t(`workflow.steps.${step.key}.title`) }}</h3>
            <p class="step-desc">{{ t(`workflow.steps.${step.key}.description`) }}</p>
            <div class="step-status-row">
              <a-tag :color="getStepStatusColor(getStepStatus(step.key))">
                {{ t(`workflow.stepStatus.${getStepStatus(step.key)}`) }}
              </a-tag>
            </div>
            <div v-if="getToolViewModel(step.key)" class="step-meta">
              <a-tag color="green">
                {{ t('workflow.toolStatus.availableCount', { count: getToolViewModel(step.key)?.availableToolSlugs.length ?? 0 }) }}
              </a-tag>
              <a-tag v-if="(getToolViewModel(step.key)?.missingToolSlugs.length ?? 0) > 0">
                {{ t('workflow.toolStatus.missingCount', { count: getToolViewModel(step.key)?.missingToolSlugs.length ?? 0 }) }}
              </a-tag>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import type { WorkflowStepCatalogItem } from '@/workflow/aidd-catalog'
  import type { WorkflowStepKey, WorkflowStepStateMap, WorkflowStepStatus } from '@/workflow/artifact-types'
  import type { WorkflowStepToolViewModel } from '@/workflow/step-tools'

  const props = defineProps<{
    steps: readonly WorkflowStepCatalogItem[]
    activeStepKey?: WorkflowStepKey | null
    stepStates?: WorkflowStepStateMap
    toolViewModels?: Partial<Record<WorkflowStepKey, WorkflowStepToolViewModel>>
  }>()

  const emit = defineEmits<{
    select: [stepKey: WorkflowStepKey]
  }>()

  const { t } = useI18n()

  function isActiveStep(stepKey: WorkflowStepKey, index: number): boolean {
    if (props.activeStepKey) {
      return props.activeStepKey === stepKey
    }

    return index === 0
  }

  function getToolViewModel(stepKey: WorkflowStepKey): WorkflowStepToolViewModel | null {
    return props.toolViewModels?.[stepKey] ?? null
  }

  function getStepStatus(stepKey: WorkflowStepKey): WorkflowStepStatus {
    return props.stepStates?.[stepKey]?.status ?? 'idle'
  }

  function getStepStatusColor(status: WorkflowStepStatus): string | undefined {
    const colorMap: Partial<Record<WorkflowStepStatus, string>> = {
      ready: 'blue',
      running: 'processing',
      completed: 'green',
      failed: 'red',
      invalidated: 'orange',
      needs_tool_selection: 'gold'
    }

    return colorMap[status]
  }

  function selectStep(stepKey: WorkflowStepKey) {
    emit('select', stepKey)
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

  .step-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-md;
  }

  .step-card {
    display: flex;
    gap: @spacing-md;
    align-items: flex-start;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    padding: @spacing-md;
    background: @bg-card-light;
    cursor: pointer;
    transition: border-color 0.2s ease, transform 0.2s ease;

    &:hover {
      border-color: @accent-color;
      transform: translateY(-1px);
    }
  }

  .step-card-active {
    border-color: @accent-color;
    box-shadow: @shadow-sm;
  }

  .step-index {
    min-width: 44px;
    height: 44px;
    border-radius: @border-radius-round;
    background: @accent-color-light;
    color: @accent-color;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: @font-size-sm;
    font-weight: @font-weight-bold;
  }

  .step-copy {
    min-width: 0;
  }

  .step-title {
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-xs;
  }

  .step-desc {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    line-height: @line-height-base;
  }

  .step-meta {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-xs;
    margin-top: @spacing-sm;
  }

  .step-status-row {
    margin-top: @spacing-sm;
  }
</style>
