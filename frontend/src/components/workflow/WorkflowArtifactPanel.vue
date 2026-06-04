<template>
  <section class="workflow-column artifacts-column">
    <div class="column-card artifact-lab-panel">
      <div class="column-header">
        <div>
          <h2 class="column-title">{{ t('workflow.columns.artifacts') }}</h2>
          <p class="column-subtitle">{{ t('workflow.columns.artifactsHint') }}</p>
        </div>
        <a-button
          v-if="userStore.isLoggedIn"
          type="link"
          size="small"
          :loading="artifactsStore.loading"
          @click="refreshArtifacts"
        >
          {{ t('common.refresh') }}
        </a-button>
      </div>

      <a-alert
        v-if="!userStore.isLoggedIn"
        type="info"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #message>
          {{ t('auth.loginRequired') }}
        </template>
      </a-alert>

      <div v-else class="artifact-groups">
        <div v-if="activeTask" class="task-summary-card">
          <div class="task-summary-head">
            <span class="task-summary-label">{{ t('workflow.currentTool.lastTask') }}</span>
            <strong class="task-summary-heading">{{ getActiveTaskDisplayName() }}</strong>
            <p class="task-summary-meta">
              <span class="artifact-task-short-id">{{ formatTaskShortId(activeTask.id) }}</span>
              <span>{{ formatDateTime(activeTask.created_at) }}</span>
            </p>
          </div>
          <div class="task-summary-grid">
            <div class="task-summary-row">
              <span class="task-summary-label">{{ t('tasks.status') }}</span>
              <span class="task-summary-value">{{ activeTask.status }}</span>
            </div>
            <div class="task-summary-row">
              <span class="task-summary-label">{{ t('tasks.progress') }}</span>
              <span class="task-summary-value">{{ activeTask.progress }}%</span>
            </div>
          </div>
        </div>

        <div class="artifact-group">
          <h3 class="artifact-group-title">{{ t('workflow.artifacts.currentGroup') }}</h3>
          <div v-if="currentGroupNodes.length > 0" class="artifact-tree">
            <section
              v-for="groupNode in currentGroupNodes"
              :key="groupKey('current', groupNode.groupId)"
              class="artifact-group-shell"
            >
              <button
                type="button"
                class="artifact-group-toggle"
                @click="toggleGroup('current', groupNode.groupId)"
              >
                <span class="artifact-group-toggle-copy">
                  <span class="artifact-group-toggle-kicker">{{ t('tools.artifactGroupLabel') }}</span>
                  <strong class="artifact-group-heading">{{ getGroupDisplayName(groupNode) }}</strong>
                </span>
                <a-tag class="artifact-group-toggle-count">{{ groupNode.tools.length }}</a-tag>
              </button>

              <div v-if="isGroupExpanded('current', groupNode.groupId)" class="artifact-group-content">
                <section
                  v-for="toolNode in groupNode.tools"
                  :key="toolKey('current', groupNode.groupId, toolNode.toolSlug)"
                  class="artifact-tool-section"
                  :class="{ 'is-active': selectedToolSlug === toolNode.toolSlug }"
                >
                  <button
                    type="button"
                    class="artifact-tool-toggle"
                    @click="toggleTool('current', groupNode.groupId, toolNode.toolSlug)"
                  >
                    <span class="artifact-tool-header">
                      <span class="artifact-tool-kicker">{{ t('workflow.artifacts.sourceToolLabel') }}</span>
                      <strong class="artifact-tool-title">{{ toolNode.toolName }}</strong>
                    </span>
                    <a-tag class="artifact-tool-toggle-count">
                      {{ t('workflow.artifacts.taskCount', { count: toolNode.tasks.length }) }}
                    </a-tag>
                  </button>

                  <div v-if="isToolExpanded('current', groupNode.groupId, toolNode.toolSlug)" class="artifact-task-list">
                    <article
                      v-for="taskNode in toolNode.tasks"
                      :key="taskKey('current', groupNode.groupId, toolNode.toolSlug, taskNode.taskId)"
                      class="artifact-task-card"
                    >
                      <div class="artifact-task-header">
                        <button
                          type="button"
                          class="artifact-task-toggle"
                          @click="toggleTask('current', groupNode.groupId, toolNode.toolSlug, taskNode.taskId)"
                        >
                          <div class="artifact-task-main">
                            <span class="artifact-task-kicker">{{ t('workflow.artifacts.taskLabel') }}</span>
                            <strong class="artifact-task-title">{{ getTaskDisplayName(taskNode) }}</strong>
                            <p class="artifact-task-meta">
                              <span class="artifact-task-short-id">{{ formatTaskShortId(taskNode.taskId) }}</span>
                              <span>{{ formatDateTime(taskNode.latestCreatedAt) }}</span>
                            </p>
                          </div>
                        </button>
                        <div class="artifact-action">
                          <a-tag class="artifact-task-count">
                            {{ t('workflow.artifacts.taskCount', { count: taskNode.artifacts.length }) }}
                          </a-tag>
                          <a-button
                            type="link"
                            size="small"
                            class="artifact-action-button"
                            @click.stop="selectTaskPath(groupNode, toolNode, taskNode)"
                          >
                            {{ t('workflow.artifacts.locatePath') }}
                          </a-button>
                          <a-button
                            type="link"
                            size="small"
                            class="artifact-action-button"
                            @click.stop="openTaskDetail(taskNode.taskId)"
                          >
                            {{ t('workflow.currentTool.viewTask') }}
                          </a-button>
                        </div>
                      </div>

                      <div v-if="isTaskExpanded('current', groupNode.groupId, toolNode.toolSlug, taskNode.taskId)" class="artifact-task-content">
                        <div class="artifact-task-meta-grid">
                          <div class="artifact-task-meta-item">
                            <span class="artifact-meta-label">{{ t('workflow.artifacts.sourceToolLabel') }}</span>
                            <strong class="artifact-meta-value">{{ toolNode.toolName }}</strong>
                          </div>
                          <div class="artifact-task-meta-item">
                            <span class="artifact-meta-label">{{ t('workflow.artifacts.generatedAtLabel') }}</span>
                            <strong class="artifact-meta-value">{{ formatDateTime(taskNode.latestCreatedAt) }}</strong>
                          </div>
                        </div>

                        <div class="artifact-list artifact-list-compact">
                          <button
                            v-for="artifact in visibleArtifacts(taskNode.artifacts)"
                            :key="artifact.id"
                            type="button"
                            class="artifact-item artifact-item-button"
                            @click.stop="selectArtifactPath(groupNode, toolNode, taskNode, artifact)"
                          >
                            <div class="artifact-copy">
                              <strong class="artifact-name">{{ artifact.filename }}</strong>
                              <p class="artifact-meta">{{ formatDateTime(artifact.created_at) }}</p>
                            </div>
                          </button>
                        </div>

                        <p v-if="hiddenArtifactCount(taskNode.artifacts) > 0" class="artifact-more">
                          {{ t('workflow.artifacts.moreArtifacts', { count: hiddenArtifactCount(taskNode.artifacts) }) }}
                        </p>
                      </div>
                    </article>
                  </div>
                </section>
              </div>
            </section>
          </div>
          <a-empty v-else :description="t('workflow.artifacts.emptyCurrentGroup')" />
        </div>

        <div class="artifact-group">
          <h3 class="artifact-group-title">{{ t('workflow.artifacts.recentGroup') }}</h3>
          <div v-if="recentGroupNodes.length > 0" class="artifact-tree">
            <section
              v-for="groupNode in recentGroupNodes"
              :key="groupKey('recent', groupNode.groupId)"
              class="artifact-group-shell"
            >
              <button
                type="button"
                class="artifact-group-toggle"
                @click="toggleGroup('recent', groupNode.groupId)"
              >
                <span class="artifact-group-toggle-copy">
                  <span class="artifact-group-toggle-kicker">{{ t('tools.artifactGroupLabel') }}</span>
                  <strong class="artifact-group-heading">{{ getGroupDisplayName(groupNode) }}</strong>
                </span>
                <a-tag class="artifact-group-toggle-count">{{ groupNode.tools.length }}</a-tag>
              </button>

              <div v-if="isGroupExpanded('recent', groupNode.groupId)" class="artifact-group-content">
                <section
                  v-for="toolNode in groupNode.tools"
                  :key="toolKey('recent', groupNode.groupId, toolNode.toolSlug)"
                  class="artifact-tool-section"
                  :class="{ 'is-active': selectedToolSlug === toolNode.toolSlug }"
                >
                  <button
                    type="button"
                    class="artifact-tool-toggle"
                    @click="toggleTool('recent', groupNode.groupId, toolNode.toolSlug)"
                  >
                    <span class="artifact-tool-header">
                      <span class="artifact-tool-kicker">{{ t('workflow.artifacts.sourceToolLabel') }}</span>
                      <strong class="artifact-tool-title">{{ toolNode.toolName }}</strong>
                    </span>
                    <a-tag class="artifact-tool-toggle-count">
                      {{ t('workflow.artifacts.taskCount', { count: toolNode.tasks.length }) }}
                    </a-tag>
                  </button>

                  <div v-if="isToolExpanded('recent', groupNode.groupId, toolNode.toolSlug)" class="artifact-task-list">
                    <article
                      v-for="taskNode in toolNode.tasks"
                      :key="taskKey('recent', groupNode.groupId, toolNode.toolSlug, taskNode.taskId)"
                      class="artifact-task-card"
                    >
                      <div class="artifact-task-header">
                        <button
                          type="button"
                          class="artifact-task-toggle"
                          @click="toggleTask('recent', groupNode.groupId, toolNode.toolSlug, taskNode.taskId)"
                        >
                          <div class="artifact-task-main">
                            <span class="artifact-task-kicker">{{ t('workflow.artifacts.taskLabel') }}</span>
                            <strong class="artifact-task-title">{{ getTaskDisplayName(taskNode) }}</strong>
                            <p class="artifact-task-meta">
                              <span class="artifact-task-short-id">{{ formatTaskShortId(taskNode.taskId) }}</span>
                              <span>{{ formatDateTime(taskNode.latestCreatedAt) }}</span>
                            </p>
                          </div>
                        </button>
                        <div class="artifact-action">
                          <a-tag class="artifact-task-count">
                            {{ t('workflow.artifacts.taskCount', { count: taskNode.artifacts.length }) }}
                          </a-tag>
                          <a-button
                            type="link"
                            size="small"
                            class="artifact-action-button"
                            @click.stop="selectTaskPath(groupNode, toolNode, taskNode)"
                          >
                            {{ t('workflow.artifacts.locatePath') }}
                          </a-button>
                          <a-button
                            type="link"
                            size="small"
                            class="artifact-action-button"
                            @click.stop="openTaskDetail(taskNode.taskId)"
                          >
                            {{ t('workflow.currentTool.viewTask') }}
                          </a-button>
                        </div>
                      </div>

                      <div v-if="isTaskExpanded('recent', groupNode.groupId, toolNode.toolSlug, taskNode.taskId)" class="artifact-task-content">
                        <div class="artifact-task-meta-grid">
                          <div class="artifact-task-meta-item">
                            <span class="artifact-meta-label">{{ t('workflow.artifacts.sourceToolLabel') }}</span>
                            <strong class="artifact-meta-value">{{ toolNode.toolName }}</strong>
                          </div>
                          <div class="artifact-task-meta-item">
                            <span class="artifact-meta-label">{{ t('workflow.artifacts.generatedAtLabel') }}</span>
                            <strong class="artifact-meta-value">{{ formatDateTime(taskNode.latestCreatedAt) }}</strong>
                          </div>
                        </div>

                        <div class="artifact-list artifact-list-compact">
                          <button
                            v-for="artifact in visibleArtifacts(taskNode.artifacts)"
                            :key="artifact.id"
                            type="button"
                            class="artifact-item artifact-item-button"
                            @click.stop="selectArtifactPath(groupNode, toolNode, taskNode, artifact)"
                          >
                            <div class="artifact-copy">
                              <strong class="artifact-name">{{ artifact.filename }}</strong>
                              <p class="artifact-meta">{{ formatDateTime(artifact.created_at) }}</p>
                            </div>
                          </button>
                        </div>

                        <p v-if="hiddenArtifactCount(taskNode.artifacts) > 0" class="artifact-more">
                          {{ t('workflow.artifacts.moreArtifacts', { count: hiddenArtifactCount(taskNode.artifacts) }) }}
                        </p>
                      </div>
                    </article>
                  </div>
                </section>
              </div>
            </section>
          </div>
          <a-empty v-else :description="t('workflow.artifacts.emptyRecent')" />
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
  import { computed, ref, watch } from 'vue'
  import { useRouter } from 'vue-router'
  import dayjs from 'dayjs'
  import { useI18n } from 'vue-i18n'
  import { useArtifactsStore, useToolsStore, useUserStore, useWorkflowStore } from '@/stores'
  import type { ArtifactFile, WorkbenchGroup } from '@/types/models'
  import {
    buildWorkflowArtifactHierarchy,
    type WorkflowArtifactGroupNode,
    type WorkflowArtifactSelectionPath,
    type WorkflowArtifactTaskNode,
    type WorkflowArtifactToolNode
  } from '../../workflow/artifact-hierarchy.ts'

  const ARTIFACT_TASK_PREVIEW_LIMIT = 3

  const props = defineProps<{
    group?: WorkbenchGroup | null
    selectedToolSlug?: string | null
  }>()

  const emit = defineEmits<{
    'select-artifact-path': [path: WorkflowArtifactSelectionPath]
  }>()

  const { t } = useI18n()
  const router = useRouter()
  const artifactsStore = useArtifactsStore()
  const toolsStore = useToolsStore()
  const userStore = useUserStore()
  const workflowStore = useWorkflowStore()
  const expandedGroupIds = ref<string[]>([])
  const expandedToolSlugs = ref<string[]>([])
  const expandedTaskIds = ref<string[]>([])

  const sortedArtifacts = computed(() => {
    return [...artifactsStore.items].sort((left, right) => {
      return Date.parse(right.created_at) - Date.parse(left.created_at)
    })
  })

  const currentGroupNodes = computed(() => {
    return buildWorkflowArtifactHierarchy({
      groups: toolsStore.workbenchGroups,
      artifacts: sortedArtifacts.value,
      scope: 'current-group',
      currentGroupId: props.group?.id ?? null
    }).groups
  })

  const recentGroupNodes = computed(() => {
    return buildWorkflowArtifactHierarchy({
      groups: toolsStore.workbenchGroups,
      artifacts: sortedArtifacts.value,
      scope: 'global'
    }).groups
  })

  const activeTask = computed(() => {
    if (!props.selectedToolSlug) {
      return null
    }

    return workflowStore.taskByTool[props.selectedToolSlug] ?? null
  })

  async function refreshArtifacts() {
    if (!userStore.isLoggedIn) {
      return
    }

    await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
  }

  function openTaskDetail(taskId: string) {
    router.push(`/tasks/${taskId}`)
  }

  function getGroupDisplayName(groupNode: WorkflowArtifactGroupNode): string {
    if (groupNode.isUngrouped) {
      return t('workflow.artifacts.ungroupedGroup')
    }

    return groupNode.groupName
  }

  function visibleArtifacts(artifacts: ArtifactFile[]): ArtifactFile[] {
    return artifacts.slice(0, ARTIFACT_TASK_PREVIEW_LIMIT)
  }

  function hiddenArtifactCount(artifacts: ArtifactFile[]): number {
    return Math.max(artifacts.length - ARTIFACT_TASK_PREVIEW_LIMIT, 0)
  }

  function formatTaskShortId(taskId: string): string {
    return `#${taskId.slice(0, 8)}`
  }

  function getTaskDisplayName(taskNode: WorkflowArtifactTaskNode): string {
    return taskNode.taskName?.trim() || `${t('workflow.artifacts.taskLabel')} ${formatTaskShortId(taskNode.taskId)}`
  }

  function getActiveTaskDisplayName(): string {
    if (!activeTask.value) {
      return ''
    }

    return activeTask.value.name?.trim() || `${t('workflow.artifacts.taskLabel')} ${formatTaskShortId(activeTask.value.id)}`
  }

  function formatDateTime(value: string): string {
    if (!value) {
      return '--'
    }

    return dayjs(value).format('YYYY-MM-DD HH:mm:ss')
  }

  function groupKey(scope: 'current' | 'recent', groupId: string): string {
    return `${scope}:${groupId}`
  }

  function toolKey(scope: 'current' | 'recent', groupId: string, toolSlug: string): string {
    return `${scope}:${groupId}:${toolSlug}`
  }

  function taskKey(scope: 'current' | 'recent', groupId: string, toolSlug: string, taskId: string): string {
    return `${scope}:${groupId}:${toolSlug}:${taskId}`
  }

  function ensureKey(collection: string[], key: string): string[] {
    if (collection.includes(key)) {
      return collection
    }

    return [...collection, key]
  }

  function toggleKey(target: typeof expandedGroupIds, key: string) {
    target.value = target.value.includes(key)
      ? target.value.filter((item) => item !== key)
      : [...target.value, key]
  }

  function toggleGroup(scope: 'current' | 'recent', groupId: string) {
    toggleKey(expandedGroupIds, groupKey(scope, groupId))
  }

  function toggleTool(scope: 'current' | 'recent', groupId: string, toolSlug: string) {
    expandedGroupIds.value = ensureKey(expandedGroupIds.value, groupKey(scope, groupId))
    toggleKey(expandedToolSlugs, toolKey(scope, groupId, toolSlug))
  }

  function toggleTask(scope: 'current' | 'recent', groupId: string, toolSlug: string, taskId: string) {
    expandedGroupIds.value = ensureKey(expandedGroupIds.value, groupKey(scope, groupId))
    expandedToolSlugs.value = ensureKey(expandedToolSlugs.value, toolKey(scope, groupId, toolSlug))
    toggleKey(expandedTaskIds, taskKey(scope, groupId, toolSlug, taskId))
  }

  function isGroupExpanded(scope: 'current' | 'recent', groupId: string): boolean {
    return expandedGroupIds.value.includes(groupKey(scope, groupId))
  }

  function isToolExpanded(scope: 'current' | 'recent', groupId: string, toolSlug: string): boolean {
    return expandedToolSlugs.value.includes(toolKey(scope, groupId, toolSlug))
  }

  function isTaskExpanded(scope: 'current' | 'recent', groupId: string, toolSlug: string, taskId: string): boolean {
    return expandedTaskIds.value.includes(taskKey(scope, groupId, toolSlug, taskId))
  }

  function selectTaskPath(
    groupNode: WorkflowArtifactGroupNode,
    toolNode: WorkflowArtifactToolNode,
    taskNode: WorkflowArtifactTaskNode
  ) {
    emit('select-artifact-path', {
      token: Date.now(),
      groupId: groupNode.groupId,
      toolSlug: toolNode.toolSlug,
      taskId: taskNode.taskId
    })
  }

  function selectArtifactPath(
    groupNode: WorkflowArtifactGroupNode,
    toolNode: WorkflowArtifactToolNode,
    taskNode: WorkflowArtifactTaskNode,
    artifact: ArtifactFile
  ) {
    emit('select-artifact-path', {
      token: Date.now(),
      groupId: groupNode.groupId,
      toolSlug: toolNode.toolSlug,
      taskId: taskNode.taskId,
      artifactId: artifact.id
    })
  }

  function ensureDefaultExpansion() {
    const currentGroupNode = props.group
      ? currentGroupNodes.value.find((group) => group.groupId === props.group?.id) ?? currentGroupNodes.value[0]
      : currentGroupNodes.value[0]
    const currentToolNode = currentGroupNode?.tools.find((tool) => tool.toolSlug === props.selectedToolSlug) ?? currentGroupNode?.tools[0]
    const currentTaskNode = currentToolNode?.tasks.find((task) => task.taskId === activeTask.value?.id) ?? currentToolNode?.tasks[0]

    if (currentGroupNode) {
      expandedGroupIds.value = ensureKey(expandedGroupIds.value, groupKey('current', currentGroupNode.groupId))
      expandedGroupIds.value = ensureKey(expandedGroupIds.value, groupKey('recent', currentGroupNode.groupId))
    }

    if (currentGroupNode && currentToolNode) {
      expandedToolSlugs.value = ensureKey(expandedToolSlugs.value, toolKey('current', currentGroupNode.groupId, currentToolNode.toolSlug))
      expandedToolSlugs.value = ensureKey(expandedToolSlugs.value, toolKey('recent', currentGroupNode.groupId, currentToolNode.toolSlug))
    }

    if (currentGroupNode && currentToolNode && currentTaskNode) {
      expandedTaskIds.value = ensureKey(expandedTaskIds.value, taskKey('current', currentGroupNode.groupId, currentToolNode.toolSlug, currentTaskNode.taskId))
    }
  }

  watch(
    () => [
      props.group?.id,
      props.selectedToolSlug,
      activeTask.value?.id,
      currentGroupNodes.value.map((group) => `${group.groupId}:${group.tools.map((tool) => tool.toolSlug).join(',')}`).join(';'),
      recentGroupNodes.value.map((group) => `${group.groupId}:${group.tools.map((tool) => tool.toolSlug).join(',')}`).join(';')
    ] as const,
    () => {
      ensureDefaultExpansion()
    },
    { immediate: true }
  )
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-column {
    min-width: 0;

    @media (min-width: @screen-md) {
      position: sticky;
      top: calc(@header-height + @spacing-md);
      align-self: start;
      z-index: 2;
      max-height: calc(100vh - @header-height - @spacing-xl);
      overflow-y: auto;
    }
  }

  .column-card {
    .card();
    height: 100%;
    border: 1px solid rgba(205, 217, 235, 0.9);
    background:
      linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(245, 249, 255, 0.98) 100%);
    box-shadow: 0 20px 42px rgb(15 23 42 / 6%);
  }

  .artifact-lab-panel {
    position: relative;
    overflow: visible;

    &::before {
      content: '';
      position: absolute;
      inset: 0 0 auto;
      height: 140px;
      background: linear-gradient(135deg, rgba(13, 110, 253, 0.1) 0%, rgba(46, 196, 182, 0.1) 100%);
      pointer-events: none;
    }
  }

  .column-header {
    position: relative;
    z-index: 1;
    display: flex;
    justify-content: space-between;
    gap: @spacing-md;
    align-items: flex-start;
  }

  .column-title {
    font-size: @font-size-xl;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-xs;
  }

  .column-subtitle {
    color: @text-color-light-secondary;
    margin-bottom: @spacing-lg;
  }

  .artifact-groups {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    gap: @spacing-lg;
  }

  .artifact-group {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .artifact-group-title {
    margin: 0;
    font-size: @font-size-sm;
    font-weight: @font-weight-semibold;
    color: @text-color-light-secondary;
  }

  .artifact-tree,
  .artifact-group-content,
  .artifact-task-list,
  .task-summary-card {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .artifact-group-shell {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
  }

  .artifact-group-toggle,
  .artifact-tool-toggle,
  .artifact-task-toggle,
  .artifact-item-button {
    width: 100%;
    border: none;
    background: none;
    padding: 0;
    text-align: left;
    cursor: pointer;
  }

  .artifact-group-toggle {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: @spacing-sm;
    align-items: center;
    padding: @spacing-sm @spacing-md;
    border: 1px solid rgba(210, 220, 235, 0.92);
    border-radius: @border-radius-lg;
    background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
    box-shadow: 0 10px 24px rgb(15 23 42 / 4%);
  }

  .artifact-group-toggle-copy {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    min-width: 0;
  }

  .artifact-group-toggle-kicker {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .artifact-group-heading {
    margin: 0;
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    font-weight: @font-weight-semibold;
  }

  .artifact-group-toggle-count {
    margin-inline-end: 0;
  }

  .artifact-tool-section {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
    padding: @spacing-md;
    border: 1px solid rgba(215, 224, 238, 0.9);
    border-radius: @border-radius-lg;
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(247, 250, 255, 0.98) 100%);
  }

  .artifact-tool-section.is-active {
    border-color: rgba(24, 144, 255, 0.4);
    box-shadow: 0 0 0 3px rgb(24 144 255 / 8%);
  }

  .artifact-tool-toggle {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: @spacing-sm;
    align-items: center;
  }

  .artifact-tool-header {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    min-width: 0;
  }

  .artifact-tool-kicker {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .artifact-tool-title {
    color: @text-color-light-primary;
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
  }

  .artifact-tool-toggle-count,
  .artifact-task-count {
    margin-inline-end: 0;
    white-space: nowrap;
  }

  .artifact-task-card {
    display: flex;
    flex-direction: column;
    gap: @spacing-md;
    padding: @spacing-lg;
    border: 1px solid rgba(215, 224, 238, 0.92);
    border-radius: @border-radius-lg;
    background: linear-gradient(180deg, #fff 0%, #f8fbff 100%);
    box-shadow: 0 14px 30px rgb(15 23 42 / 5%);
  }

  .artifact-task-header {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: @spacing-md;
    align-items: start;
  }

  .artifact-task-main {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    min-width: 0;
  }

  .artifact-task-kicker {
    display: block;
    margin-bottom: @spacing-xs;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: @line-height-base;
  }

  .artifact-task-title {
    display: block;
    color: @text-color-light-primary;
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
    line-height: @line-height-base;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  .artifact-task-meta,
  .task-summary-meta {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-xs;
    align-items: center;
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: @line-height-base;
  }

  .artifact-task-short-id {
    display: inline-flex;
    align-items: center;
    padding: 2px @spacing-xs;
    border: 1px solid rgba(205, 217, 235, 0.9);
    border-radius: 999px;
    background: #f8fbff;
    color: #355070;
    font-family: @font-family-mono;
    white-space: nowrap;
  }

  .artifact-action {
    align-self: start;
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-xs;
    justify-content: flex-end;
  }

  .artifact-action-button {
    padding-inline: @spacing-xs;
    white-space: nowrap;
  }

  .artifact-task-content {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .artifact-task-meta-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: @spacing-sm;
  }

  .artifact-task-meta-item {
    min-width: 0;
    padding: @spacing-sm @spacing-md;
    border: 1px solid rgba(228, 235, 244, 0.96);
    border-radius: @border-radius-md;
    background: rgba(248, 251, 255, 0.92);
  }

  .artifact-meta-label {
    display: block;
    margin-bottom: @spacing-xs;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: @line-height-base;
  }

  .artifact-meta-value {
    display: block;
    color: @text-color-light-primary;
    font-size: @font-size-xs;
    line-height: @line-height-base;
    overflow-wrap: anywhere;
  }

  .task-summary-head {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
  }

  .task-summary-heading {
    color: @text-color-light-primary;
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
  }

  .task-summary-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: @spacing-sm;
  }

  .task-summary-row {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: @spacing-sm @spacing-md;
    border: 1px solid rgba(228, 235, 244, 0.96);
    border-radius: @border-radius-md;
    background: rgba(248, 251, 255, 0.88);
  }

  .artifact-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .artifact-item {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: @spacing-sm;
    align-items: start;
    padding: @spacing-sm;
    border: 1px solid #eef2f7;
    border-radius: @border-radius-md;
    background: #fff;
  }

  .artifact-item-button {
    transition: border-color 0.2s ease, background 0.2s ease;
  }

  .artifact-item-button:hover {
    border-color: rgba(24, 144, 255, 0.45);
    background: #f8fbff;
  }

  .artifact-list-compact {
    gap: @spacing-xs;

    .artifact-item {
      padding: @spacing-xs @spacing-sm;
      background: #f8fafc;
    }
  }

  .artifact-copy {
    min-width: 0;
  }

  .artifact-name {
    display: block;
    font-size: @font-size-sm;
    margin-bottom: @spacing-xs;
    overflow-wrap: anywhere;
  }

  .artifact-meta,
  .task-summary-label {
    margin: 0;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: @line-height-base;
    overflow-wrap: anywhere;
  }

  .artifact-more {
    margin: @spacing-xs 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: @line-height-base;
  }

  .task-summary-card {
    border: 1px solid rgba(205, 217, 235, 0.9);
    border-radius: @border-radius-lg;
    padding: @spacing-md;
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(244, 248, 255, 0.96) 100%);
    box-shadow: 0 12px 24px rgb(15 23 42 / 5%);
  }

  .task-summary-value {
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    font-weight: @font-weight-semibold;
  }

  @media (max-width: @screen-sm) {
    .column-header,
    .artifact-task-header,
    .artifact-task-meta-grid,
    .task-summary-grid {
      grid-template-columns: minmax(0, 1fr);
    }

    .column-header {
      display: grid;
    }

    .artifact-action {
      justify-content: flex-start;
    }
  }
</style>
