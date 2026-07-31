<template>
  <div v-if="projects.length" class="project-list">
    <router-link
      v-for="project in projects"
      :key="project.id"
      :to="`/projects/${project.id}/research`"
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
        <span class="continue-action">{{ t('workspace.continueResearch') }}</span>
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

const { t } = useI18n()
const formatUpdatedAt = (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm')
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
.project-meta { display: grid; grid-template-columns: 72px 126px 80px; align-items: center; gap: @spacing-sm; color: @text-tertiary; font-size: @font-size-xs; text-align: right; }
.project-status { justify-self: end; color: @text-secondary; }
.status-active { color: @success-color; }
.status-frozen { color: @warning-color; }
.status-completed { color: @accent-color; }
.continue-action { color: @accent-color; font-size: @font-size-sm; }
.project-empty { padding: @spacing-xxl @spacing-md; color: @text-tertiary; text-align: center; }
.project-empty :deep(.anticon) { font-size: 30px; }
.project-empty p { margin: @spacing-sm 0 @spacing-xs; color: @text-secondary; }

@media (max-width: @screen-sm) {
  .project-row { align-items: flex-start; }
  .project-meta { grid-template-columns: auto; }
  .project-meta time { display: none; }
}
</style>
