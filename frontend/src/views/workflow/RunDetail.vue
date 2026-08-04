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
    <a-empty
      v-else-if="!workflowStore.activeWorkflowRun"
      :description="t('workflow.canvasPresets.emptyRunDetail')"
    />
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
</template>

<script setup lang="ts">
  import { computed, onMounted } from 'vue'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import { useRoute, useRouter } from 'vue-router'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import WorkflowRunStatusPanel from '@/components/workflow/WorkflowRunStatusPanel.vue'
  import { useWorkflowStore } from '@/stores'

  const { t } = useI18n()
  const route = useRoute()
  const router = useRouter()
  const workflowStore = useWorkflowStore()

  const runId = computed(() => {
    const value = route.params.runId
    return Array.isArray(value) ? value[0] : value
  })
  const runTitle = computed(() => workflowStore.activeWorkflowRun?.name || '工作流运行详情')
  const runSubtitle = computed(() => {
    const run = workflowStore.activeWorkflowRun
    if (!run) {
      return '查看运行节点、任务和错误状态'
    }
    return `Run ID: ${run.id}`
  })

  async function loadRun() {
    if (!runId.value) {
      return
    }
    await workflowStore.loadWorkflowRun(runId.value)
  }

  async function handleSync() {
    await workflowStore.syncActiveWorkflowRun(runId.value)
  }

  async function handleCancel() {
    await workflowStore.cancelActiveWorkflowRun(runId.value)
    message.success('工作流运行已取消')
  }

  async function handleRetryNode(nodeId: string) {
    if (!runId.value) {
      return
    }
    await workflowStore.retryWorkflowRunNode(runId.value, nodeId)
    message.success('工作流节点已重试')
  }

  function goBackToWorkflow() {
    const projectId = workflowStore.activeWorkflowRun?.project_id
    router.push({
      name: 'Workflow',
      query: projectId ? { project_id: projectId } : undefined
    })
  }

  onMounted(() => {
    void loadRun()
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
