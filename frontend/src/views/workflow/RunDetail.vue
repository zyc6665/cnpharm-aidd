<template>
  <main class="workflow-run-detail-page">
    <AppPageHeader
      :title="runTitle"
      :subtitle="runSubtitle"
      align="center"
    >
      <template #actions>
        <a-space wrap>
          <a-button @click="goBackToWorkflow">
            {{ t('common.back') }}
          </a-button>
          <a-button
            type="primary"
            :loading="workflowStore.isLoadingWorkflowRun"
            @click="loadRun"
          >
            {{ t('workflow.canvasPresets.refreshRuns') }}
          </a-button>
        </a-space>
      </template>
    </AppPageHeader>

    <a-skeleton v-if="workflowStore.isLoadingWorkflowRun && !workflowStore.activeWorkflowRun" active />
    <!-- 运行详情拿不到有两种原因：链接过期（运行被清理）或还没有任何运行。
         前者要引导回列表重选，后者要引导去运行一次，不能用同一句「无数据」打发。 -->
    <AppEmptyState
      v-else-if="!workflowStore.activeWorkflowRun"
      :title="t('workflow.canvasPresets.emptyRunDetail')"
      :description="t('workflow.canvasPresets.emptyRunDetailHint')"
    >
      <a-button @click="loadRun">{{ t('workflow.canvasPresets.refreshRuns') }}</a-button>
    </AppEmptyState>
    <WorkflowRunStatusPanel
      v-else
      :run="workflowStore.activeWorkflowRun"
      :syncing="workflowStore.isSyncingWorkflowRun || workflowStore.isLoadingWorkflowRun"
      :canceling="workflowStore.isCancelingWorkflowRun"
      :retrying-node-id="workflowStore.retryingWorkflowRunNodeId"
      @sync="handleSync"
      @cancel="handleCancel"
      @retry-node="handleRetryNode"
    />
  </main>
  <ResultDisclaimer />
</template>

<script setup lang="ts">
  import { computed, onUnmounted, watch } from 'vue'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import { useRoute, useRouter } from 'vue-router'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AppEmptyState from '@/components/common/AppEmptyState.vue'
  import WorkflowRunStatusPanel from '@/components/workflow/WorkflowRunStatusPanel.vue'
  import { useWorkflowStore } from '@/stores'
  import { isWorkflowRunTerminal } from '@/workflow/workflow-runs'
  import ResultDisclaimer from '@/components/common/ResultDisclaimer.vue'

  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()
  const workflowStore = useWorkflowStore()
  let autoSyncTimer: number | null = null

  const runId = computed(() => {
    const value = route.params.runId
    return Array.isArray(value) ? value[0] : value
  })
  const runTitle = computed(() => workflowStore.activeWorkflowRun?.name || t('workflow.runDetail.title'))
  const runSubtitle = computed(() => {
    const run = workflowStore.activeWorkflowRun
    if (!run) {
      return t('workflow.runDetail.subtitle')
    }
    return `Run ID: ${run.id}`
  })

  async function loadRun() {
    if (!runId.value) {
      return
    }
    try {
      await workflowStore.loadWorkflowRun(runId.value)
      if (workflowStore.activeWorkflowRun?.id === runId.value) {
        scheduleAutoSync()
      }
    } catch {
      // 请求层已经展示具体错误。
    }
  }

  async function handleSync() {
    try {
      await workflowStore.syncActiveWorkflowRun(runId.value)
      scheduleAutoSync()
    } catch {
      // 请求层已经展示具体错误。
    }
  }

  async function handleCancel() {
    try {
      await workflowStore.cancelActiveWorkflowRun(runId.value)
      message.success(t('workflow.runDetail.canceled'))
      scheduleAutoSync()
    } catch {
      // 请求层已经展示具体错误。
    }
  }

  async function handleRetryNode(nodeId: string) {
    if (!runId.value) {
      return
    }
    try {
      await workflowStore.retryWorkflowRunNode(runId.value, nodeId)
      message.success(t('workflow.runDetail.nodeRetried'))
      scheduleAutoSync()
    } catch {
      // 请求层已经展示具体错误。
    }
  }

  function goBackToWorkflow() {
    const projectId = workflowStore.activeWorkflowRun?.project_id
    if (projectId) {
      router.push({ name: 'ProjectWorkflow', params: { projectId } })
      return
    }
    router.push({ name: 'Workflow' })
  }

  function stopAutoSync() {
    if (autoSyncTimer !== null) {
      window.clearInterval(autoSyncTimer)
      autoSyncTimer = null
    }
  }

  function scheduleAutoSync() {
    stopAutoSync()
    const run = workflowStore.activeWorkflowRun
    if (!run || isWorkflowRunTerminal(run.status)) {
      return
    }

    autoSyncTimer = window.setInterval(async () => {
      if (workflowStore.isSyncingWorkflowRun || workflowStore.isLoadingWorkflowRun) {
        return
      }
      const currentRun = workflowStore.activeWorkflowRun
      if (!currentRun || isWorkflowRunTerminal(currentRun.status)) {
        stopAutoSync()
        return
      }

      try {
        await workflowStore.syncActiveWorkflowRun(runId.value)
        if (
          workflowStore.activeWorkflowRun &&
          isWorkflowRunTerminal(workflowStore.activeWorkflowRun.status)
        ) {
          stopAutoSync()
        }
      } catch {
        // 请求层已经展示错误，停止轮询等待用户手动刷新。
        stopAutoSync()
      }
    }, 5000)
  }

  watch(
    runId,
    async id => {
      stopAutoSync()
      if (!id) {
        return
      }
      workflowStore.clearActiveWorkflowRun()
      void loadRun()
    },
    { immediate: true }
  )

  onUnmounted(() => {
    stopAutoSync()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-run-detail-page {
    min-height: calc(100vh - @header-height - @footer-height);
    padding: @spacing-xl 0 @spacing-xxl;
    background: @bg-light;
  }
</style>
