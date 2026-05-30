<template>
  <section class="workflow-column artifacts-column">
    <div class="column-card">
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
          <div class="task-summary-row">
            <span class="task-summary-label">{{ t('workflow.currentTool.lastTask') }}</span>
            <strong class="task-summary-value">#{{ activeTask.id }}</strong>
          </div>
          <div class="task-summary-row">
            <span class="task-summary-label">{{ t('tasks.status') }}</span>
            <span class="task-summary-value">{{ activeTask.status }}</span>
          </div>
          <div class="task-summary-row">
            <span class="task-summary-label">{{ t('tasks.progress') }}</span>
            <span class="task-summary-value">{{ activeTask.progress }}%</span>
          </div>
        </div>

        <div class="artifact-group">
          <h3 class="artifact-group-title">{{ t('workflow.artifacts.currentGroup') }}</h3>
          <div v-if="currentGroupTaskGroups.length > 0" class="artifact-task-list">
            <article
              v-for="taskGroup in currentGroupTaskGroups"
              :key="taskGroup.taskId"
              class="artifact-task-card"
            >
              <div class="artifact-task-header">
                <div class="artifact-task-main">
                  <span class="artifact-task-kicker">{{ t('workflow.artifacts.taskLabel') }}</span>
                  <strong class="artifact-task-id">#{{ taskGroup.taskId }}</strong>
                </div>
                <div class="artifact-action">
                  <a-tag class="artifact-task-count">
                    {{ t('workflow.artifacts.taskCount', { count: taskGroup.artifacts.length }) }}
                  </a-tag>
                  <a-button
                    type="link"
                    size="small"
                    class="artifact-action-button"
                    @click="openTaskDetail(taskGroup.taskId)"
                  >
                    {{ t('workflow.currentTool.viewTask') }}
                  </a-button>
                </div>
              </div>
              <div class="artifact-task-meta-grid">
                <div class="artifact-task-meta-item">
                  <span class="artifact-meta-label">{{ t('workflow.artifacts.sourceToolLabel') }}</span>
                  <strong class="artifact-meta-value">{{ taskGroup.toolName }}</strong>
                </div>
                <div class="artifact-task-meta-item">
                  <span class="artifact-meta-label">{{ t('workflow.artifacts.generatedAtLabel') }}</span>
                  <strong class="artifact-meta-value">{{ formatDateTime(taskGroup.latestCreatedAt) }}</strong>
                </div>
              </div>
              <div class="artifact-list artifact-list-compact">
                <div v-for="artifact in taskGroup.visibleArtifacts" :key="artifact.id" class="artifact-item">
                  <div class="artifact-copy">
                    <strong class="artifact-name">{{ artifact.filename }}</strong>
                  </div>
                </div>
              </div>
              <p v-if="taskGroup.hiddenCount > 0" class="artifact-more">
                {{ t('workflow.artifacts.moreArtifacts', { count: taskGroup.hiddenCount }) }}
              </p>
            </article>
          </div>
          <a-empty v-else :description="t('workflow.artifacts.emptyCurrentGroup')" />
        </div>

        <div class="artifact-group">
          <h3 class="artifact-group-title">{{ t('workflow.artifacts.recentGroup') }}</h3>
          <div v-if="recentTaskGroups.length > 0" class="artifact-task-list">
            <article
              v-for="taskGroup in recentTaskGroups"
              :key="taskGroup.taskId"
              class="artifact-task-card"
            >
              <div class="artifact-task-header">
                <div class="artifact-task-main">
                  <span class="artifact-task-kicker">{{ t('workflow.artifacts.taskLabel') }}</span>
                  <strong class="artifact-task-id">#{{ taskGroup.taskId }}</strong>
                </div>
                <div class="artifact-action">
                  <a-tag class="artifact-task-count">
                    {{ t('workflow.artifacts.taskCount', { count: taskGroup.artifacts.length }) }}
                  </a-tag>
                  <a-button
                    type="link"
                    size="small"
                    class="artifact-action-button"
                    @click="openTaskDetail(taskGroup.taskId)"
                  >
                    {{ t('workflow.currentTool.viewTask') }}
                  </a-button>
                </div>
              </div>
              <div class="artifact-task-meta-grid">
                <div class="artifact-task-meta-item">
                  <span class="artifact-meta-label">{{ t('workflow.artifacts.sourceToolLabel') }}</span>
                  <strong class="artifact-meta-value">{{ taskGroup.toolName }}</strong>
                </div>
                <div class="artifact-task-meta-item">
                  <span class="artifact-meta-label">{{ t('workflow.artifacts.generatedAtLabel') }}</span>
                  <strong class="artifact-meta-value">{{ formatDateTime(taskGroup.latestCreatedAt) }}</strong>
                </div>
              </div>
              <div class="artifact-list artifact-list-compact">
                <div v-for="artifact in taskGroup.visibleArtifacts" :key="artifact.id" class="artifact-item">
                  <div class="artifact-copy">
                    <strong class="artifact-name">{{ artifact.filename }}</strong>
                  </div>
                </div>
              </div>
              <p v-if="taskGroup.hiddenCount > 0" class="artifact-more">
                {{ t('workflow.artifacts.moreArtifacts', { count: taskGroup.hiddenCount }) }}
              </p>
            </article>
          </div>
          <a-empty v-else :description="t('workflow.artifacts.emptyRecent')" />
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useRouter } from 'vue-router'
  import dayjs from 'dayjs'
  import { useI18n } from 'vue-i18n'
  import { useArtifactsStore, useUserStore, useWorkflowStore } from '@/stores'
  import type { ArtifactFile, WorkbenchGroup } from '@/types/models'

  const ARTIFACT_TASK_GROUP_LIMIT = 4
  const ARTIFACT_TASK_PREVIEW_LIMIT = 3

  interface ArtifactTaskGroup {
    taskId: string
    toolName: string
    latestCreatedAt: string
    artifacts: ArtifactFile[]
    visibleArtifacts: ArtifactFile[]
    hiddenCount: number
  }

  const props = defineProps<{
    group?: WorkbenchGroup | null
    selectedToolSlug?: string | null
  }>()

  const { t } = useI18n()
  const router = useRouter()
  const artifactsStore = useArtifactsStore()
  const userStore = useUserStore()
  const workflowStore = useWorkflowStore()

  const currentGroupToolSlugs = computed(() => {
    return new Set((props.group?.tools ?? []).map((tool) => tool.slug))
  })

  const sortedArtifacts = computed(() => {
    return [...artifactsStore.items].sort((left, right) => {
      return Date.parse(right.created_at) - Date.parse(left.created_at)
    })
  })

  const currentGroupArtifacts = computed(() => {
    if (currentGroupToolSlugs.value.size === 0) {
      return []
    }

    return sortedArtifacts.value
      .filter((artifact) => currentGroupToolSlugs.value.has(artifact.tool_slug))
  })

  const currentGroupTaskGroups = computed(() => {
    return groupArtifactsByTask(currentGroupArtifacts.value).slice(0, ARTIFACT_TASK_GROUP_LIMIT)
  })

  const recentTaskGroups = computed(() => {
    return groupArtifactsByTask(sortedArtifacts.value).slice(0, ARTIFACT_TASK_GROUP_LIMIT)
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

  function groupArtifactsByTask(artifacts: ArtifactFile[]): ArtifactTaskGroup[] {
    const taskMap = new Map<string, ArtifactFile[]>()

    for (const artifact of artifacts) {
      const taskArtifacts = taskMap.get(artifact.task_id) ?? []
      taskArtifacts.push(artifact)
      taskMap.set(artifact.task_id, taskArtifacts)
    }

    return Array.from(taskMap.entries()).map(([taskId, taskArtifacts]) => {
      const sortedTaskArtifacts = [...taskArtifacts].sort((left, right) => {
        return Date.parse(right.created_at) - Date.parse(left.created_at)
      })
      const latestArtifact = sortedTaskArtifacts[0]
      const visibleArtifacts = sortedTaskArtifacts.slice(0, ARTIFACT_TASK_PREVIEW_LIMIT)

      return {
        taskId,
        toolName: latestArtifact?.tool_name ?? '-',
        latestCreatedAt: latestArtifact?.created_at ?? '',
        artifacts: sortedTaskArtifacts,
        visibleArtifacts,
        hiddenCount: Math.max(sortedTaskArtifacts.length - visibleArtifacts.length, 0)
      }
    })
  }

  function formatDateTime(value: string): string {
    return dayjs(value).format('YYYY-MM-DD HH:mm:ss')
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-column {
    min-width: 0;
  }

  .column-card {
    .card();
    height: 100%;
    border-color: #e8edf5;

    @media (min-width: @screen-md) {
      position: sticky;
      top: @spacing-lg;
      max-height: calc(100vh - 112px);
      overflow-y: auto;
    }
  }

  .column-header {
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

  .artifact-list,
  .artifact-task-list,
  .task-summary-card {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .artifact-task-card {
    display: flex;
    flex-direction: column;
    gap: @spacing-md;
    padding: @spacing-lg;
    border: 1px solid #e8edf5;
    border-radius: @border-radius-md;
    background: linear-gradient(180deg, #fff 0%, #fbfdff 100%);
    box-shadow: 0 8px 20px rgb(15 23 42 / 4%);
  }

  .artifact-task-header {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: @spacing-md;
    align-items: start;
  }

  .artifact-task-main {
    min-width: 0;
  }

  .artifact-task-kicker {
    display: block;
    margin-bottom: @spacing-xs;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: @line-height-base;
  }

  .artifact-task-id {
    display: block;
    padding: @spacing-xs @spacing-sm;
    border: 1px solid #e8edf5;
    border-radius: @border-radius-sm;
    background: #f8fafc;
    color: @text-color-light-primary;
    font-family: @font-family-mono;
    font-size: @font-size-xs;
    line-height: @line-height-base;
    overflow-wrap: anywhere;
  }

  .artifact-task-meta-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: @spacing-sm;
  }

  .artifact-task-meta-item {
    min-width: 0;
    padding: @spacing-sm @spacing-md;
    border: 1px solid #eef2f7;
    border-radius: @border-radius-md;
    background: #f8fafc;
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

  .task-summary-row {
    display: flex;
    justify-content: space-between;
    gap: @spacing-sm;
    align-items: flex-start;
  }

  .artifact-item {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: @spacing-sm;
    align-items: start;
    padding: @spacing-sm;
    border: 1px solid #eef2f7;
    border-radius: @border-radius-md;
    background: #fff;
  }

  .artifact-list-compact {
    gap: @spacing-xs;

    .artifact-item {
      grid-template-columns: minmax(0, 1fr);
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

  .artifact-task-count {
    margin-inline-end: 0;
    white-space: nowrap;
  }

  .artifact-more {
    margin: @spacing-xs 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    line-height: @line-height-base;
  }

  .task-summary-card {
    border: 1px solid @border-color-light;
    border-radius: @border-radius-md;
    padding: @spacing-md;
    background: @bg-card-light;
  }

  .task-summary-value {
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    text-align: right;
    overflow-wrap: anywhere;
  }

  @media (max-width: @screen-sm) {
    .column-header,
    .artifact-item,
    .artifact-task-header,
    .artifact-task-meta-grid {
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
