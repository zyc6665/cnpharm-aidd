<template>
  <div v-if="projects.length" class="project-list">
    <router-link
      v-for="project in projects"
      :key="project.id"
      :to="`/projects/${project.id}`"
      class="project-row"
    >
      <div class="project-main">
        <strong>{{ project.name }}</strong>
        <span>{{ project.goal || t('workspace.project.noGoal') }}</span>
      </div>
      <div class="project-meta">
        <span class="project-status" :class="`status-${project.status}`">
          {{ t(`workspace.project.status.${project.status}`) }}
        </span>
        <time :datetime="project.updated_at">{{ formatUpdatedAt(project.updated_at) }}</time>
        <span class="project-actions">
          <span class="continue-action">{{ t('workspace.openProject') }}</span>
          <a-button
            v-if="canArchive(project)"
            type="link"
            size="small"
            class="project-action"
            @click="handleAction('archive', project.id, $event)"
          >
            {{ t('workspace.project.archive') }}
          </a-button>
          <!-- 已归档项目必须在这里就能撤销：默认列表不显示归档项目，
               如果只把入口放在详情页，用户得先「猜」到能点进去才找得到。 -->
          <a-button
            v-if="canUnarchive(project)"
            type="link"
            size="small"
            class="project-action"
            data-testid="project-unarchive-button"
            @click="handleAction('unarchive', project.id, $event)"
          >
            {{ t('workspace.project.unarchive') }}
          </a-button>
          <span v-if="canDelete(project)" @click.prevent.stop>
            <a-popconfirm
              :title="t('workspace.project.deleteConfirm')"
              :ok-text="t('common.delete')"
              :cancel-text="t('common.cancel')"
              ok-type="danger"
              @confirm="emit('delete', project.id)"
            >
              <a-button
                type="link"
                size="small"
                danger
                class="project-action"
              >
                {{ t('common.delete') }}
              </a-button>
            </a-popconfirm>
          </span>
        </span>
      </div>
    </router-link>
  </div>
  <AppEmptyState
    v-else
    :title="t('workspace.emptyProjects')"
    :description="t('workspace.emptyProjectsHint')"
  />
</template>

<script setup lang="ts">
import { formatDateTimeMinutes } from '@/utils/datetime'
import { useI18n } from 'vue-i18n'
import AppEmptyState from '@/components/common/AppEmptyState.vue'
import type { ResearchProject } from '@/types/projects'

defineProps<{ projects: ResearchProject[] }>()
const emit = defineEmits<{
  archive: [projectId: string]
  unarchive: [projectId: string]
  delete: [projectId: string]
}>()

const { t } = useI18n()
const formatUpdatedAt = (value: string) => formatDateTimeMinutes(value)
const canManage = (project: ResearchProject) =>
  ['owner', 'editor', 'admin'].includes(project.role)
const canArchive = (project: ResearchProject) =>
  project.status !== 'archived' && canManage(project)
const canUnarchive = (project: ResearchProject) =>
  project.status === 'archived' && canManage(project)
const canDelete = (project: ResearchProject) => ['owner', 'admin'].includes(project.role)

function stopAction(event?: Event) {
  event?.preventDefault()
  event?.stopPropagation()
}

function handleAction(
  action: 'archive' | 'unarchive',
  projectId: string,
  event?: Event
) {
  stopAction(event)
  if (action === 'archive') {
    emit('archive', projectId)
  } else {
    emit('unarchive', projectId)
  }
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.project-list { border-top: 1px solid @border-color; }
.project-row { display: flex; align-items: center; justify-content: space-between; gap: @spacing-lg; min-height: 72px; padding: @spacing-md @spacing-sm; color: inherit; border-bottom: 1px solid @border-color; transition: background @transition-fast; }
.project-row:hover { background: @bg-hover; }
.project-main { min-width: 0; }
.project-main strong, .project-main span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.project-main strong { color: @text-primary; font-size: @font-size-md; }
.project-main span { margin-top: @spacing-xs; color: @text-tertiary; font-size: @font-size-sm; }
.project-meta { display: grid; grid-template-columns: 72px 126px minmax(168px, auto); align-items: center; gap: @spacing-sm; color: @text-tertiary; font-size: @font-size-xs; text-align: right; }
.project-status { justify-self: end; color: @text-secondary; }
.status-active { color: @success-color; }
.status-frozen { color: @warning-color; }
.status-completed { color: @accent-color; }
.status-archived { color: @text-disabled; }
.project-actions { display: inline-flex; align-items: center; justify-content: flex-end; gap: @spacing-xs; }
.continue-action { color: @accent-color; font-size: @font-size-sm; }
.project-action { height: 24px; padding: 0 4px; font-size: @font-size-xs; }

@media (max-width: @screen-sm) {
  .project-row { align-items: flex-start; }
  .project-meta { grid-template-columns: auto; }
  .project-meta time { display: none; }
  .project-actions { justify-content: flex-start; flex-wrap: wrap; }
}
</style>
