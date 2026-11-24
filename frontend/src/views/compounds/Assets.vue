<template>
  <main class="compounds-assets-page">
    <router-link :to="`/projects/${projectId}`" class="back-link">
      {{ t('compounds.backToProject') }}
    </router-link>
    <ProjectWorkspaceNav :project-id="projectId" />
    <ProjectViewSwitcher :items="dataViewTabs" active="assets" />

    <AppPageHeader :title="t('compounds.title')" :subtitle="t('compounds.subtitle')">
      <template #actions>
        <a-space>
          <a-button
            type="primary"
            data-testid="assets-upload-artifact-open"
            @click="openArtifactUpload"
          >
            上传到数据空间
          </a-button>
          <a-button data-testid="assets-import-open" @click="openImport">
            {{ t('compounds.actions.import') }}
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

    <SkeletonList v-if="loading && !hasAnyRecord" :count="5" />

    <AppEmptyState
      v-else-if="!loadError && !hasAnyRecord"
      :title="t('compounds.empty.compounds')"
      :description="t('compounds.emptyHint.assets')"
    >
      <a-button type="primary" @click="openArtifactUpload">上传到数据空间</a-button>
      <a-button @click="openImport">{{ t('compounds.actions.import') }}</a-button>
      <a-button @click="createVisible = true">{{ t('compounds.actions.create') }}</a-button>
    </AppEmptyState>

    <section v-else class="assets-space-section" data-testid="assets-space-section">
      <!-- 项目数据空间（按每次工具调用分组成目录，避免成千上万个单分子平铺） -->
      <div class="assets-toolbar">
        <a-space wrap>
          <a-select
            v-model:value="artifactTypeFilter"
            style="width: 200px"
            allow-clear
            placeholder="按类型筛选"
            :options="artifactFilterOptions"
          />
          <span class="assets-space-hint">
            按每次工具调用分组成目录，点击「查看结果」即可钻进该次生成的分子明细。
          </span>
        </a-space>
      </div>

      <a-spin :spinning="artifactsLoading">
        <a-empty
          v-if="artifactGroups.length === 0"
          description="项目数据空间暂无文件，可直接上传蛋白 PDB、配体 SDF 或发起任务"
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
                <a-tag>{{ group.items.length }} 个产物</a-tag>
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
                查看结果 →
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
      title="上传文件到项目数据空间"
      :confirm-loading="artifactUploading"
      ok-text="上传"
      data-testid="assets-upload-artifact-modal"
      @ok="submitArtifactUpload"
    >
      <a-form layout="vertical">
        <a-form-item label="选择文件（PDB / CIF / FASTA / SDF / MOL2 / CSV / SMI）" required>
          <input
            type="file"
            accept=".pdb,.cif,.mmcif,.fasta,.fa,.sdf,.mol2,.smi,.csv,.tsv,.json,.zip"
            class="import-file-input"
            data-testid="assets-upload-artifact-input"
            @change="handleArtifactFileChange"
          />
          <div v-if="artifactUploadFile" class="import-file-name">
            已选：{{ artifactUploadFile.name }}
          </div>
        </a-form-item>
        <a-form-item label="数据类型" required>
          <a-select v-model:value="artifactUploadType" :options="artifactTypeOptions" />
        </a-form-item>
        <a-form-item label="说明（可选）">
          <a-input v-model:value="artifactUploadDescription" placeholder="例如：EGFR 野生型受体结构" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 批量导入 -->
    <a-modal
      v-model:open="importVisible"
      :title="t('compounds.import.title')"
      :confirm-loading="importing"
      :ok-text="t('compounds.import.submit')"
      data-testid="assets-import-modal"
      @ok="submitImport"
    >
      <p class="import-subtitle">
        {{ t('compounds.import.subtitle') }}（.smi / .csv / .sdf）
      </p>

      <a-form layout="vertical">
        <a-form-item :label="t('compounds.import.selectFile')">
          <input
            class="import-file-input"
            type="file"
            accept=".smi,.csv,.sdf"
            data-testid="assets-import-input"
            @change="handleFileChange"
          />
          <div v-if="importFileName" class="import-file-name">
            {{ t('compounds.import.fileName') }}: {{ importFileName }}
          </div>
        </a-form-item>
        <a-form-item :label="t('compounds.import.datasetName')">
          <a-input
            v-model:value="importDatasetName"
            :placeholder="t('compounds.import.datasetNamePlaceholder')"
          />
        </a-form-item>
        <a-form-item :label="t('compounds.import.smilesColumn')">
          <a-input
            v-model:value="importSmilesColumn"
            :placeholder="t('compounds.import.smilesColumnPlaceholder')"
          />
        </a-form-item>
        <a-form-item :label="t('compounds.import.nameColumn')">
          <a-input
            v-model:value="importNameColumn"
            :placeholder="t('compounds.import.nameColumnPlaceholder')"
          />
        </a-form-item>
        <a-form-item :label="t('compounds.import.dedupeStrategy')">
          <a-select v-model:value="dedupeStrategy">
            <a-select-option value="INCHIKEY_SKIP">
              {{ t('compounds.import.dedupeOptions.skip') }}
            </a-select-option>
            <a-select-option value="INCHIKEY_UPDATE">
              {{ t('compounds.import.dedupeOptions.update') }}
            </a-select-option>
            <a-select-option value="INCHIKEY_ERROR">
              {{ t('compounds.import.dedupeOptions.error') }}
            </a-select-option>
          </a-select>
        </a-form-item>
      </a-form>

      <section v-if="importResult" class="import-summary" data-testid="assets-import-summary">
        <h4>{{ t('compounds.import.summary') }}</h4>
        <a-descriptions :column="2" size="small" bordered>
          <a-descriptions-item :label="t('compounds.import.total')">
            {{ importResult.summary.total }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('compounds.import.success')">
            {{ importResult.summary.success }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('compounds.import.failed')">
            {{ importResult.summary.failed }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('compounds.import.duplicate')">
            {{ importResult.summary.duplicate }}
          </a-descriptions-item>
        </a-descriptions>

        <template v-if="importResult.errors.length > 0">
          <h5 class="import-errors-title">{{ t('compounds.import.errors') }}</h5>
          <ul class="import-errors" data-testid="assets-import-errors">
            <li v-for="error in importResult.errors" :key="`${error.row}-${error.message}`">
              {{ t('compounds.import.errorRow') }} {{ error.row }}：{{ error.message }}
            </li>
          </ul>
          <p v-if="importErrorsTruncated" class="import-errors-hint">
            {{ t('compounds.import.errorsTruncated') }}
          </p>
        </template>
      </section>
    </a-modal>

    <!-- 新增化合物 -->
    <a-modal
      v-model:open="createVisible"
      :title="t('compounds.create.title')"
      :ok-text="t('compounds.create.submit')"
      :confirm-loading="creating"
      data-testid="assets-create-modal"
      @ok="submitCreate"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('compounds.create.name')">
          <a-input
            v-model:value="createName"
            :placeholder="t('compounds.create.namePlaceholder')"
          />
        </a-form-item>
        <a-form-item :label="t('compounds.create.smiles')" required>
          <a-input
            v-model:value="createSmiles"
            :placeholder="t('compounds.create.smilesPlaceholder')"
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
  import { uploadFile } from '@/api/files'
  import {
    buildArtifactVersionDownloadUrl,
    getAllProjectArtifacts,
    uploadProjectArtifact
  } from '@/api/artifacts'
  import { getTaskList } from '@/api/tasks'
  import { triggerProtectedFileDownload } from '@/utils/protected-file-access'
  import {
    createCompound,
    importCompounds,
    listCompounds
  } from '@/api/compounds'
  import Smiles2DCell from '@/components/tasks/Smiles2DCell.vue'
  import { formatPropertyValue } from '@/domain/compounds'
  import type { AssetArtifactType, TypedArtifact } from '@/types/artifacts'
  import type { Task } from '@/types/models'
  import type {
    Compound,
    CompoundImportResult,
    DedupeStrategy
  } from '@/types/compounds'

  type TabKey = 'artifacts' | 'compounds'

  const route = useRoute()
  const { t } = useI18n()

  const projectId = computed(() => String(route.params.projectId || ''))
  const dataViewTabs = computed(() => buildProjectDataViewTabs(projectId.value))
  const pageSize = 20

  /** 后端导入错误清单最多回 500 条，达到上限才提示「已截断」。 */
  const IMPORT_ERROR_LIMIT = 500

  /**
   * 详情页（`/compounds/:id`）自己拿不到所属项目，必须由入口链接带上 `project_id`，
   * 否则目标页的「返回数据资产」会变成死链。
   */
  const projectQuery = computed(() =>
    projectId.value ? `?project_id=${encodeURIComponent(projectId.value)}` : ''
  )

  function compoundRoute(id: string): string {
    return `/compounds/${encodeURIComponent(id)}${projectQuery.value}`
  }

  const activeTab = ref<TabKey>('artifacts')
  const show2DStructure = ref(false)
  const artifactTypeFilter = ref<string | undefined>(undefined)
  const loading = ref(false)
  const loadError = ref(false)
  // 加载失败时不能再说「还没有化合物」——那会让人以为要重新导入。
  const emptyTextFor = (key: string) => (loadError.value ? t('common.listStates.emptyAfterError') : t(key))

  const compounds = ref<Compound[]>([])
  const compoundTotal = ref(0)
  const compoundPage = ref(1)
  const compoundKeyword = ref('')

  const artifacts = ref<TypedArtifact[]>([])
  const artifactsLoading = ref(false)
  const taskMap = ref<Record<string, Task>>({})
  const expandedGroupKeys = ref<string[]>([])

  const hasAnyRecord = computed(
    () => compounds.value.length > 0 || artifacts.value.length > 0
  )

  /**
   * 性质列的空值文案。
   *
   * 资产表里一列全是 `-` 时，用户分不清「这个分子还没算性质」还是「算过但为空」。
   * RDKit 描述符只在导入或手动刷新时计算，所以「未计算」才是真实语义。
   */
  function propertyText(key: 'mol_weight' | 'QED', value: number | null | undefined): string {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return t('compounds.notCalculated')
    }
    return formatPropertyValue(key, value)
  }

  const compoundColumns = computed(() => [
    ...(show2DStructure.value ? [{ title: t('compounds.columns.structure'), key: 'structure', width: 140 }] : []),
    { title: t('compounds.columns.name'), key: 'name', width: 220 },
    { title: t('compounds.columns.inchikey'), dataIndex: 'inchikey', key: 'inchikey', width: 200 },
    { title: t('compounds.columns.smiles'), key: 'smiles', width: 220 },
    { title: t('compounds.columns.formula'), dataIndex: 'mol_formula', key: 'mol_formula', width: 120 },
    { title: t('compounds.columns.molWeight'), key: 'mol_weight', width: 110 },
    { title: t('compounds.columns.qed'), key: 'qed', width: 100 },
    { title: t('compounds.columns.createdAt'), key: 'created_at', width: 160 }
  ])

  const proteinColumns = computed(() => [
    { title: t('compounds.proteinColumns.name'), dataIndex: 'name', key: 'name', width: 240 },
    { title: t('compounds.proteinColumns.filename'), key: 'filename', width: 240 },
    { title: t('compounds.proteinColumns.createdAt'), key: 'created_at', width: 160 }
  ])

  const datasetColumns = computed(() => [
    { title: t('compounds.datasetColumns.name'), dataIndex: 'name', key: 'name', width: 240 },
    { title: t('compounds.datasetColumns.source'), key: 'source', width: 120 },
    { title: t('compounds.datasetColumns.datasetType'), key: 'dataset_type', width: 140 },
    { title: t('compounds.datasetColumns.rowCount'), key: 'row_count', width: 110 },
    { title: t('compounds.datasetColumns.fileCount'), key: 'file_count', width: 110 },
    { title: t('compounds.datasetColumns.createdAt'), key: 'created_at', width: 160 }
  ])

  const artifactColumns = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 220 },
    { title: '类型', key: 'artifact_type', width: 140 },
    { title: '文件名', key: 'filename', width: 220 },
    { title: '版本', key: 'version', width: 80 },
    { title: '创建时间', key: 'created_at', width: 160 },
    { title: '操作', key: 'actions', width: 100 }
  ]

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
          ? task?.name || task?.tool_name || task?.tool?.name || `任务 #${taskId.slice(0, 8)}`
          : '手动上传 / 基础文件'
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

  const importVisible = ref(false)
  const importing = ref(false)
  const importFile = ref<File | null>(null)
  const importFileName = ref('')
  const importDatasetName = ref('')
  const importSmilesColumn = ref('')
  const importNameColumn = ref('')
  const dedupeStrategy = ref<DedupeStrategy>('INCHIKEY_SKIP')
  const importResult = ref<CompoundImportResult | null>(null)

  const importErrorsTruncated = computed(
    () => (importResult.value?.errors.length ?? 0) >= IMPORT_ERROR_LIMIT
  )

  const createVisible = ref(false)
  const creating = ref(false)
  const createName = ref('')
  const createSmiles = ref('')

  function optionalText(value: string): string | undefined {
    const trimmed = value.trim()
    return trimmed ? trimmed : undefined
  }

  async function loadCompounds(): Promise<void> {
    if (!projectId.value) return
    const keyword = optionalText(compoundKeyword.value)
    const response = await listCompounds(projectId.value, {
      page: compoundPage.value,
      page_size: pageSize,
      ...(keyword ? { keyword } : {})
    })
    compounds.value = response.data.items
    compoundTotal.value = response.data.total
  }

  async function loadArtifacts(): Promise<void> {
    if (!projectId.value) return
    artifactsLoading.value = true
    try {
      const [artifactRes, tasksRes] = await Promise.allSettled([
        getAllProjectArtifacts(projectId.value),
        getTaskList({ project_id: projectId.value, page: 1, page_size: 100 }),
      ])
      if (artifactRes.status === 'fulfilled') {
        artifacts.value = artifactRes.value.data.items ?? []
      } else {
        throw artifactRes.reason
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
    } finally {
      artifactsLoading.value = false
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
      message.warning('请先选择要上传的文件')
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
      message.success('已上传到项目数据空间')
      artifactUploadVisible.value = false
      activeTab.value = 'artifacts'
      await loadArtifacts()
    } catch {
      message.error('上传到项目数据空间失败，请重试')
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

  async function loadAll(): Promise<void> {
    if (!projectId.value) return
    loading.value = true
    loadError.value = false
    const settled = await Promise.allSettled([
      loadCompounds(),
      loadArtifacts()
    ])
    loadError.value = settled.some(result => result.status === 'rejected')
    loading.value = false
  }

  function handleCompoundSearch(): void {
    compoundPage.value = 1
    void loadCompounds().catch(() => {
      loadError.value = true
    })
  }

  function openImport(): void {
    importVisible.value = true
    importResult.value = null
  }

  function handleFileChange(event: Event): void {
    const target = event.target as HTMLInputElement
    const file = target.files?.[0] ?? null
    importFile.value = file
    importFileName.value = file?.name ?? ''
  }

  async function submitImport(): Promise<void> {
    if (!importFile.value) {
      message.warning(t('compounds.import.fileRequired'))
      return
    }

    importing.value = true
    try {
      const uploaded = await uploadFile(importFile.value)
      const datasetName = optionalText(importDatasetName.value)
      const smilesColumn = optionalText(importSmilesColumn.value)
      const nameColumn = optionalText(importNameColumn.value)
      const response = await importCompounds(projectId.value, {
        file_id: uploaded.data.id,
        dedupe_strategy: dedupeStrategy.value,
        ...(datasetName ? { dataset_name: datasetName } : {}),
        ...(smilesColumn ? { smiles_column: smilesColumn } : {}),
        ...(nameColumn ? { name_column: nameColumn } : {})
      })
      importResult.value = response.data
      compoundPage.value = 1
      await loadCompounds()
    } catch {
      message.error(t('common.error'))
    } finally {
      importing.value = false
    }
  }

  async function submitCreate(): Promise<void> {
    const smiles = createSmiles.value.trim()
    if (!smiles) {
      message.warning(t('compounds.create.smiles'))
      return
    }

    creating.value = true
    try {
      const name = optionalText(createName.value)
      await createCompound(projectId.value, {
        smiles,
        ...(name ? { name } : {})
      })
      message.success(t('compounds.create.success'))
      createVisible.value = false
      createName.value = ''
      createSmiles.value = ''
      compoundPage.value = 1
      await loadCompounds()
    } catch {
      message.error(t('common.error'))
    } finally {
      creating.value = false
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

  .assets-tab-note {
    margin-bottom: @spacing-md;
  }

  .assets-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    margin-bottom: @spacing-md;
  }

  .assets-search {
    max-width: 320px;
  }

  .assets-pagination {
    display: flex;
    justify-content: flex-end;
    margin-top: @spacing-md;
  }

  .mono-cell {
    font-family: @font-family-mono;
    font-size: @font-size-xs;
    color: @text-secondary;
    word-break: break-all;
  }

  .import-subtitle {
    margin-bottom: @spacing-md;
    color: @text-tertiary;
    font-size: @font-size-sm;
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

  .import-summary {
    margin-top: @spacing-md;
    padding-top: @spacing-md;
    border-top: 1px solid @border-color;
  }

  .import-errors-title {
    margin: @spacing-md 0 @spacing-sm;
    font-size: @font-size-sm;
  }

  .import-errors {
    max-height: 180px;
    margin: 0;
    padding-left: @spacing-lg;
    overflow-y: auto;
    color: @error-color;
    font-size: @font-size-xs;

    li {
      margin-bottom: @spacing-xs;
    }
  }

  .import-errors-hint {
    margin: @spacing-xs 0 0;
    color: @text-tertiary;
    font-size: @font-size-xs;
  }
</style>
