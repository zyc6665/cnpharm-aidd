<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { getTaskDetail } from '@/api/tasks'
import { resolveTaskResultPath } from '@/domain/design/runs'
import { getTaskStatusColor, getTaskStatusTextKey, normalizeTaskStatus } from '@/domain/tasks'
import type { Task } from '@/types/models'

const props = withDefaults(
  defineProps<{
    taskId: string
    active: 'detail' | 'result'
    /** 任务详情页已经有任务数据时直接传入，避免重复请求。 */
    task?: Task | null
    /** 结果页知道自己所在的路径时直接传入；不传则按 tool_slug 推导。 */
    resultPath?: string | null
    /** 是否展示「运行结果」入口；不传则按是否有专属结果页自动判断。 */
    showResult?: boolean
    /** 结果页展示任务名/状态/ID；详情页已有状态卡，可只保留视图切换。 */
    showMeta?: boolean
    /** 详情页由父页面负责取数时关掉内部请求。 */
    fetchTask?: boolean
  }>(),
  {
    task: null,
    resultPath: undefined,
    showResult: undefined,
    showMeta: true,
    fetchTask: true
  }
)

const { t } = useI18n()
const router = useRouter()
const loadedTask = ref<Task | null>(null)

const taskRecord = computed(() => props.task ?? loadedTask.value)
const taskSlug = computed(() => taskRecord.value?.tool_slug ?? taskRecord.value?.tool?.slug)
const resolvedResultPath = computed(() =>
  props.resultPath !== undefined
    ? props.resultPath
    : resolveTaskResultPath(taskSlug.value, props.taskId)
)
const canShowResult = computed(() => props.showResult ?? Boolean(resolvedResultPath.value))
const status = computed(() => normalizeTaskStatus(taskRecord.value?.status))
const taskTitle = computed(
  () => taskRecord.value?.name || taskRecord.value?.tool?.name || t('tasks.taskDetail')
)

watch(
  () => [props.taskId, props.fetchTask] as const,
  async ([id, fetchTask]) => {
    if (!id || !fetchTask || props.task) return
    try {
      const response = await getTaskDetail(id, { silent: true })
      loadedTask.value = response.data
    } catch {
      // 上下文条只是辅助导航；任务接口失败时仍保留任务 ID 与返回入口。
    }
  },
  { immediate: true }
)

function goDetail(): void {
  if (props.active !== 'detail') {
    void router.push(`/tasks/${props.taskId}`)
  }
}

function goResult(): void {
  const target = resolvedResultPath.value
  if (target && props.active !== 'result') {
    void router.push(target)
  }
}
</script>

<template>
  <div class="task-context-bar" :class="{ 'task-context-bar--compact': !showMeta }" data-testid="task-context-bar">
    <div v-if="showMeta" class="task-context-bar__meta">
      <router-link
        v-if="taskRecord?.project_id"
        class="task-context-bar__back"
        :to="`/projects/${taskRecord.project_id}`"
        data-testid="task-context-project"
      >
        <span aria-hidden="true">←</span>
        {{ t('tasks.taskWorkspace.backToProject') }}
      </router-link>
      <router-link class="task-context-bar__back" to="/tasks" data-testid="task-context-back">
        <span aria-hidden="true">←</span>
        {{ t('tasks.taskWorkspace.backToCenter') }}
      </router-link>
      <span class="task-context-bar__title">{{ taskTitle }}</span>
      <a-tag v-if="taskRecord" :color="getTaskStatusColor(status)">
        {{ t(getTaskStatusTextKey(status)) }}
      </a-tag>
      <span class="task-context-bar__id">ID: {{ taskId }}</span>
    </div>

    <div class="task-context-bar__views" role="group" :aria-label="t('tasks.taskWorkspace.views')">
      <a-button
        size="small"
        :type="active === 'detail' ? 'primary' : 'default'"
        data-testid="task-context-detail"
        @click="goDetail"
      >
        {{ t('tasks.taskWorkspace.detail') }}
      </a-button>
      <a-button
        v-if="canShowResult"
        size="small"
        :type="active === 'result' ? 'primary' : 'default'"
        data-testid="task-context-result"
        @click="goResult"
      >
        {{ t('tasks.taskWorkspace.result') }}
      </a-button>
    </div>
  </div>
</template>

<style scoped lang="less">
.task-context-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: @spacing-md;
  flex-wrap: wrap;
  margin-bottom: @spacing-lg;
  padding: @spacing-sm @spacing-md;
  background: @bg-surface;
  border: 1px solid @border-color;
  border-radius: @border-radius-base;

  &--compact {
    justify-content: flex-end;
  }

  &__meta {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    min-width: 0;
    flex-wrap: wrap;
  }

  &__back {
    color: @text-secondary;
    white-space: nowrap;

    &:hover {
      color: @accent-color;
    }
  }

  &__title {
    font-weight: @font-weight-medium;
    max-width: 420px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  &__id {
    color: @text-tertiary;
    font-size: @font-size-sm;
    font-family: @font-family-mono;
  }

  &__views {
    display: flex;
    align-items: center;
    gap: @spacing-xs;
    margin-left: auto;
  }
}

@media (max-width: @screen-md) {
  .task-context-bar {
    align-items: flex-start;
    flex-direction: column;

    &__views {
      margin-left: 0;
    }
  }
}
</style>
