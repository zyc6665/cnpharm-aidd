<template>
  <div class="workflow-page">
    <div class="container">
      <div class="page-header">
        <h1 class="page-title">{{ t('workflow.title') }}</h1>
        <p class="page-subtitle">{{ t('workflow.subtitle') }}</p>
      </div>

      <div class="workflow-layout">
        <WorkflowStepSidebar
          :steps="workflowSteps"
          :active-step-key="activeStep.key"
          :step-states="workflowStore.stepStateByKey"
          :tool-view-models="stepToolViewModels"
          @select="handleStepSelect"
        />
        <WorkflowRunPanel
          :step="activeStep"
          :tool-view-model="activeStepToolViewModel"
          :selected-tool-slug="activeSelectedToolSlug"
          @select-tool="handleToolSelect"
        />
        <WorkflowArtifactPanel :step="activeStep" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import WorkflowArtifactPanel from '@/components/workflow/WorkflowArtifactPanel.vue'
  import WorkflowRunPanel from '@/components/workflow/WorkflowRunPanel.vue'
  import WorkflowStepSidebar from '@/components/workflow/WorkflowStepSidebar.vue'
  import { useToolsStore, useWorkflowStore } from '@/stores'
  import {
    AIDD_WORKFLOW_STEP_MAP,
    AIDD_WORKFLOW_STEPS,
    type WorkflowStepCatalogItem
  } from '@/workflow/aidd-catalog'
  import type { WorkflowStepKey } from '@/workflow/artifact-types'
  import { buildWorkflowStepToolViewModel } from '@/workflow/step-tools'
  import type { WorkflowBoundToolSlug } from '@/workflow/tool-bindings'

  const { t } = useI18n()
  const toolsStore = useToolsStore()
  const workflowStore = useWorkflowStore()
  const workflowSteps = AIDD_WORKFLOW_STEPS

  function getInitialWorkflowStep(): WorkflowStepCatalogItem {
    const initialStep = workflowSteps[0]

    if (!initialStep) {
      throw new Error('AIDD workflow steps must define at least one step')
    }

    return initialStep
  }

  const activeStep = computed(() => {
    return AIDD_WORKFLOW_STEP_MAP[workflowStore.activeStepKey] ?? getInitialWorkflowStep()
  })

  const stepToolViewModels = computed(() => {
    return Object.fromEntries(
      workflowSteps.map((step) => [
        step.key,
        buildWorkflowStepToolViewModel({
          stepKey: step.key,
          tools: toolsStore.workflowToolOptions
        })
      ])
    ) as Record<WorkflowStepKey, ReturnType<typeof buildWorkflowStepToolViewModel>>
  })

  const activeStepToolViewModel = computed(() => stepToolViewModels.value[activeStep.value.key])
  const activeSelectedToolSlug = computed(() => {
    return (workflowStore.selectedToolByStep[activeStep.value.key] ?? null) as WorkflowBoundToolSlug | null
  })

  function handleStepSelect(stepKey: WorkflowStepKey) {
    workflowStore.setActiveStep(stepKey)
  }

  function handleToolSelect(toolSlug: WorkflowBoundToolSlug) {
    workflowStore.selectTool(activeStep.value.key, toolSlug)
  }

  watch(
    activeStepToolViewModel,
    (viewModel) => {
      const currentSelectedToolSlug = activeSelectedToolSlug.value

      if (
        viewModel.defaultSelectedToolSlug &&
        (
          currentSelectedToolSlug === null ||
          !viewModel.availableToolSlugs.includes(currentSelectedToolSlug)
        )
      ) {
        workflowStore.selectTool(viewModel.stepKey, viewModel.defaultSelectedToolSlug)
      }
    },
    { immediate: true }
  )

  onMounted(async () => {
    if (toolsStore.workflowToolOptions.length === 0) {
      await toolsStore.fetchWorkflowTools()
    }
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-page {
    padding: @spacing-xl 0;
    min-height: calc(100vh - @header-height - @footer-height);
    background: @bg-light;
  }

  .page-header {
    text-align: center;
    margin-bottom: @spacing-xl;
  }

  .page-title {
    font-size: @font-size-xxxl;
    font-weight: @font-weight-bold;
    margin-bottom: @spacing-sm;
  }

  .page-subtitle {
    max-width: 760px;
    margin: 0 auto;
    color: @text-color-light-secondary;
    font-size: @font-size-lg;
  }

  .workflow-layout {
    display: grid;
    grid-template-columns: 280px minmax(0, 1fr) 320px;
    gap: @spacing-lg;

    @media (max-width: @screen-xl) {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    @media (max-width: @screen-md) {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
