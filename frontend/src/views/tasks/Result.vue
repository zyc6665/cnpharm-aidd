<template>
  <div class="task-result-page" data-testid="task-result-page">
    <div class="container">
      <SkeletonList v-if="loading && !task" :count="4" />
      <AppInlineError
        v-else-if="loadError"
        :title="t('tasks.resultPage.loadFailed')"
        :description="t('tasks.resultPage.loadFailedHint')"
      >
        <a-button size="small" @click="loadTask">{{ t('common.retry') }}</a-button>
      </AppInlineError>

      <template v-else-if="task">
        <StructureTaskResult
          v-if="isSuccess && kind === 'structure'"
          :task="task"
          :task-id="taskId"
        />
        <PocketTaskResult
          v-else-if="isSuccess && kind === 'pocket'"
          :task="task"
          :task-id="taskId"
        />
        <GenerationResults v-else-if="isSuccess && kind === 'generation'" />
        <PropertyPredictResult v-else-if="isSuccess && kind === 'predict'" />
        <ScreenResult v-else-if="isSuccess && kind === 'screening'" />
        <MdResult v-else-if="isSuccess && kind === 'md'" />
        <FreeEnergyResult v-else-if="isSuccess && kind === 'freeEnergy'" />
        <GenericTaskResult v-else-if="isSuccess" :task="task" :task-id="taskId" />

        <template v-else>
          <AppPageHeader :title="t('tasks.resultPage.title')" :subtitle="t('tasks.resultPage.subtitle')" />
          <TaskContextBar
            :task-id="taskId"
            :task="task"
            active="result"
            :fetch-task="false"
          />
          <a-card v-if="isActive" :bordered="false">
            <a-result status="info" :title="t('tasks.resultPage.running')" :sub-title="runningHint">
              <template #icon><LoadingOutlined spin /></template>
              <a-progress
                :percent="Math.round(task.progress ?? 0)"
                :status="getTaskProgressStatus(task.status)"
                :stroke-color="getTaskProgressColor(task.status)"
              />
              <p v-if="task.progress_message" class="task-result-page__progress-message">
                {{ task.progress_message }}
              </p>
            </a-result>
          </a-card>
          <a-result
            v-else
            status="error"
            :title="t('tasks.resultPage.failed')"
            :sub-title="task.error_message || t('tasks.resultPage.failedHint')"
          >
            <template #extra>
              <a-button @click="loadTask">{{ t('common.retry') }}</a-button>
              <a-button type="primary" @click="goDetail">{{ t('tasks.viewDetail') }}</a-button>
            </template>
          </a-result>
        </template>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { useRoute, useRouter } from 'vue-router'
  import { LoadingOutlined } from '@ant-design/icons-vue'
  import AppInlineError from '@/components/common/AppInlineError.vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import SkeletonList from '@/components/common/SkeletonList.vue'
  import TaskContextBar from '@/components/tasks/TaskContextBar.vue'
  import { getTaskDetail } from '@/api/tasks'
  import { getTaskProgressColor, getTaskProgressStatus } from '@/domain/tasks'
  import { resolveTaskResultKind } from '@/domain/tasks/result'
  import type { Task } from '@/types/models'
  import StructureTaskResult from './StructureTaskResult.vue'
  import PocketTaskResult from './PocketTaskResult.vue'
  import GenericTaskResult from './GenericTaskResult.vue'
  import GenerationResults from '@/views/design/GenerationResults.vue'
  import PropertyPredictResult from '@/views/predict/PropertyPredictResult.vue'
  import ScreenResult from '@/views/screening/ScreenResult.vue'
  import MdResult from '@/views/md/MdResult.vue'
  import FreeEnergyResult from '@/views/md/FreeEnergyResult.vue'

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()

  const taskId = computed(() => String(route.params.id ?? ''))
  const task = ref<Task | null>(null)
  const loading = ref(false)
  const loadError = ref(false)
  const kind = computed(() =>
    resolveTaskResultKind(task.value?.tool_slug ?? task.value?.tool?.slug)
  )
  const isActive = computed(
    () => task.value?.status === 'pending' || task.value?.status === 'queued' || task.value?.status === 'running'
  )
  const isSuccess = computed(() => task.value?.status === 'success')
  const runningHint = computed(() => t('tasks.resultPage.runningHint'))

  let pollTimer: ReturnType<typeof setInterval> | null = null

  function stopPolling(): void {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function syncPolling(): void {
    if (isActive.value && !pollTimer) {
      pollTimer = setInterval(() => void loadTask(true), 3000)
    } else if (!isActive.value) {
      stopPolling()
    }
  }

  async function loadTask(silent = false): Promise<void> {
    if (!taskId.value) return
    if (!silent) loading.value = true
    loadError.value = false
    try {
      const response = await getTaskDetail(taskId.value, { silent: true })
      task.value = response.data
      syncPolling()
    } catch {
      if (!task.value) loadError.value = true
    } finally {
      loading.value = false
    }
  }

  function goDetail(): void {
    void router.push(`/tasks/${taskId.value}`)
  }

  watch(isActive, syncPolling)
  onMounted(() => void loadTask())
  onUnmounted(stopPolling)
</script>

<style scoped lang="less">
  .task-result-page {
    &__progress-message {
      margin-top: @spacing-md;
      color: @text-secondary;
    }
  }
</style>
