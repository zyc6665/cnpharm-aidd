<template>
  <main class="compounds-assets-page">
    <router-link :to="`/projects/${projectId}`" class="back-link">
      {{ t('compounds.backToProject') }}
    </router-link>
    <ProjectWorkspaceNav :project-id="projectId" />

    <AppPageHeader :title="t('compounds.title')" :subtitle="t('compounds.subtitle')">
      <template #actions>
        <a-space>
          <a-button
            :loading="loading"
            data-testid="assets-refresh"
            @click="loadAll"
          >
            {{ t('compounds.actions.refresh') }}
          </a-button>
          <router-link :to="`/projects/${projectId}/candidates`">
            <a-button data-testid="assets-candidates-link">
              {{ t('compounds.actions.candidates') }}
            </a-button>
          </router-link>
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
      <a-button type="primary" @click="openImport">{{ t('compounds.actions.import') }}</a-button>
      <a-button @click="createVisible = true">{{ t('compounds.actions.create') }}</a-button>
    </AppEmptyState>

    <a-tabs v-else v-model:activeKey="activeTab" data-testid="assets-tabs">
      <!-- 化合物 -->
      <a-tab-pane key="compounds" :tab="t('compounds.tabs.compounds')">
        <div class="assets-toolbar">
          <a-input-search
            v-model:value="compoundKeyword"
            class="assets-search"
            allow-clear
            :placeholder="t('common.search')"
            data-testid="assets-compound-search"
            @search="handleCompoundSearch"
          />
          <a-space>
            <a-button
              type="primary"
              data-testid="assets-import-open"
              @click="openImport"
            >
              {{ t('compounds.actions.import') }}
            </a-button>
            <a-button data-testid="assets-create-open" @click="createVisible = true">
              {{ t('compounds.actions.create') }}
            </a-button>
          </a-space>
        </div>

        <a-table
          :scroll="{ x: 'max-content' }"
          :columns="compoundColumns"
          :data-source="compounds"
          :pagination="false"
          :locale="{ emptyText: emptyTextFor('compounds.empty.compounds') }"
          row-key="id"
          size="middle"
          data-testid="assets-compound-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'structure'">
              <Smiles2DCell :smiles="record.canonical_smiles || ''" :width="120" />
            </template>
            <template v-else-if="column.key === 'name'">
              <router-link :to="compoundRoute(record.id)">
                {{ record.name || record.inchikey }}
              </router-link>
            </template>
            <template v-else-if="column.key === 'smiles'">
              <span class="mono-cell">{{ record.canonical_smiles }}</span>
            </template>
            <template v-else-if="column.key === 'mol_weight'">
              {{ propertyText('mol_weight', record.mol_weight) }}
            </template>
            <template v-else-if="column.key === 'qed'">
              {{ propertyText('QED', record.props?.QED) }}
            </template>
            <template v-else-if="column.key === 'created_at'">
              {{ formatDate(record.created_at) }}
            </template>
          </template>
        </a-table>

        <div v-if="compoundTotal > pageSize" class="assets-pagination">
          <a-pagination
            v-model:current="compoundPage"
            :total="compoundTotal"
            :page-size="pageSize"
            :show-total="(total: number) => t('common.totalItems', { total })"
            @change="loadCompounds"
          />
        </div>
      </a-tab-pane>

      <!-- 蛋白（模型产出/上传的结构产物，非蛋白主数据） -->
      <a-tab-pane key="proteins" :tab="t('compounds.tabs.proteins')">
        <a-alert
          class="assets-tab-note"
          type="info"
          show-icon
          data-testid="assets-protein-note"
          :message="t('compounds.notes.proteins')"
        />

        <a-table
          :scroll="{ x: 'max-content' }"
          :columns="proteinColumns"
          :data-source="proteins"
          :pagination="false"
          :loading="proteinsLoading"
          :locale="{ emptyText: emptyTextFor('compounds.empty.proteins') }"
          row-key="id"
          size="middle"
          data-testid="assets-protein-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'filename'">
              <span class="mono-cell">{{ record.metadata.filename || '-' }}</span>
            </template>
            <template v-else-if="column.key === 'created_at'">
              {{ formatDate(record.created_at) }}
            </template>
          </template>
        </a-table>

        <div v-if="proteinTotal > pageSize" class="assets-pagination">
          <a-pagination
            v-model:current="proteinPage"
            :total="proteinTotal"
            :page-size="pageSize"
            :show-total="(total: number) => t('common.totalItems', { total })"
            @change="loadProteins"
          />
        </div>
      </a-tab-pane>

      <!-- 数据集（登记的数据集领域对象） -->
      <a-tab-pane key="datasets" :tab="t('compounds.tabs.datasets')">
        <a-table
          :scroll="{ x: 'max-content' }"
          :columns="datasetColumns"
          :data-source="datasets"
          :pagination="false"
          :loading="datasetsLoading"
          :locale="{ emptyText: emptyTextFor('compounds.empty.datasets') }"
          row-key="id"
          size="middle"
          data-testid="assets-dataset-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'source'">
              <a-tag :color="record.source === 'artifact' ? 'blue' : 'green'">
                {{
                  record.source === 'artifact'
                    ? t('compounds.datasetSource.upload')
                    : t('compounds.datasetSource.dataset')
                }}
              </a-tag>
            </template>
            <template v-else-if="column.key === 'dataset_type'">
              {{ record.metadata.datasetType || '-' }}
            </template>
            <template v-else-if="column.key === 'row_count'">
              {{ record.metadata.rowCount ?? '-' }}
            </template>
            <template v-else-if="column.key === 'file_count'">
              {{ record.metadata.fileCount ?? '-' }}
            </template>
            <template v-else-if="column.key === 'created_at'">
              {{ formatDate(record.created_at) }}
            </template>
          </template>
        </a-table>

        <div v-if="datasetTotal > pageSize" class="assets-pagination">
          <a-pagination
            v-model:current="datasetPage"
            :total="datasetTotal"
            :page-size="pageSize"
            :show-total="(total: number) => t('common.totalItems', { total })"
            @change="loadDatasets"
          />
        </div>
      </a-tab-pane>
    </a-tabs>

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
  import { formatDateTimeMinutes } from '@/utils/datetime'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AppEmptyState from '@/components/common/AppEmptyState.vue'
  import AppInlineError from '@/components/common/AppInlineError.vue'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import SkeletonList from '@/components/common/SkeletonList.vue'
  import { uploadFile } from '@/api/files'
  import { listProjectAssets } from '@/api/assets'
  import {
    createCompound,
    importCompounds,
    listCompounds
  } from '@/api/compounds'
  import Smiles2DCell from '@/components/tasks/Smiles2DCell.vue'
  import { formatPropertyValue } from '@/domain/compounds'
  import type { AssetItem } from '@/types/assets'
  import type {
    Compound,
    CompoundImportResult,
    DedupeStrategy
  } from '@/types/compounds'

  type TabKey = 'compounds' | 'proteins' | 'datasets'

  const route = useRoute()
  const { t } = useI18n()

  const projectId = computed(() => String(route.params.projectId || ''))
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

  const activeTab = ref<TabKey>('compounds')
  const loading = ref(false)
  const loadError = ref(false)
  // 加载失败时不能再说「还没有化合物」——那会让人以为要重新导入。
  const emptyTextFor = (key: string) => (loadError.value ? t('common.listStates.emptyAfterError') : t(key))

  const compounds = ref<Compound[]>([])
  const compoundTotal = ref(0)
  const compoundPage = ref(1)
  const compoundKeyword = ref('')

  const proteins = ref<AssetItem[]>([])
  const proteinTotal = ref(0)
  const proteinPage = ref(1)
  const proteinsLoading = ref(false)

  const datasets = ref<AssetItem[]>([])
  const datasetTotal = ref(0)
  const datasetPage = ref(1)
  const datasetsLoading = ref(false)

  const hasAnyRecord = computed(
    () =>
      compounds.value.length > 0 ||
      proteins.value.length > 0 ||
      datasets.value.length > 0
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
    { title: t('compounds.columns.structure'), key: 'structure', width: 140 },
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

  function formatDate(value: string | null | undefined): string {
    return value ? formatDateTimeMinutes(value) : '-'
  }

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

  async function loadProteins(): Promise<void> {
    if (!projectId.value) return
    proteinsLoading.value = true
    try {
      const response = await listProjectAssets(projectId.value, {
        type: 'protein_structure',
        page: proteinPage.value,
        page_size: pageSize
      })
      proteins.value = response.data.items
      proteinTotal.value = response.data.total
    } finally {
      proteinsLoading.value = false
    }
  }

  async function loadDatasets(): Promise<void> {
    if (!projectId.value) return
    datasetsLoading.value = true
    try {
      const response = await listProjectAssets(projectId.value, {
        type: 'dataset',
        page: datasetPage.value,
        page_size: pageSize
      })
      datasets.value = response.data.items
      datasetTotal.value = response.data.total
    } finally {
      datasetsLoading.value = false
    }
  }

  async function loadAll(): Promise<void> {
    if (!projectId.value) return
    loading.value = true
    loadError.value = false
    const settled = await Promise.allSettled([
      loadCompounds(),
      loadProteins(),
      loadDatasets()
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
    max-width: 1240px;
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
