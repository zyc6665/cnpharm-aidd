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
          <div v-if="currentGroupArtifacts.length > 0" class="artifact-list">
            <div v-for="artifact in currentGroupArtifacts" :key="artifact.id" class="artifact-item">
              <div class="artifact-copy">
                <strong class="artifact-name">{{ artifact.filename }}</strong>
                <p class="artifact-meta">
                  {{ t('workflow.artifacts.sourceTool', { tool: artifact.tool_name }) }}
                </p>
                <p class="artifact-meta">
                  {{ t('workflow.artifacts.generatedAt', { time: formatDateTime(artifact.created_at) }) }}
                </p>
              </div>
              <a-button type="link" size="small" @click="openTaskDetail(artifact.task_id)">
                {{ t('workflow.currentTool.viewTask') }}
              </a-button>
            </div>
          </div>
          <a-empty v-else :description="t('workflow.artifacts.emptyCurrentGroup')" />
        </div>

        <div class="artifact-group">
          <h3 class="artifact-group-title">{{ t('workflow.artifacts.recentGroup') }}</h3>
          <div v-if="recentArtifacts.length > 0" class="artifact-list">
            <div v-for="artifact in recentArtifacts" :key="artifact.id" class="artifact-item">
              <div class="artifact-copy">
                <strong class="artifact-name">{{ artifact.filename }}</strong>
                <p class="artifact-meta">
                  {{ t('workflow.artifacts.sourceTool', { tool: artifact.tool_name }) }}
                </p>
                <p class="artifact-meta">
                  {{ t('workflow.artifacts.generatedAt', { time: formatDateTime(artifact.created_at) }) }}
                </p>
              </div>
              <a-button type="link" size="small" @click="openTaskDetail(artifact.task_id)">
                {{ t('workflow.currentTool.viewTask') }}
              </a-button>
            </div>
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
  import type { WorkbenchGroup } from '@/types/models'

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
      .slice(0, 8)
  })

  const recentArtifacts = computed(() => sortedArtifacts.value.slice(0, 8))

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
  .task-summary-card {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .artifact-item,
  .task-summary-row {
    display: flex;
    justify-content: space-between;
    gap: @spacing-sm;
    align-items: flex-start;
  }

  .artifact-copy {
    min-width: 0;
  }

  .artifact-name {
    display: block;
    font-size: @font-size-sm;
    margin-bottom: @spacing-xs;
  }

  .artifact-meta,
  .task-summary-label {
    margin: 0;
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
    color: @text-color-primary;
    font-size: @font-size-sm;
    text-align: right;
  }
</style>
