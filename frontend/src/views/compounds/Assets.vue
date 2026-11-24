<template>
  <main class="compounds-assets-page">
    <router-link :to="`/projects/${projectId}`" class="back-link">
      {{ t('compounds.backToProject') }}
    </router-link>
    <ProjectWorkspaceNav :project-id="projectId" />
    <ProjectViewSwitcher :items="dataViewTabs" active="assets" />

    <AppPageHeader
      :title="t('compounds.dataSpaceTitle')"
      :subtitle="t('compounds.dataSpaceSubtitle')"
    >
      <template #actions>
        <a-space>
          <a-button
            type="primary"
            data-testid="assets-upload-artifact-open"
            @click="openArtifactUpload"
          >
            {{ t('compounds.dataSpaceUpload') }}
          </a-button>
          <a-button
            :loading="loading"
            data-testid="assets-refresh"
            @click="loadAll"
          >
            {{ t('compounds.actions.refresh') }}
          </a-button>
        </a-space>
      </template>
    </AppPageHeader>

    <AppInlineError
      v-if="loadError"
      class="assets-alert"
      data-testid="assets-error"
      :title="t('compounds.errors.loadAssets')"
      :description="t('common.listStates.errorDescription')"
    >
      <a-button size="small" @click="loadAll">{{ t('common.listStates.retry') }}</a-button>
    </AppInlineError>

    <SkeletonList v-if="loading && artifacts.length === 0" :count="5" />

    <AppEmptyState
      v-else-if="!loadError && artifacts.length === 0"
      :title="t('compounds.dataSpaceEmpty')"
      :description="t('compounds.dataSpaceEmptyHint')"
    >
      <a-button type="primary" @click="openArtifactUpload">{{ t('compounds.dataSpaceUpload') }}</a-button>
    </AppEmptyState>

    <section v-else class="assets-space-section" data-testid="assets-space-section">
      <!-- 项目数据空间（按每次工具调用分组成目录，避免成千上万个单分子平铺） -->
      <div class="assets-toolbar">
        <a-space wrap>
          <a-select
            v-model:value="artifactTypeFilter"
            style="width: 200px"
            allow-clear
            :placeholder="t('compounds.dataSpaceFilterPlaceholder')"
            :options="artifactFilterOptions"
          />
          <span class="assets-space-hint">
            {{ t('compounds.dataSpaceHint') }}
          </span>
        </a-space>
      </div>

      <a-spin :spinning="loading">
        <a-empty
          v-if="artifactGroups.length === 0"
          :description="t('compounds.dataSpaceEmptyHint')"
        />
        <a-collapse
          v-else
          v-model:activeKey="expandedGroupKeys"
          class="artifact-folder-list"
          data-testid="assets-artifact-folders"
        >
          <a-collapse-panel v-for="group in artifactGroups" :key="group.key">
            <template #header>
              <div class="artifact-folder-head">
                <span class="artifact-folder-title">{{ group.title }}</span>
                <a-tag>{{ group.items.length }} {{ t('compounds.dataSpaceArtifactUnit') }}</a-tag>
                <span v-if="group.createdAt" class="artifact-folder-time">
                  {{ formatDateTimeOrDash(group.createdAt) }}
                </span>
              </div>
            </template>
            <template #extra>
              <router-link
                v-if="group.taskId"
                :to="`/projects/${encodeURIComponent(projectId)}/tasks/${encodeURIComponent(group.taskId)}/result`"
                @click.stop
              >
                {{ t('compounds.dataSpaceViewResult') }}
              </router-link>
            </template>

            <a-table
              :scroll="{ x: 'max-content' }"
              :columns="artifactColumns"
              :data-source="group.items"
              :pagination="false"
              row-key="id"
              size="small"
              data-testid="assets-artifact-table"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'artifact_type'">
                  <a-tag color="blue">{{ artifactTypeLabel(record.artifact_type) }}</a-tag>
                </template>
                <template v-else-if="column.key === 'filename'">
                  <span class="mono">{{ record.latest_version?.filename || '-' }}</span>
                </template>
                <template v-else-if="column.key === 'version'">
                  v{{ record.latest_version?.version ?? 1 }}
                </template>
                <template v-else-if="column.key === 'created_at'">
                  {{ formatDateTimeOrDash(record.created_at) }}
                </template>
                <template v-else-if="column.key === 'actions'">
                  <a-button
                    v-if="record.latest_version?.id"
                    type="link"
                    size="small"
                    @click="downloadArtifactItem(record)"
                  >
                    {{ t('common.download') }}
                  </a-button>
                </template>
              </template>
            </a-table>
          </a-collapse-panel>
        </a-collapse>
      </a-spin>
    </section>

    <!-- 上传到项目数据空间 -->
    <a-modal
      v-model:open="artifactUploadVisible"
      :title="t('compounds.dataSpaceUploadTitle')"
      :confirm-loading="artifactUploading"
      :ok-text="t('compounds.dataSpaceUploadSubmit')"
      data-testid="assets-upload-artifact-modal"
      @ok="submitArtifactUpload"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('compounds.dataSpaceUploadFileLabel')" required>
          <input
            type="file"
            accept=".pdb,.cif,.mmcif,.fasta,.fa,.sdf,.mol2,.smi,.csv,.tsv,.json,.zip"
            class="import-file-input"
            data-testid="assets-upload-artifact-input"
            @change="handleArtifactFileChange"
          />
          <div v-if="artifactUploadFile" class="import-file-name">
            {{ artifactUploadFile.name }}
          </div>
        </a-form-item>
        <a-form-item :label="t('compounds.dataSpaceUploadTypeLabel')" required>
          <a-select v-model:value="artifactUploadType" :options="artifactTypeOptions" />
        </a-form-item>
        <a-form-item :label="t('compounds.dataSpaceUploadDescLabel')">
          <a-input
            v-model:value="artifactUploadDescription"
            :placeholder="t('compounds.dataSpaceUploadDescPlaceholder')"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import { formatDateTimeOrDash } from '@/domain/common/format'
  import AppEmptyState from '@/components/common/AppEmptyState.vue'
  import AppInlineError from '@/components/common/AppInlineError.vue'
  import ProjectViewSwitcher from '@/components/projects/ProjectViewSwitcher.vue'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import SkeletonList from '@/components/common/SkeletonList.vue'
  import { buildProjectDataViewTabs } from '@/domain/projects'
  import {
    buildArtifactVersionDownloadUrl,
    getAllProjectArtifacts,
    uploadProjectArtifact
  } from '@/api/artifacts'
  import { getTaskList } from '@/api/tasks'
  import { triggerProtectedFileDownload } from '@/utils/protected-file-access'
  import type { AssetArtifactType, TypedArtifact } from '@/types/artifacts'
  import type { Task } from '@/types/models'

  const route = useRoute()
  const { t } = useI18n()

  const projectId = computed(() => String(route.params.projectId || ''))
  const dataViewTabs = computed(() => buildProjectDataViewTabs(projectId.value))

  const artifactTypeFilter = ref<string | undefined>(undefined)
  const loading = ref(false)
  const loadError = ref(false)

  const artifacts = ref<TypedArtifact[]>([])
  const taskMap = ref<Record<string, Task>>({})
  const expandedGroupKeys = ref<string[]>([])

  const artifactColumns = computed(() => [
    { title: t('common.name'), dataIndex: 'name', key: 'name', width: 220 },
    { title: t('compounds.dataSpaceColType'), key: 'artifact_type', width: 140 },
    { title: t('compounds.dataSpaceColFilename'), key: 'filename', width: 220 },
    { title: t('compounds.dataSpaceColVersion'), key: 'version', width: 80 },
    { title: t('common.createdAt'), key: 'created_at', width: 160 },
    { title: t('common.actions'), key: 'actions', width: 100 }
  ])

  const artifactTypeOptions: Array<{
    value: AssetArtifactType
    label: string
    semantic: string
    standardType?: string
  }> = [
    { value: 'protein_structure', label: '蛋白结构（PDB / CIF）', semantic: 'protein_structure', standardType: 'protein_structure' },
    { value: 'ligand_structure', label: '配体 / 小分子结构（SDF / MOL2）', semantic: 'ligand_structure', standardType: 'ligand_structure' },
    { value: 'binding_pocket', label: '结合口袋（PDB / JSON）', semantic: 'binding_pocket', standardType: 'binding_pocket' },
    { value: 'molecule_table', label: '分子表（CSV / SMI）', semantic: 'molecule_table', standardType: 'molecule_table' },
    { value: 'dataset', label: '通用数据集 / 序列（FASTA / ZIP）', semantic: 'dataset' },
  ]

  const artifactFilterOptions = [
    ...artifactTypeOptions.map(item => ({ value: item.value, label: item.label })),
    { value: 'compound_set', label: '化合物集' },
    { value: 'md_trajectory', label: 'MD 轨迹' },
    { value: 'run_report', label: '运行报告' },
  ]

  const filteredArtifacts = computed(() => {
    if (!artifactTypeFilter.value) return artifacts.value
    return artifacts.value.filter(item => item.artifact_type === artifactTypeFilter.value)
  })

  interface ArtifactFolderGroup {
    key: string
    taskId: string | null
    title: string
    createdAt: string
    items: TypedArtifact[]
  }

  const artifactGroups = computed<ArtifactFolderGroup[]>(() => {
    const groups = new Map<string, ArtifactFolderGroup>()
    for (const item of filteredArtifacts.value) {
      const taskId = item.latest_version?.source_task_id ?? null
      const key = taskId ?? '__manual__'
      let group = groups.get(key)
      if (!group) {
        const task = taskId ? taskMap.value[taskId] : undefined
        const title = taskId
          ? task?.name || task?.tool_name || task?.tool?.name || `#${taskId.slice(0, 8)}`
          : t('compounds.dataSpaceManualGroup')
        group = {
          key,
          taskId,
          title,
          createdAt: task?.created_at ?? item.created_at,
          items: [],
        }
        groups.set(key, group)
      }
      group.items.push(item)
    }
    return Array.from(groups.values()).sort((a, b) => {
      if (a.key === '__manual__') return -1
      if (b.key === '__manual__') return 1
      return (b.createdAt || '').localeCompare(a.createdAt || '')
    })
  })

  function artifactTypeLabel(type: string): string {
    return artifactFilterOptions.find(item => item.value === type)?.label ?? type
  }

  const artifactUploadVisible = ref(false)
  const artifactUploading = ref(false)
  const artifactUploadFile = ref<File | null>(null)
  const artifactUploadType = ref<AssetArtifactType>('protein_structure')
  const artifactUploadDescription = ref('')

  async function loadAll(): Promise<void> {
    if (!projectId.value) return
    loading.value = true
    loadError.value = false
    try {
      const [artifactRes, tasksRes] = await Promise.allSettled([
        getAllProjectArtifacts(projectId.value),
        getTaskList({ project_id: projectId.value, page: 1, page_size: 100 }),
      ])
      if (artifactRes.status === 'fulfilled') {
        artifacts.value = artifactRes.value.data.items ?? []
      } else {
        loadError.value = true
      }
      if (tasksRes.status === 'fulfilled') {
        const map: Record<string, Task> = {}
        for (const task of tasksRes.value.data.items ?? []) {
          map[task.id] = task
        }
        taskMap.value = map
      }
      if (expandedGroupKeys.value.length === 0) {
        expandedGroupKeys.value = artifactGroups.value.slice(0, 3).map(group => group.key)
      }
    } catch {
      loadError.value = true
    } finally {
      loading.value = false
    }
  }

  function openArtifactUpload(): void {
    artifactUploadVisible.value = true
    artifactUploadFile.value = null
    artifactUploadDescription.value = ''
  }

  function handleArtifactFileChange(event: Event): void {
    const target = event.target as HTMLInputElement
    const file = target.files?.[0] ?? null
    artifactUploadFile.value = file
    if (!file) return
    const lower = file.name.toLowerCase()
    if (lower.endsWith('.pdb') || lower.endsWith('.cif') || lower.endsWith('.mmcif')) {
      artifactUploadType.value = 'protein_structure'
    } else if (lower.endsWith('.sdf') || lower.endsWith('.mol2')) {
      artifactUploadType.value = 'ligand_structure'
    } else if (lower.endsWith('.csv') || lower.endsWith('.smi') || lower.endsWith('.tsv')) {
      artifactUploadType.value = 'molecule_table'
    } else {
      artifactUploadType.value = 'dataset'
    }
  }

  async function submitArtifactUpload(): Promise<void> {
    if (!artifactUploadFile.value || !projectId.value) {
      message.warning(t('compounds.dataSpaceUploadFileRequired'))
      return
    }
    const option = artifactTypeOptions.find(item => item.value === artifactUploadType.value)
    artifactUploading.value = true
    try {
      await uploadProjectArtifact(projectId.value, {
        file: artifactUploadFile.value,
        artifact_type: artifactUploadType.value,
        semantic_type: option?.semantic ?? artifactUploadType.value,
        ...(option?.standardType
          ? { standard_type: option.standardType, standard_version: 1 }
          : {}),
        description: artifactUploadDescription.value.trim() || undefined,
      })
      message.success(t('compounds.dataSpaceUploadSuccess'))
      artifactUploadVisible.value = false
      await loadAll()
    } catch {
      message.error(t('compounds.dataSpaceUploadFailed'))
    } finally {
      artifactUploading.value = false
    }
  }

  async function downloadArtifactItem(record: TypedArtifact): Promise<void> {
    const version = record.latest_version
    if (!version?.id) return
    try {
      await triggerProtectedFileDownload({
        url: buildArtifactVersionDownloadUrl(record.id, version.id),
        filename: version.filename || record.name,
      })
    } catch (cause) {
      message.error(cause instanceof Error ? cause.message : String(cause))
    }
  }

  onMounted(() => {
    void loadAll()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .compounds-assets-page {
    max-width: @page-max-width;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .back-link {
    display: inline-block;
    margin-bottom: @spacing-lg;
    color: @text-tertiary;
  }

  .assets-alert {
    margin-bottom: @spacing-lg;
  }

  .assets-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    margin-bottom: @spacing-md;
  }

  .assets-space-hint {
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .artifact-folder-head {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    flex-wrap: wrap;
  }

  .artifact-folder-title {
    font-weight: @font-weight-semibold;
  }

  .artifact-folder-time {
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .import-file-input {
    display: block;
    width: 100%;
    padding: @spacing-sm;
    color: @text-secondary;
    background: @bg-elevated;
    border: 1px dashed @border-color;
    border-radius: @border-radius-md;
  }

  .import-file-name {
    margin-top: @spacing-xs;
    color: @text-tertiary;
    font-size: @font-size-xs;
  }
</style>
