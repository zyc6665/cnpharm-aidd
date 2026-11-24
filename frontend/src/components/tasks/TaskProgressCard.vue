<template>
  <aside class="task-progress-card" data-testid="task-progress-card" :data-status="status">
    <header class="task-progress-card__header">
      <div class="task-progress-card__title">
        <span>{{ t('design.progressCard.title') }}</span>
        <a-tag :color="getTaskStatusColor(status)">{{ t(getTaskStatusTextKey(status)) }}</a-tag>
      </div>
      <button
        type="button"
        class="task-progress-card__close"
        :aria-label="t('design.progressCard.close')"
        data-testid="task-progress-close"
        @click="emit('close')"
      >
        ×
      </button>
    </header>

    <p v-if="taskName" class="task-progress-card__name">{{ taskName }}</p>

    <div class="task-progress-card__progress">
      <div class="task-progress-card__progress-head">
        <span>{{ t('design.progressCard.progress') }}</span>
        <span>{{ progress }}%</span>
      </div>
      <a-progress
        :percent="progress"
        :status="status === 'failure' || status === 'timeout' ? 'exception' : 'active'"
        :show-info="false"
        size="small"
      />
    </div>

    <div v-if="isWaiting" class="task-progress-card__queue" data-testid="task-progress-queue">
      <p v-if="queueInfo.queuePosition !== null">
        {{ t('design.progressCard.queuePosition', { position: queueInfo.queuePosition }) }}
      </p>
      <p v-if="queueInfo.estimatedWaitSeconds !== null">
        {{ t('design.progressCard.estimatedWait', { time: formatWaitSeconds(queueInfo.estimatedWaitSeconds) }) }}
      </p>
      <p v-if="queueInfo.queuePosition === null && queueInfo.estimatedWaitSeconds === null">
        {{ t('design.progressCard.queuing') }}
      </p>
    </div>

    <p v-if="progressMessage" class="task-progress-card__message">{{ progressMessage }}</p>
    <p v-if="errorMessage" class="task-progress-card__error">{{ errorMessage }}</p>

    <footer class="task-progress-card__actions">
      <a-button
        v-if="canCancel"
        size="small"
        danger
        data-testid="task-progress-cancel"
        @click="handleCancel"
      >
        {{ t('design.progressCard.cancel') }}
      </a-button>
      <router-link :to="detailPath" class="task-progress-card__link" data-testid="task-progress-detail">
        {{ t('design.progressCard.viewDetail') }}
      </router-link>
      <router-link
        v-if="status === 'success'"
        :to="resultsPath"
        class="task-progress-card__link task-progress-card__link--primary"
        data-testid="task-progress-results"
      >
        {{ t('design.progressCard.viewResults') }}
      </router-link>
    </footer>
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import { cancelTask, getTaskDetail } from '@/api/tasks'
import {
  openTaskEventStream,
  type TaskEventPayload,
  type TaskEventStreamHandle,
} from '@/api/task-events'
import {
  formatWaitSeconds,
  getTaskStatusColor,
  getTaskStatusTextKey,
  normalizeTaskStatus,
  readTaskQueueInfo,
} from '@/domain/tasks'
import { resolveDesignRunPath } from '@/domain/design/runs'
import type { Task, TaskStatus } from '@/types/models'

const props = defineProps<{
  taskId: string
  taskName?: string
}>()

const emit = defineEmits<{ (event: 'close'): void }>()
const { t } = useI18n()

const detail = ref<Task | null>(null)
const status = ref<TaskStatus>('pending')
const progress = ref(0)
const progressMessage = ref('')
const errorMessage = ref('')

let stream: TaskEventStreamHandle | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

const isTerminal = computed(
  () => status.value === 'success' || status.value === 'failure' || status.value === 'timeout' || status.value === 'canceled' || status.value === 'rejected'
)
const isWaiting = computed(() => status.value === 'pending' || status.value === 'queued')
const canCancel = computed(() => isWaiting.value || status.value === 'running')
const queueInfo = computed(() => readTaskQueueInfo(detail.value))
const detailPath = computed(() => `/tasks/${encodeURIComponent(props.taskId)}`)
const resultsPath = computed(() =>
  resolveDesignRunPath(detail.value?.tool_slug ?? detail.value?.tool?.slug, props.taskId)
)

