<template>
  <div class="workflow-page">
    <div class="workflow-shell">
      <AppPageHeader :title="t('workflow.title')" :subtitle="t('workflow.subtitle')" />

      <div class="workflow-layout">
        <WorkflowStepSidebar
          :groups="groups"
          :active-group-id="activeGroup?.id ?? null"
          @select="handleGroupSelect"
        />
        <WorkflowRunPanel
          :group="activeGroup"
          :selected-tool-slug="activeSelectedToolSlug"
          @select-tool="handleToolSelect"
        />
        <WorkflowArtifactPanel
          :group="activeGroup"
          :selected-tool-slug="activeSelectedToolSlug"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import WorkflowArtifactPanel from '@/components/workflow/WorkflowArtifactPanel.vue'
  import WorkflowRunPanel from '@/components/workflow/WorkflowRunPanel.vue'
  import WorkflowStepSidebar from '@/components/workflow/WorkflowStepSidebar.vue'
  import { useArtifactsStore, useToolsStore, useUserStore, useWorkflowStore } from '@/stores'

  const { t } = useI18n()
  const artifactsStore = useArtifactsStore()
  const toolsStore = useToolsStore()
  const userStore = useUserStore()
  const workflowStore = useWorkflowStore()

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
      linear-gradient(180deg, rgba(24, 144, 255, 0.06) 0%, rgba(255, 255, 255, 0) 260px),
      @bg-light;
  }

  .workflow-shell {
    width: min(100%, calc(100vw - 32px));
    max-width: none;
    margin: 0 auto;
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
