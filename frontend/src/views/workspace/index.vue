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

    <a-alert
      v-if="overviewLoadError && !loadError"
      class="workspace-error"
      type="warning"
      show-icon
      :message="t('workspace.overviewLoadFailed')"
      :description="t('workspace.overviewLoadFailedHint')"
    >
      <template #action>
        <a-button size="small" :loading="loading" @click="loadWorkspace">
          {{ t('workspace.retry') }}
        </a-button>
      </template>
    </a-alert>

    <a-alert
      v-if="schemaMigrationLoadError && !loadError"
      class="workspace-error"
      type="error"
      show-icon
      :message="t('workspace.schemaMigrationLoadFailed')"
      :description="t('workspace.schemaMigrationLoadFailedHint')"
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
            <span>{{ t('workspace.projectCount', { count: activeProjects.length }) }}</span>
          </div>
        </div>
        <ProjectList
          v-if="recentProjects.length"
          :projects="recentProjects"
          @archive="handleProjectArchive"
          @delete="handleProjectDelete"
        />
        <!-- 全部项目都被归档时，不能再说「还没有研究项目」——项目明明在下面躺着。 -->
        <p v-else-if="archivedProjects.length" class="projects-empty-hint">
          {{ t('workspace.noActiveProjects') }}
        </p>
        <ProjectList
          v-else
          :projects="[]"
        />
      </section>

      <!-- 已归档项目单独成段：归档是「收起来」不是「删掉」，
           所以既要从常用列表里移走，又必须留一条能点进去看、能撤销归档的路。 -->
      <section
        v-if="archivedProjects.length"
        class="workspace-section projects-section"
        data-testid="workspace-archived-projects"
      >
        <div class="section-heading">
          <div>
            <h2>{{ t('workspace.archivedProjects') }}</h2>
            <span>{{ t('workspace.archivedProjectsHint') }}</span>
          </div>
        </div>
        <ProjectList
          :projects="archivedProjects"
          @unarchive="handleProjectUnarchive"
          @delete="handleProjectDelete"
        />
      </section>

      <!-- 待办概览：把「有什么在等我」变成一屏可见，不用分别去任务中心/结果中心翻 -->
      <section class="workspace-section todo-section" data-testid="workspace-todo">
        <div class="section-heading">
          <div>
            <h2>{{ t('workspace.todoTitle') }}</h2>
            <span>{{ t('workspace.todoHint') }}</span>
          </div>
        </div>
        <div class="todo-cards">
          <router-link
            v-for="card in todoCards"
            :key="card.key"
            class="todo-card"
            :class="`todo-${card.tone}`"
            :to="card.to"
            :data-testid="`workspace-todo-${card.key}`"
          >
            <span class="todo-label">{{ t(card.labelKey) }}</span>
            <strong class="todo-value">{{ card.value }}</strong>
            <span class="todo-desc">{{ t(card.hintKey) }}</span>
          </router-link>
        </div>
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
          <AppEmptyState
            v-else
            :title="t('workspace.emptyAttention')"
            :description="t('workspace.emptyAttentionHint')"
          />
        </section>

        <section class="workspace-section">
          <div class="section-heading">
            <div>
              <h2>{{ t('workspace.recentArtifacts') }}</h2>
            </div>
          </div>

          <div v-if="recentArtifacts.length" class="artifact-list">
            <button
              v-for="artifact in recentArtifacts"
              :key="artifact.id"
              type="button"
              class="artifact-row"
              data-testid="recent-artifact-row"
              @click="openArtifactPreview(artifact)"
            >
              <FileOutlined />
              <div class="artifact-main">
                <strong :title="artifact.title">{{ artifact.title }}</strong>
                <span class="artifact-meta">
                  <em class="artifact-type">{{ artifact.typeLabel }}</em>
                  <span
                    v-if="artifact.fileName"
                    class="artifact-file mono-cell"
                    :title="artifact.fileName"
                  >{{ artifact.fileName }}</span>
                  <span>{{ formatSize(artifact.sizeBytes) }}</span>
                </span>
              </div>
              <time>{{ formatTime(artifact.updatedAt) }}</time>
            </button>
          </div>
          <AppEmptyState
            v-else
            :title="t('workspace.emptyArtifacts')"
            :description="t('workspace.emptyArtifactsHint')"
          />
        </section>
      </div>
    </template>

    <ProjectCreateDialog
      v-model:open="createDialogOpen"
      @created="handleProjectCreated"
    />

    <WorkspaceArtifactPreview
      v-model:open="previewOpen"
      :row="previewRow"
      :artifact="previewArtifact"
      :legacy-file="previewLegacyFile"
    />
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { FileOutlined, PlusOutlined } from '@ant-design/icons-vue'
import {
  archiveProject as archiveProjectApi,
  deleteProject as deleteProjectApi,
  listProjects,
  unarchiveProject as unarchiveProjectApi
} from '@/api/projects'
import {
  getWorkspaceOverview,
  type WorkspaceArtifact,
  type WorkspaceAttentionTask,
  type WorkspaceLegacyFile
} from '@/api/workspace'
import { buildArtifactVersionDownloadUrl } from '@/api/artifacts'
import { getSystemHealth } from '@/api/system'
import { getTaskCounts } from '@/api/tasks'
import ProjectCreateDialog from '@/components/projects/ProjectCreateDialog.vue'
import AppEmptyState from '@/components/common/AppEmptyState.vue'
import ProjectList from '@/components/projects/ProjectList.vue'
import WorkspaceArtifactPreview from '@/components/workspace/WorkspaceArtifactPreview.vue'
import {
  buildRecentWorkspaceArtifactRows,
  formatWorkspaceFileSize,
  formatWorkspaceTime,
  getRecentWorkspaceProjects,
  getWorkspaceAttentionTasks,
  getWorkspaceTaskLabelKey,
  hasWorkspaceSchemaMigrationHealthIssue,
  partitionWorkspaceProjects,
  type RecentWorkspaceArtifactRow
} from '@/domain/workspace'
import type { ResearchProject } from '@/types/projects'