function applyTask(task: Task): void {
  detail.value = task
  status.value = normalizeTaskStatus(task.status)
  progress.value = Math.max(0, Math.min(100, Math.round(task.progress ?? 0)))
  progressMessage.value = task.progress_message ?? ''
  errorMessage.value = task.error_message ?? ''
  if (isTerminal.value) {
    stopTracking()
  }
}

function applyEvent(payload: TaskEventPayload): void {
  if (payload.status) status.value = normalizeTaskStatus(payload.status)
  progress.value = Math.max(0, Math.min(100, Math.round(payload.progress ?? 0)))
  progressMessage.value = payload.progressMessage ?? ''
  errorMessage.value = payload.errorMessage ?? ''
  if (payload.terminal || isTerminal.value) {
    stopTracking()
    void refresh()
  }
}

async function refresh(): Promise<void> {
  try {
    const response = await getTaskDetail(props.taskId)
    applyTask(response.data)
  } catch {
    // 卡片是辅助视图：详情拉取失败时保留 SSE/轮询接下来的状态更新。
  }
}

function startStream(): void {
  if (stream || pollTimer) return
  stream = openTaskEventStream(props.taskId, {
    onSnapshot: applyEvent,
    onStatus: applyEvent,
    onProgress: applyEvent,
    onDone: applyEvent,
    onError: () => startPolling(),
  })
  if (!stream.available) {
    startPolling()
  }
}

function startPolling(): void {
  if (pollTimer || isTerminal.value) return
  pollTimer = setInterval(() => {
    void refresh().then(() => {
      if (isTerminal.value) stopTracking()
    })
  }, 5000)
}

function stopTracking(): void {
  stream?.close()
  stream = null
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function handleCancel(): void {
  Modal.confirm({
    title: t('design.progressCard.cancelConfirm'),
    okText: t('common.confirm'),
    cancelText: t('common.cancel'),
    onOk: async () => {
      try {
        await cancelTask(props.taskId)
        message.success(t('design.progressCard.cancelSuccess'))
        status.value = 'canceled'
        stopTracking()
        await refresh()
      } catch {
        // 请求层已经提示具体错误，卡片只保留当前状态。
      }
    },
  })
}

async function initTracking(): Promise<void> {
  stopTracking()
  detail.value = null
  status.value = 'pending'
  progress.value = 0
  progressMessage.value = ''
  errorMessage.value = ''
  await refresh()
  if (!isTerminal.value) startStream()
}

watch(
  () => props.taskId,
  () => {
    void initTracking()
  }
)

onMounted(() => {
  void initTracking()
})

onUnmounted(stopTracking)
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.task-progress-card {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 900;
  display: flex;
  flex-direction: column;
  gap: @spacing-sm;
  width: min(360px, calc(100vw - 32px));
  padding: @spacing-lg;
  border: 1px solid @border-color;
  border-radius: @border-radius-lg;
  background: @bg-elevated;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
}

.task-progress-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: @spacing-sm;
}

.task-progress-card__title {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  font-weight: @font-weight-semibold;
}

.task-progress-card__close {
  border: none;
  background: transparent;
  color: @text-tertiary;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
}

.task-progress-card__name {
  margin: 0;
  color: @text-secondary;
  font-size: @font-size-sm;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-progress-card__progress-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
  color: @text-secondary;
  font-size: @font-size-sm;
}

.task-progress-card__queue {
  padding: @spacing-sm;
  border-radius: @border-radius-sm;
  background: @warning-color-light;

  p {
    margin: 0;
    color: @text-secondary;
    font-size: @font-size-sm;
    line-height: 1.6;
  }
}

.task-progress-card__message,
.task-progress-card__error {
  margin: 0;
  font-size: @font-size-sm;
  line-height: 1.5;
}

.task-progress-card__message {
  color: @text-secondary;
}

.task-progress-card__error {
  color: @error-color;
}

.task-progress-card__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: @spacing-sm;
}

.task-progress-card__link {
  font-size: @font-size-sm;
}

.task-progress-card__link--primary {
  font-weight: @font-weight-medium;
}
</style>
