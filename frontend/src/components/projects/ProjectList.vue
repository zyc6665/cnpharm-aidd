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
            @click="handleArchive(project.id, $event)"
          >
            {{ t('workspace.project.archive') }}
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
  <div v-else class="project-empty">
    <FolderOpenOutlined />
    <p>{{ t('workspace.emptyProjects') }}</p>
  </div>
</template>

<script setup lang="ts">
import dayjs from 'dayjs'
import { useI18n } from 'vue-i18n'
import { FolderOpenOutlined } from '@ant-design/icons-vue'
import type { ResearchProject } from '@/types/projects'

defineProps<{ projects: ResearchProject[] }>()
const emit = defineEmits<{
  archive: [projectId: string]
  delete: [projectId: string]
}>()

const { t } = useI18n()
const formatUpdatedAt = (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm')
const canArchive = (project: ResearchProject) =>
  project.status !== 'archived' && ['owner', 'editor'].includes(project.membership.role)
const canDelete = (project: ResearchProject) => project.membership.role === 'owner'

function stopAction(event?: Event) {
  event?.preventDefault()
  event?.stopPropagation()
}

function handleArchive(projectId: string, event?: Event) {
  stopAction(event)
  emit('archive', projectId)
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
.project-empty { padding: @spacing-xxl @spacing-md; color: @text-tertiary; text-align: center; }
.project-empty :deep(.anticon) { font-size: 30px; }
.project-empty p { margin: @spacing-sm 0 @spacing-xs; color: @text-secondary; }

@media (max-width: @screen-sm) {
  .project-row { align-items: flex-start; }
  .project-meta { grid-template-columns: auto; }
  .project-meta time { display: none; }
  .project-actions { justify-content: flex-start; flex-wrap: wrap; }
}
</style>
