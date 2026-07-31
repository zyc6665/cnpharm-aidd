<template>
  <main class="workspace-page">
    <header class="workspace-header">
      <div>
        <h1>{{ t('workspace.researchTitle') }}</h1>
      </div>
      <a-button type="primary" @click="createDialogOpen = true">
        <PlusOutlined />
        {{ t('workspace.createProject') }}
      </a-button>
    </header>

    <a-alert
      v-if="loadError"
      class="workspace-error"
      type="error"
      show-icon
      :message="t('workspace.loadFailed')"
      :description="t('workspace.loadFailedHint')"
    >
      <template #action>
        <a-button size="small" :loading="loading" @click="loadWorkspace">
          {{ t('workspace.retry') }}
        </a-button>
      </template>
    </a-alert>

    <a-skeleton v-if="loading && !hasLoaded" active :paragraph="{ rows: 10 }" />
    <template v-else-if="!loadError">
      <section class="workspace-section projects-section">
        <div class="section-heading">
          <div>
            <h2>{{ t('workspace.recentProjects') }}</h2>
            <span>{{ t('workspace.projectCount', { count: projects.length }) }}</span>
          </div>
        </div>
        <ProjectList
          :projects="recentProjects"
          @archive="handleProjectArchive"
          @delete="handleProjectDelete"
        />
      </section>

      <div class="workspace-columns">
        <section class="workspace-section">
          <div class="section-heading">
            <div>
              <h2>{{ t('workspace.attentionTitle') }}</h2>
            </div>
            <router-link to="/tasks">{{ t('common.more') }}</router-link>
          </div>

          <div v-if="attentionTasks.length" class="status-list">
            <router-link
              v-for="task in attentionTasks"
              :key="task.id"
              :to="`/tasks/${task.id}`"
              class="status-row"
            >
              <span class="status-marker" :class="`status-${task.status}`"></span>
              <div>
                <strong>{{ task.name || task.tool_name || task.id }}</strong>
                <span>{{ task.error_message || taskLabel(task.status) }}</span>
              </div>
              <time :datetime="task.updated_at">{{ formatTime(task.updated_at) }}</time>
            </router-link>
          </div>
          <a-empty v-else :description="t('workspace.emptyAttention')" />
        </section>

        <section class="workspace-section">
          <div class="section-heading">
            <div>
              <h2>{{ t('workspace.recentArtifacts') }}</h2>
            </div>
          </div>

          <div v-if="recentArtifacts.length" class="artifact-list">
            <a
              v-for="artifact in recentArtifacts"
              :key="artifact.id"
              :href="`/api/v1/files/${artifact.id}/download`"
              class="artifact-row"
            >
              <FileOutlined />
              <div>
                <strong>{{ artifact.filename }}</strong>
                <span>{{ artifact.content_type || t('workspace.unknownArtifactType') }}</span>
              </div>
              <small>{{ formatSize(artifact.size_bytes) }}</small>
            </a>
          </div>
          <a-empty v-else :description="t('workspace.emptyArtifacts')" />
        </section>
      </div>
    </template>

    <ProjectCreateDialog
      v-model:open="createDialogOpen"
      @created="handleProjectCreated"
    />
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { FileOutlined, PlusOutlined } from '@ant-design/icons-vue'
import {
  archiveProject as archiveProjectApi,
  deleteProject as deleteProjectApi,
  listProjects
} from '@/api/projects'
import {
  getWorkspaceOverview,
  type WorkspaceArtifact,
  type WorkspaceAttentionTask
} from '@/api/workspace'
import ProjectCreateDialog from '@/components/projects/ProjectCreateDialog.vue'
import ProjectList from '@/components/projects/ProjectList.vue'
import type { ResearchProject } from '@/types/projects'

const { t } = useI18n()
const router = useRouter()
const loading = ref(false)
const hasLoaded = ref(false)
const loadError = ref(false)
const createDialogOpen = ref(false)
const projects = ref<ResearchProject[]>([])
const tasks = ref<WorkspaceAttentionTask[]>([])
const artifacts = ref<WorkspaceArtifact[]>([])

const recentProjects = computed(() => projects.value.slice(0, 8))
const attentionTasks = computed(() =>
  tasks.value.filter(task => task.status === 'pending' || task.status === 'failure').slice(0, 6)
)
const recentArtifacts = computed(() => artifacts.value.slice(0, 6))

