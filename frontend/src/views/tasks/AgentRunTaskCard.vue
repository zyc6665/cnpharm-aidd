<template>
  <div
    class="agent-run-card"
    :class="{ 'is-active': isActiveAgentRunStatus(run.status), 'is-expanded': expanded }"
  >
    <button
      type="button"
      class="agent-run-card__summary"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <div class="agent-run-card__main">
        <div class="agent-run-card__icon">
          <BranchesOutlined />
        </div>
        <div class="agent-run-card__meta">
          <div class="agent-run-card__eyebrow">
            <span>{{ t('tasks.agentRun') }}</span>
            <span>ID: {{ run.id.slice(0, 8) }}...</span>
          </div>
          <h3>{{ title }}</h3>
          <div class="agent-run-card__details">
            <span>
              <CalendarOutlined />
              {{ formatTime(run.created_at) }}
            </span>
            <span v-if="run.finished_at">
              <CheckCircleOutlined />
              {{ formatTime(run.finished_at) }}
            </span>
            <span>
              <ApartmentOutlined />
              {{ t('tasks.agentRunProgress', { completed: progress.completed, total: progress.total, failed: progress.failed }) }}
            </span>
          </div>
        </div>
      </div>

      <div class="agent-run-card__status">
        <a-tag :color="statusColor">
          {{ formatStatus(run.status) }}
        </a-tag>
        <a-progress
          type="circle"
          :percent="progress.percent"
          :width="58"
          :stroke-color="progress.failed > 0 ? '#ff4d4f' : '#52c41a'"
        />
        <DownOutlined class="agent-run-card__chevron" />
      </div>
    </button>

    <div v-if="expanded" class="agent-run-card__steps">
      <div class="agent-run-card__steps-header">
        <span>{{ t('tasks.agentRunSteps') }}</span>
        <span>{{ run.steps.length }}</span>
      </div>
      <div class="agent-step-list">
        <div
          v-for="step in orderedSteps"
          :key="step.id"
          class="agent-step"
        >
          <span class="agent-step__index">#{{ String(step.sort_order + 1).padStart(2, '0') }}</span>
          <div class="agent-step__body">
            <div class="agent-step__title">
              <strong>{{ formatStepTitle(step.step_key) }}</strong>
              <span>{{ formatToolSlug(step.tool_slug) }}</span>
            </div>
            <p v-if="step.error_message" class="agent-step__error">{{ step.error_message }}</p>
          </div>
          <div class="agent-step__actions">
            <a-tag :color="stepStatusColor(step.status)">
              {{ formatStepStatus(step.status) }}
            </a-tag>
            <a-button
              v-if="step.task_id"
              type="link"
              size="small"
              @click.stop="$emit('view-task', step.task_id)"
            >
              {{ t('tasks.agentViewTask') }}
            </a-button>
            <span v-else class="agent-step__missing-task">
              {{ t('tasks.agentNoLinkedTask') }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref } from 'vue'
  import { useI18n } from 'vue-i18n'
  import dayjs from 'dayjs'
  import {
    ApartmentOutlined,
    BranchesOutlined,
    CalendarOutlined,
    CheckCircleOutlined,
    DownOutlined
  } from '@ant-design/icons-vue'
  import type { AiddAgentRun, AiddAgentRunStatus, AiddAgentStepStatus } from '@/types/models'
  import { getAgentRunProgress, isActiveAgentRunStatus } from './agent-task-grouping'

  const props = defineProps<{
    run: AiddAgentRun
  }>()

  defineEmits<{
    (event: 'view-task', taskId: string): void
  }>()

  const { t } = useI18n()
  const expanded = ref(false)

  const title = computed(() => props.run.summary || props.run.message || t('tasks.agentRun'))
  const progress = computed(() => getAgentRunProgress(props.run))
  const orderedSteps = computed(() => [...props.run.steps].sort((left, right) => left.sort_order - right.sort_order))

  const statusColor = computed(() => {
    const colors: Record<AiddAgentRunStatus, string> = {
      pending: 'default',
      planning: 'processing',
      running: 'processing',
      waiting_task: 'processing',
      success: 'success',
      failure: 'error',
      canceled: 'warning'
    }

    return colors[props.run.status]
  })

  function formatTime(time: string) {
    return dayjs(time).format('YYYY-MM-DD HH:mm:ss')
  }

  function formatStatus(status: AiddAgentRunStatus) {
    return t(`workflow.agent.status.${status}`)
  }

  function formatStepStatus(status: AiddAgentStepStatus) {
    return t(`workflow.agent.stepStatus.${status}`)
  }

  function formatStepTitle(stepKey: string) {
    const labels: Record<string, string> = {
      pocket_prediction: t('workflow.steps.pocketExploration.title'),
      molecule_generation: t('workflow.steps.moleculeGenerationOrVirtualScreening.title'),
      property_prediction: t('workflow.steps.propertyPrediction.title'),
      affinity_prediction: t('workflow.steps.molecularDockingAndAffinityPrediction.title')
    }

    return labels[stepKey] ?? stepKey
  }

  function formatToolSlug(toolSlug: string) {
    return toolSlug.replace(/-/g, ' ').toUpperCase()
  }

  function stepStatusColor(status: AiddAgentStepStatus) {
    const colors: Record<AiddAgentStepStatus, string> = {
      pending: 'default',
      ready: 'blue',
      running: 'blue',
      waiting_task: 'blue',
      success: 'green',
      failure: 'red',
      skipped: 'default',
      canceled: 'orange'
    }

    return colors[status]
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .agent-run-card {
    .card();
    padding: 0;
    overflow: hidden;
    border-left: 3px solid #475569;

    &.is-active {
      border-left-color: @primary-color;
      background: linear-gradient(90deg, @primary-color-light 0%, #fff 12%);
    }

    &.is-expanded {
      .agent-run-card__chevron {
        transform: rotate(180deg);
      }
    }
  }

  .agent-run-card__summary {
    width: 100%;
    border: 0;
    background: transparent;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-xl;
    padding: @spacing-lg;
    text-align: left;
    cursor: pointer;

    &:focus-visible {
      outline: 3px solid rgba(24, 144, 255, 0.28);
      outline-offset: -3px;
    }
  }

  .agent-run-card__main {
    min-width: 0;
    display: flex;
    align-items: center;
    gap: @spacing-md;
    flex: 1;
  }

  .agent-run-card__icon {
    width: 42px;
    height: 42px;
    border-radius: @border-radius-md;
    background: #eef2ff;
    color: #3730a3;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    flex: 0 0 auto;
  }

  .agent-run-card__meta {
    min-width: 0;

    h3 {
      margin: 0 0 @spacing-xs;
      font-size: @font-size-md;
      font-weight: @font-weight-semibold;
      color: @text-color-light-primary;
      word-break: break-word;
    }
  }

  .agent-run-card__eyebrow {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-sm;
    margin-bottom: @spacing-xs;
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-family: monospace;
  }

  .agent-run-card__details {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-lg;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;

    span {
      display: inline-flex;
      align-items: center;
      gap: @spacing-xs;
    }
  }

  .agent-run-card__status {
    display: flex;
    align-items: center;
    gap: @spacing-md;
    flex: 0 0 auto;
  }

  .agent-run-card__chevron {
    color: @text-color-light-tertiary;
    transition: transform @transition-duration;
  }

  .agent-run-card__steps {
    padding: 0 @spacing-lg @spacing-lg;
  }

  .agent-run-card__steps-header {
    display: flex;
    justify-content: space-between;
    padding: @spacing-md 0 @spacing-sm;
    border-top: 1px solid @border-color-light;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    font-weight: @font-weight-medium;
  }

  .agent-step-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .agent-step {
    display: grid;
    grid-template-columns: 52px minmax(0, 1fr) auto;
    gap: @spacing-md;
    align-items: center;
    padding: @spacing-sm @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    background: #fff;
  }

  .agent-step__index {
    color: @text-color-light-tertiary;
    font-family: monospace;
    font-size: @font-size-sm;
  }

  .agent-step__body {
    min-width: 0;
  }

  .agent-step__title {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: @spacing-sm;

    strong {
      color: @text-color-light-primary;
    }

    span {
      color: @text-color-light-tertiary;
      font-size: @font-size-sm;
    }
  }

  .agent-step__error {
    margin: @spacing-xs 0 0;
    color: @error-color;
    font-size: @font-size-sm;
  }

  .agent-step__actions {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
  }

  .agent-step__missing-task {
    color: @text-color-light-tertiary;
    font-size: @font-size-sm;
  }

  @media (max-width: @screen-md) {
    .agent-run-card__summary,
    .agent-run-card__status,
    .agent-step,
    .agent-step__actions {
      align-items: flex-start;
    }

    .agent-run-card__summary,
    .agent-run-card__status {
      flex-direction: column;
    }

    .agent-step {
      grid-template-columns: 1fr;
    }
  }
</style>