const { t } = useI18n()
const router = useRouter()
const loading = ref(false)
const hasLoaded = ref(false)
const loadError = ref(false)
const overviewLoadError = ref(false)
const schemaMigrationLoadError = ref(false)
const createDialogOpen = ref(false)
const projects = ref<ResearchProject[]>([])
const tasks = ref<WorkspaceAttentionTask[]>([])
const artifacts = ref<WorkspaceArtifact[]>([])
const legacyFiles = ref<WorkspaceLegacyFile[]>([])
// 最近 Artifact 预览抽屉：记录被点击的行，并反查它对应的标准 artifact / 传统文件。
const previewOpen = ref(false)
const previewRow = ref<RecentWorkspaceArtifactRow | null>(null)
const previewArtifact = ref<WorkspaceArtifact | null>(null)
const previewLegacyFile = ref<WorkspaceLegacyFile | null>(null)
// 待办计数：来自任务系统视图的口径（running / needs_attention / recent_results），
// 与任务中心的页签一一对应，点进去就能看到同一批记录。
const todoCounts = ref<{ running: number; needs_attention: number; recent_results: number } | null>(null)

const projectGroups = computed(() => partitionWorkspaceProjects(projects.value))
const activeProjects = computed(() => projectGroups.value.active)
const archivedProjects = computed(() => projectGroups.value.archived)
const recentProjects = computed(() => getRecentWorkspaceProjects(activeProjects.value))
const attentionTasks = computed(() => getWorkspaceAttentionTasks(tasks.value))