async function loadWorkspace() {
  if (loading.value) return
  loading.value = true
  loadError.value = false
  try {
    const [projectResponse, workspaceResponse] = await Promise.all([
      listProjects(),
      getWorkspaceOverview()
    ])
    projects.value = projectResponse.data.items
    tasks.value = workspaceResponse.data.tasks
    artifacts.value = workspaceResponse.data.files
    hasLoaded.value = true
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function handleProjectCreated(project: ResearchProject) {
  projects.value = [project, ...projects.value.filter(item => item.id !== project.id)]
  void router.push(`/projects/${project.id}/research`)
}

async function handleProjectArchive(projectId: string) {
  const previousProjects = projects.value
  projects.value = projects.value.filter(project => project.id !== projectId)
  try {
    await archiveProjectApi(projectId)
    message.success(t('workspace.project.archiveSuccess'))
  } catch {
    projects.value = previousProjects
    message.error(t('workspace.project.archiveFailed'))
  }
}

async function handleProjectDelete(projectId: string) {
  const previousProjects = projects.value
  projects.value = projects.value.filter(project => project.id !== projectId)
  try {
    await deleteProjectApi(projectId)
    message.success(t('workspace.project.deleteSuccess'))
  } catch {
    projects.value = previousProjects
    message.error(t('workspace.project.deleteFailed'))
  }
}

const taskLabel = (status: WorkspaceAttentionTask['status']) =>
  status === 'pending' ? t('workspace.pendingApproval') : t('workspace.taskNeedsAttention')
const formatTime = (value: string) => dayjs(value).format('MM-DD HH:mm')
const formatSize = (bytes: number) =>
  bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`

onMounted(() => { void loadWorkspace() })
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.workspace-page { max-width: 1180px; margin: 0 auto; padding: @spacing-xl @spacing-lg @spacing-xxl; }
.workspace-header { display: flex; align-items: flex-start; justify-content: space-between; gap: @spacing-lg; margin-bottom: @spacing-xl; }
.workspace-header h1 { margin: 0; color: @text-primary; font-size: @font-size-xxl; line-height: @line-height-tight; letter-spacing: 0; }
.workspace-error { margin-bottom: @spacing-lg; }
.workspace-section { min-width: 0; padding: 0 0 @spacing-xl; }
.projects-section { margin-bottom: @spacing-xl; border-bottom: 1px solid @border-color; }
.workspace-columns { display: grid; grid-template-columns: minmax(0, 3fr) minmax(280px, 2fr); gap: @spacing-xxl; }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; min-height: 40px; margin-bottom: @spacing-md; }
.section-heading h2 { margin: 0; color: @text-primary; font-size: @font-size-md; letter-spacing: 0; }
.section-heading span { display: block; margin-top: 2px; color: @text-tertiary; font-size: @font-size-xs; }
.section-heading a { color: @text-tertiary; font-size: @font-size-sm; }
.status-list, .artifact-list { border-top: 1px solid @border-color; }
.status-row, .artifact-row { display: grid; align-items: center; gap: @spacing-sm; min-height: 58px; padding: @spacing-sm; color: inherit; border-bottom: 1px solid @border-color; transition: background @transition-fast; }
.status-row { grid-template-columns: auto minmax(0, 1fr) auto; }
.artifact-row { grid-template-columns: auto minmax(0, 1fr) auto; }
.status-row:hover, .artifact-row:hover { background: @bg-hover; }
.status-marker { width: 8px; height: 8px; border-radius: 50%; background: @text-disabled; }
.status-pending { background: @warning-color; }
.status-failure { background: @error-color; }
.status-row strong, .status-row span, .artifact-row strong, .artifact-row span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.status-row strong, .artifact-row strong { color: @text-primary; font-size: @font-size-sm; }
.status-row span, .artifact-row span, .status-row time, .artifact-row small { color: @text-tertiary; font-size: @font-size-xs; }
.status-row time { white-space: nowrap; }
.artifact-row :deep(.anticon) { color: @accent-color; font-size: @font-size-lg; }

@media (max-width: @screen-md) {
  .workspace-columns { grid-template-columns: 1fr; gap: @spacing-lg; }
}
@media (max-width: @screen-sm) {
  .workspace-page { padding: @spacing-lg @spacing-md; }
  .workspace-header { align-items: stretch; flex-direction: column; }
  .workspace-header :deep(.ant-btn) { width: 100%; }
  .status-row time { display: none; }
}
</style>
