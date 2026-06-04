<template>
  <div class="workflow-page">
    <div class="workflow-shell workflow-deck">
      <AppPageHeader :title="t('workflow.title')" :subtitle="t('workflow.subtitle')" align="center" />

      <a-tabs v-model:activeKey="activeMode" class="workflow-mode-tabs">
        <a-tab-pane key="manual" :tab="t('workflow.mode.manual')">
          <div class="workflow-layout">
            <WorkflowStepSidebar
              :groups="groups"
              :active-group-id="activeGroup?.id ?? null"
              @select="handleGroupSelect"
            />
            <WorkflowRunPanel
              :group="activeGroup"
              :selected-tool-slug="activeSelectedToolSlug"
              :artifact-selection-path="artifactSelectionPath"
              :result-task-id="activeResultTaskId"
              :result-task-summary="activeResultTaskSummary"
              @select-tool="handleToolSelect"
              @result-task-change="handleResultTaskChange"
            />
            <WorkflowArtifactPanel
              :group="activeGroup"
              :selected-tool-slug="activeSelectedToolSlug"
              @select-artifact-path="handleArtifactPathSelect"
            />
          </div>
        </a-tab-pane>
        <a-tab-pane key="agent" :tab="t('workflow.mode.agent')">
          <AiddAgentPanel />
        </a-tab-pane>
      </a-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AiddAgentPanel from '@/components/workflow/AiddAgentPanel.vue'
  import WorkflowArtifactPanel from '@/components/workflow/WorkflowArtifactPanel.vue'
  import WorkflowRunPanel from '@/components/workflow/WorkflowRunPanel.vue'
  import WorkflowStepSidebar from '@/components/workflow/WorkflowStepSidebar.vue'
  import { useArtifactsStore, useToolsStore, useUserStore, useWorkflowStore } from '@/stores'
  import type { WorkflowArtifactSelectionPath } from '@/workflow/artifact-hierarchy'

  const { t } = useI18n()
  const artifactsStore = useArtifactsStore()
  const toolsStore = useToolsStore()
  const userStore = useUserStore()
  const workflowStore = useWorkflowStore()
  type WorkflowMode = 'manual' | 'agent'
  const activeMode = ref<WorkflowMode>('manual')
  const artifactSelectionPath = ref<WorkflowArtifactSelectionPath | null>(null)
  const activeResultTaskId = ref<string | null>(null)
  const activeResultToolSlug = ref<string | null>(null)

  const groups = computed(() => toolsStore.workbenchGroups)
  const activeGroup = computed(() => {
    if (groups.value.length === 0) {
      return null
    }

    return groups.value.find((group) => group.id === workflowStore.activeGroupId) ?? groups.value[0] ?? null
  })

  const activeSelectedToolSlug = computed(() => {
    if (!activeGroup.value) {
      return null
    }

    return workflowStore.selectedToolByGroup[activeGroup.value.id] ?? null
  })

  const currentToolTask = computed(() => {
    if (!activeSelectedToolSlug.value) {
      return null
    }

    return workflowStore.taskByTool[activeSelectedToolSlug.value] ?? null
  })

  const activeResultTaskSummary = computed(() => {
    if (!activeResultTaskId.value || !activeResultToolSlug.value) {
      return null
    }

    const matchingTask = workflowStore.taskByTool[activeResultToolSlug.value]
    if (!matchingTask || matchingTask.id !== activeResultTaskId.value) {
      return null
    }

    return matchingTask
  })

  function getDefaultToolSlug(groupId: string): string | null {
    const group = groups.value.find((item) => item.id === groupId)
    if (!group || group.tools.length === 0) {
      return null
    }

    return group.tools.find((tool) => tool.is_recommended)?.slug ?? group.tools[0]?.slug ?? null
  }

  function handleGroupSelect(groupId: string) {
    workflowStore.setActiveGroup(groupId)
  }

  function handleToolSelect(toolSlug: string) {
    if (!activeGroup.value) {
      return
    }

    workflowStore.selectTool(activeGroup.value.id, toolSlug)
  }

  function handleResultTaskChange(taskId: string) {
    activeResultTaskId.value = taskId
    activeResultToolSlug.value = activeSelectedToolSlug.value
  }

  function handleArtifactPathSelect(path: WorkflowArtifactSelectionPath) {
    if (path.groupId && path.groupId !== workflowStore.activeGroupId) {
      workflowStore.setActiveGroup(path.groupId)
    }

    if (path.groupId && path.toolSlug) {
      workflowStore.selectTool(path.groupId, path.toolSlug)
    }

    artifactSelectionPath.value = {
      ...path,
      token: Date.now()
    }

    activeResultTaskId.value = path.taskId ?? null
    activeResultToolSlug.value = path.toolSlug ?? null
  }

  function syncResultContextToCurrentTool(force = false) {
    const currentToolSlug = activeSelectedToolSlug.value

    if (!currentToolSlug) {
      activeResultTaskId.value = null
      activeResultToolSlug.value = null
      return
    }

    if (force || activeResultToolSlug.value !== currentToolSlug || !activeResultTaskId.value) {
      activeResultTaskId.value = currentToolTask.value?.id ?? null
      activeResultToolSlug.value = currentToolSlug
    }
  }

  watch(
    groups,
    (nextGroups) => {
      if (nextGroups.length === 0) {
        workflowStore.setActiveGroup(null)
        return
      }

      const activeGroupId = workflowStore.activeGroupId
      if (!activeGroupId || !nextGroups.some((group) => group.id === activeGroupId)) {
        workflowStore.setActiveGroup(nextGroups[0]?.id ?? null)
      }
    },
    { immediate: true }
  )

  watch(
    activeGroup,
    (group) => {
      if (!group) {
        return
      }

      const selectedToolSlug = workflowStore.selectedToolByGroup[group.id]
      if (!selectedToolSlug || !group.tools.some((tool) => tool.slug === selectedToolSlug)) {
        const fallbackToolSlug = getDefaultToolSlug(group.id)
        if (fallbackToolSlug) {
          workflowStore.selectTool(group.id, fallbackToolSlug)
        }
      }
    },
    { immediate: true }
  )

  watch(
    () => [activeSelectedToolSlug.value, currentToolTask.value?.id] as const,
    () => {
      syncResultContextToCurrentTool()
    },
    { immediate: true }
  )

  watch(
    () => [userStore.isLoggedIn, userStore.user?.id] as const,
    async ([isLoggedIn, userId]) => {
      workflowStore.syncOwnerUserId(isLoggedIn ? userId ?? undefined : undefined)

      if (!isLoggedIn) {
        artifactsStore.resetArtifacts()
        return
      }

      await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
    },
    { immediate: true }
  )

  onMounted(async () => {
    await toolsStore.fetchWorkbenchGroups()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-page {
    padding: @spacing-xl 0 @spacing-xxl;
    min-height: calc(100vh - @header-height - @footer-height);
    background:
      radial-gradient(circle at top, rgba(13, 110, 253, 0.08) 0%, rgba(255, 255, 255, 0) 32%),
      linear-gradient(180deg, rgba(24, 144, 255, 0.06) 0%, rgba(255, 255, 255, 0) 260px),
      @bg-light;
  }

  .workflow-shell {
    width: min(100%, calc(100vw - 32px));
    max-width: none;
    margin: 0 auto;
  }

  .workflow-deck {
    position: relative;
    padding: @spacing-sm;
    border-radius: 32px;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.45) 0%, rgba(255, 255, 255, 0.18) 100%),
      linear-gradient(135deg, rgba(13, 110, 253, 0.04) 0%, rgba(46, 196, 182, 0.04) 100%);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
  }

  .workflow-mode-tabs {
    :deep(.ant-tabs-nav) {
      margin: 0 0 @spacing-lg;
      padding: 0 @spacing-md;
    }

    :deep(.ant-tabs-tab) {
      padding: @spacing-sm @spacing-md;
      color: @text-color-light-secondary;
      font-weight: 600;
      letter-spacing: 0;
    }

    :deep(.ant-tabs-tab-active .ant-tabs-tab-btn) {
      color: @primary-color;
    }

    :deep(.ant-tabs-content-holder) {
      min-width: 0;
      overflow: visible;
    }

    :deep(.ant-tabs-content),
    :deep(.ant-tabs-tabpane) {
      overflow: visible;
    }
  }

  .workflow-layout {
    display: grid;
    grid-template-columns: minmax(260px, 320px) minmax(0, 1fr) minmax(320px, 380px);
    gap: @spacing-lg;
    align-items: start;

    @media (max-width: @screen-xl) {
      grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);

      :deep(.artifacts-column) {
        grid-column: 1 / -1;
        order: 3;
      }
    }

    @media (max-width: @screen-md) {
      grid-template-columns: minmax(0, 1fr);
      gap: @spacing-md;

      :deep(.groups-column) {
        order: 1;
      }

      :deep(.tools-column) {
        order: 2;
      }

      :deep(.artifacts-column) {
        grid-column: auto;
        order: 3;
      }
    }
  }
</style>