const todoCards = computed(() => {
  const counts = todoCounts.value
  return [
    {
      key: 'running',
      labelKey: 'workspace.todo.running',
      hintKey: 'workspace.todo.runningHint',
      to: '/tasks?view=running',
      tone: 'running',
      value: counts ? counts.running : '-'
    },
    {
      key: 'attention',
      labelKey: 'workspace.todo.attention',
      hintKey: 'workspace.todo.attentionHint',
      to: '/tasks?view=needs_attention',
      tone: 'attention',
      value: counts ? counts.needs_attention : '-'
    },
    {
      key: 'results',
      labelKey: 'workspace.todo.results',
      hintKey: 'workspace.todo.resultsHint',
      to: '/tasks?view=recent_results',
      tone: 'results',
      value: counts ? counts.recent_results : '-'
    }
  ]
})
const recentArtifacts = computed<RecentWorkspaceArtifactRow[]>(() =>
  buildRecentWorkspaceArtifactRows({
    artifacts: artifacts.value,
    legacyFiles: legacyFiles.value,
    unknownArtifactTypeLabel: t('workspace.unknownArtifactType'),
    buildArtifactDownloadUrl: buildArtifactVersionDownloadUrl,
    translate: t
  })
)

async function loadWorkspace() {
  if (loading.value) return
  loading.value = true
  loadError.value = false
  overviewLoadError.value = false
  schemaMigrationLoadError.value = false
  try {
    const [projectResult, workspaceResult, countResult] = await Promise.allSettled([
      listProjects({ includeArchived: true }),
      getWorkspaceOverview(),
      getTaskCounts()
    ])
    const countData = countResult.status === 'fulfilled' ? countResult.value?.data : null
    todoCounts.value = countData
      ? {
          running: countData.running ?? 0,
          needs_attention: countData.needs_attention ?? 0,
          recent_results: countData.recent_results ?? 0
        }
      : null

    if (projectResult.status === 'rejected') {
      loadError.value = true
      return
    }

    projects.value = projectResult.value.data.items
    if (workspaceResult.status === 'fulfilled') {
      tasks.value = workspaceResult.value.data.tasks
      artifacts.value = workspaceResult.value.data.artifacts ?? []
      legacyFiles.value = workspaceResult.value.data.files
    } else {
      tasks.value = []
      artifacts.value = []
      legacyFiles.value = []
      schemaMigrationLoadError.value = await hasDatabaseSchemaHealthIssue()
      overviewLoadError.value = !schemaMigrationLoadError.value
    }
    hasLoaded.value = true
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

async function hasDatabaseSchemaHealthIssue() {
  try {
    const health = await getSystemHealth({ silent: true, retry: 0 })
    return hasWorkspaceSchemaMigrationHealthIssue(health.data.services)
  } catch {
    return false
  }
}

function openArtifactPreview(row: RecentWorkspaceArtifactRow) {
  previewRow.value = row
  previewArtifact.value = artifacts.value.find(item => item.id === row.id) ?? null
  previewLegacyFile.value = previewArtifact.value
    ? null
    : legacyFiles.value.find(item => item.id === row.id) ?? null
  previewOpen.value = true
}

function handleProjectCreated(project: ResearchProject) {
  projects.value = [project, ...projects.value.filter(item => item.id !== project.id)]
  void router.push(`/projects/${project.id}`)
}

async function handleProjectArchive(projectId: string) {
  const previousProjects = projects.value
  // 归档不是删除：项目仍然存在，只是从「在用」列表挪到「已归档」。
  // 直接把它从数组里删掉会让用户以为数据没了，也让「撤销归档」无处可点。
  projects.value = projects.value.map(project =>
    project.id === projectId ? { ...project, status: 'archived' } : project
  )
  try {
    await archiveProjectApi(projectId)
    message.success(t('workspace.project.archiveSuccess'))
  } catch {
    projects.value = previousProjects
    message.error(t('workspace.project.archiveFailed'))
  }
}

async function handleProjectUnarchive(projectId: string) {
  const previousProjects = projects.value
  projects.value = projects.value.map(project =>
    project.id === projectId ? { ...project, status: 'active' } : project
  )
  try {
    await unarchiveProjectApi(projectId)
    message.success(t('workspace.project.unarchiveSuccess'))
  } catch {
    projects.value = previousProjects
    message.error(t('workspace.project.unarchiveFailed'))
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
  t(getWorkspaceTaskLabelKey(status))
const formatTime = formatWorkspaceTime
const formatSize = formatWorkspaceFileSize

onMounted(() => { void loadWorkspace() })
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.workspace-page { max-width: 1180px; margin: 0 auto; padding: @spacing-xl @spacing-lg @spacing-xxl; }
.workspace-header { display: flex; align-items: flex-start; justify-content: space-between; gap: @spacing-lg; margin-bottom: @spacing-xl; }
.workspace-header h1 { margin: 0; color: @text-primary; font-size: @font-size-xxl; line-height: @line-height-tight; letter-spacing: 0; }
.workspace-error { margin-bottom: @spacing-lg; }
.workspace-section { min-width: 0; padding: 0 0 @spacing-xl; }

.todo-section { margin-bottom: @spacing-lg; }

.todo-cards {
  display: grid;
  gap: @spacing-md;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
}

.todo-card {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: @spacing-md @spacing-lg;
  border: 1px solid @border-color;
  border-radius: @border-radius-md;
  background: @bg-surface;
  color: inherit;
  text-decoration: none;
  transition: border-color 0.2s, box-shadow 0.2s;

  &:hover {
    border-color: @primary-color;
    box-shadow: 0 2px 8px rgb(0 0 0 / 8%);
  }
}

.todo-label { color: @text-secondary; font-size: @font-size-sm; }
.todo-value { color: @text-primary; font-size: 26px; font-weight: 600; line-height: 1.3; }
.todo-desc { color: @text-tertiary; font-size: @font-size-xs; }
.todo-attention .todo-value { color: @error-color; }
.todo-running .todo-value { color: @primary-color; }
.projects-section { margin-bottom: @spacing-xl; border-bottom: 1px solid @border-color; }
.projects-empty-hint { margin: 0; padding: @spacing-md @spacing-sm; color: @text-tertiary; font-size: @font-size-sm; }
.workspace-columns { display: grid; grid-template-columns: minmax(0, 3fr) minmax(280px, 2fr); gap: @spacing-xxl; }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; min-height: 40px; margin-bottom: @spacing-md; }
.section-heading h2 { margin: 0; color: @text-primary; font-size: @font-size-md; letter-spacing: 0; }
.section-heading span { display: block; margin-top: 2px; color: @text-tertiary; font-size: @font-size-xs; }
.section-heading a { color: @text-tertiary; font-size: @font-size-sm; }
.status-list, .artifact-list { border-top: 1px solid @border-color; }
.status-row, .artifact-row { display: grid; align-items: center; gap: @spacing-sm; min-height: 58px; padding: @spacing-sm; color: inherit; border-bottom: 1px solid @border-color; transition: background @transition-fast; }
.status-row { grid-template-columns: auto minmax(0, 1fr) auto; }
.artifact-row {
  grid-template-columns: auto minmax(0, 1fr) auto;
  width: 100%;
  border: none;
  border-bottom: 1px solid @border-color;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.artifact-row:focus-visible {
  outline: 2px solid @primary-color;
  outline-offset: -2px;
}
.status-row:hover, .artifact-row:hover { background: @bg-hover; }
.status-marker { width: 8px; height: 8px; border-radius: 50%; background: @text-disabled; }
.status-pending { background: @warning-color; }
.status-failure { background: @error-color; }
.status-row strong, .status-row span, .artifact-row strong, .artifact-row span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.status-row strong, .artifact-row strong { color: @text-primary; font-size: @font-size-sm; }
.status-row span, .artifact-row span, .status-row time, .artifact-row small { color: @text-tertiary; font-size: @font-size-xs; }
.status-row time { white-space: nowrap; }
.artifact-row :deep(.anticon) { color: @accent-color; font-size: @font-size-lg; }
.artifact-main { min-width: 0; }
.artifact-meta { display: flex; align-items: center; gap: @spacing-xs; min-width: 0; }
.artifact-type { flex: none; padding: 0 6px; border-radius: 9px; background: @bg-hover; color: @accent-color; font-style: normal; line-height: 18px; }
.artifact-file { min-width: 0; font-family: @font-family-mono; }
.artifact-row time { color: @text-tertiary; font-size: @font-size-xs; white-space: nowrap; }

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
