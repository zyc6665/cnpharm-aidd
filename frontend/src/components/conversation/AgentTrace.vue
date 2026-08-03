<template>
  <section class="trace">
    <button class="trace-toggle" type="button" @click="expanded = !expanded">
      <RightOutlined :class="{ expanded }" />
      <span>智能体过程</span>
      <span class="count">{{ events.length }}</span>
    </button>
    <ol v-if="expanded">
      <li v-for="view in traceEvents" :key="view.sequence" :class="{ failed: view.failed }">
        <span class="sequence">{{ view.sequence }}</span>
        <span class="event-body">
          <span class="event-main">
            <span class="event-title">{{ view.label }}</span>
            <span v-if="view.statusLabel" class="event-status" :class="view.statusClass">
              {{ view.statusLabel }}
            </span>
            <span v-if="view.taskId" class="task-id">{{ view.taskId }}</span>
          </span>
          <span v-if="view.progress !== null" class="progress-line">
            <span
              class="progress-bar"
              data-testid="agent-event-progress"
              role="progressbar"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-valuenow="view.progress"
            >
              <span :style="{ width: `${view.progress}%` }" />
            </span>
            <span class="progress-value">{{ view.progress }}%</span>
          </span>
        </span>
      </li>
    </ol>
    <div v-if="hasFailure" class="failure-state">
      <WarningOutlined />失败后可重试
      <a-button size="small" data-testid="retry-run" @click="$emit('retry')">重试</a-button>
    </div>
  </section>
</template>

<script setup lang="ts">
  import { computed, ref } from 'vue'
  import { RightOutlined, WarningOutlined } from '@ant-design/icons-vue'
  import type { AgentEvent } from '@/types/conversations'

  const props = defineProps<{ events: AgentEvent[]; showRetry?: boolean }>()
  defineEmits<{ retry: [] }>()
  const expanded = ref(false)
  const traceEvents = computed(() =>
    props.events.map(event => {
      const status = statusKind(event)
      const statusLabel = status ? statusLabels[status] || status : null
      return {
        sequence: event.sequence,
        label: eventLabel(event),
        progress: eventProgress(event),
        statusLabel,
        statusClass: statusClass(status),
        taskId: eventTaskId(event),
        failed: isFailure(event, status)
      }
    })
  )
  const hasFailure = computed(
    () => props.showRetry || traceEvents.value.some(event => event.failed)
  )

  const eventLabels: Record<string, string> = {
    plan_created: '计划已生成',
    approval_required: '等待审批',
    execution_submitted: '任务已提交',
    execution_queued: '任务已排队',
    execution_started: '任务开始执行',
    execution_progress: '任务运行中',
    execution_completed: '任务执行成功',
    execution_failed: '任务执行失败'
  }

  const statusLabels: Record<string, string> = {
    queued: '排队中',
    pending: '排队中',
    running: '运行中',
    in_progress: '运行中',
    success: '成功',
    completed: '成功',
    failure: '失败',
    failed: '失败',
    error: '失败'
  }

  const payloadString = (event: AgentEvent, key: string) => {
    const value = event.payload[key]
    return typeof value === 'string' && value.trim() ? value : null
  }

  const statusKind = (event: AgentEvent) => {
    const status = payloadString(event, 'status')
    if (status) return status.toLowerCase()
    if (event.event_type === 'execution_queued') return 'queued'
    if (event.event_type === 'execution_completed') return 'success'
    if (event.event_type.includes('fail')) return 'failure'
    if (event.event_type.startsWith('execution_')) return 'running'
    return null
  }

  const eventLabel = (event: AgentEvent) =>
    payloadString(event, 'message') ||
    payloadString(event, 'summary') ||
    eventLabels[event.event_type] ||
    event.event_type.replace(/_/g, ' ')

  const eventProgress = (event: AgentEvent) => {
    const rawProgress = event.payload.progress
    const progress =
      typeof rawProgress === 'number'
        ? rawProgress
        : typeof rawProgress === 'string'
          ? Number(rawProgress)
          : NaN
    if (!Number.isFinite(progress)) return null
    return Math.max(0, Math.min(100, Math.round(progress)))
  }

  const statusClass = (status: string | null) => {
    if (!status) return ''
    if (['success', 'completed'].includes(status)) return 'status-success'
    if (['failure', 'failed', 'error'].includes(status)) return 'status-failure'
    if (['queued', 'pending'].includes(status)) return 'status-queued'
    return 'status-running'
  }

  const eventTaskId = (event: AgentEvent) => {
    const taskId = payloadString(event, 'task_id')
    if (!taskId) return null
    return taskId.length > 8 ? taskId.slice(0, 8) : taskId
  }

  const isFailure = (event: AgentEvent, knownStatus = statusKind(event)) => {
    const status = knownStatus
    return (
      event.event_type.includes('fail') || ['failure', 'failed', 'error'].includes(status || '')
    )
  }
</script>

<style scoped lang="less">
  .trace {
    width: min(780px, 100%);
    margin: 0 auto;
    padding: 0 28px;
  }
  .trace-toggle {
    display: flex;
    align-items: center;
    gap: 7px;
    height: 34px;
    padding: 0;
    border: 0;
    background: transparent;
    color: @text-secondary;
    cursor: pointer;
  }
  .trace-toggle svg {
    transition: transform 0.15s;
  }
  .trace-toggle svg.expanded {
    transform: rotate(90deg);
  }
  .count {
    color: @text-tertiary;
  }
  ol {
    max-height: 180px;
    margin: 0 0 10px;
    padding: 4px 0;
    list-style: none;
    overflow: auto;
  }
  li {
    display: grid;
    grid-template-columns: 28px minmax(0, 1fr);
    gap: 6px;
    padding: 6px 8px;
    font-size: 12px;
    color: @text-secondary;
  }
  li.failed {
    color: @error-color;
  }
  .sequence {
    color: @text-tertiary;
  }
  .event-body {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 5px;
  }
  .event-main {
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .event-title {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .event-status {
    flex: 0 0 auto;
    padding: 1px 6px;
    border-radius: 999px;
    font-size: 11px;
    line-height: 17px;
    background: @bg-hover;
    color: @text-secondary;
  }
  .event-status.status-running {
    background: @primary-color-light;
    color: @primary-color;
  }
  .event-status.status-success {
    background: @success-color-light;
    color: @success-color;
  }
  .event-status.status-failure {
    background: @error-color-light;
    color: @error-color;
  }
  .event-status.status-queued {
    background: @warning-color-light;
    color: @warning-color;
  }
  .task-id {
    flex: 0 0 auto;
    padding: 0 5px;
    border-radius: 4px;
    background: @bg-hover;
    color: @text-tertiary;
    font-family: @font-family-mono;
  }
  .progress-line {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .progress-bar {
    position: relative;
    height: 5px;
    flex: 1 1 auto;
    min-width: 48px;
    overflow: hidden;
    border-radius: 999px;
    background: @border-color;
  }
  .progress-bar span {
    position: absolute;
    inset: 0 auto 0 0;
    border-radius: inherit;
    background: @primary-color;
  }
  li.failed .progress-bar span {
    background: @error-color;
  }
  .progress-value {
    width: 34px;
    flex: 0 0 auto;
    text-align: right;
    color: @text-tertiary;
  }
  .failure-state {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 9px 10px;
    border-left: 3px solid @error-color;
    background: @error-color-light;
    color: @error-color;
  }
  .failure-state :deep(.ant-btn) {
    margin-left: auto;
  }
</style>
