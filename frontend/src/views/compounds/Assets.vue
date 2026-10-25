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
          <router-link :to="`/projects/${projectId}/candidates/compare`">
            <a-button data-testid="assets-compare-link">
              {{ t('compounds.actions.compare') }}
            </a-button>
          </router-link>
        </a-space>
      </template>
    </AppPageHeader>

    <a-alert
      v-if="loadError"
      class="assets-alert"
      type="error"
      show-icon
      data-testid="assets-error"
      :message="t('compounds.errors.loadCompounds')"
    >
      <template #action>
        <a-button size="small" @click="loadAll">{{ t('common.refresh') }}</a-button>
      </template>
    </a-alert>

    <SkeletonList v-if="loading && !hasAnyRecord" :count="5" />

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
          :columns="compoundColumns"
          :data-source="compounds"
          :pagination="false"
          :locale="{ emptyText: t('compounds.empty.compounds') }"
          row-key="id"
          size="middle"
          data-testid="assets-compound-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <router-link :to="`/compounds/${record.id}`">
                {{ record.name || record.inchikey }}
              </router-link>
            </template>
            <template v-else-if="column.key === 'smiles'">
              <span class="mono-cell">{{ record.canonical_smiles }}</span>
            </template>
            <template v-else-if="column.key === 'mol_weight'">
              {{ formatPropertyValue('mol_weight', record.mol_weight) }}
            </template>
            <template v-else-if="column.key === 'qed'">
              {{ formatPropertyValue('QED', record.props?.QED) }}
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

      <!-- 候选物 -->
      <a-tab-pane key="candidates" :tab="t('compounds.tabs.candidates')">
        <a-table
          :columns="candidateColumns"
          :data-source="candidates"
          :pagination="false"
          :locale="{ emptyText: t('compounds.empty.candidates') }"
          row-key="id"
          size="middle"
          data-testid="assets-candidate-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <router-link :to="`/candidates/${record.id}`">
                {{ candidateTitle(record) }}
              </router-link>
            </template>
            <template v-else-if="column.key === 'type'">
              <a-tag>{{ t(candidateLocationLabel(record)) }}</a-tag>
            </template>
            <template v-else-if="column.key === 'source'">
              {{ t(`candidates.source.${record.source}`) }}
            </template>
            <template v-else-if="column.key === 'design_score'">
              {{ record.design_score ?? '-' }}
            </template>
            <template v-else-if="column.key === 'created_at'">
              {{ formatDate(record.created_at) }}
            </template>
          </template>
        </a-table>

        <div v-if="candidateTotal > pageSize" class="assets-pagination">
          <a-pagination
            v-model:current="candidatePage"
            :total="candidateTotal"
            :page-size="pageSize"
            :show-total="(total: number) => t('common.totalItems', { total })"
            @change="loadCandidates"
          />
        </div>
      </a-tab-pane>

      <!-- 候选集 -->
      <a-tab-pane key="candidateSets" :tab="t('compounds.tabs.candidateSets')">
        <div class="assets-toolbar">
          <span />
          <a-button
            type="primary"
            data-testid="assets-create-set-open"
            @click="createSetVisible = true"
          >
            {{ t('compounds.actions.createSet') }}
          </a-button>
        </div>

        <a-table
          :columns="candidateSetColumns"
          :data-source="candidateSets"
          :pagination="false"
          :locale="{ emptyText: t('compounds.empty.candidateSets') }"
          row-key="id"
          size="middle"
          data-testid="assets-candidate-set-table"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <router-link :to="`/candidate-sets/${record.id}`">
                {{ record.name }}
              </router-link>
            </template>
            <template v-else-if="column.key === 'description'">
              {{ record.description || '-' }}
            </template>
            <template v-else-if="column.key === 'updated_at'">
              {{ formatDate(record.updated_at) }}
            </template>
          </template>
        </a-table>

        <div v-if="setTotal > pageSize" class="assets-pagination">
          <a-pagination
            v-model:current="setPage"
            :total="setTotal"
            :page-size="pageSize"
            :show-total="(total: number) => t('common.totalItems', { total })"
            @change="loadCandidateSets"
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
          <p class="import-errors-hint">{{ t('compounds.import.errorsTruncated') }}</p>
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

    <!-- 新建候选集 -->
    <a-modal
      v-model:open="createSetVisible"
      :title="t('compounds.set.create.title')"
      :ok-text="t('compounds.set.create.submit')"
      :confirm-loading="creatingSet"
      data-testid="assets-create-set-modal"
      @ok="submitCreateSet"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('compounds.set.create.name')" required>
          <a-input
            v-model:value="createSetName"
            :placeholder="t('compounds.set.create.namePlaceholder')"
          />
        </a-form-item>
        <a-form-item :label="t('compounds.set.create.description')">
          <a-textarea
            v-model:value="createSetDescription"
            :rows="3"
            :placeholder="t('compounds.set.create.descriptionPlaceholder')"
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
  import dayjs from 'dayjs'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import SkeletonList from '@/components/common/SkeletonList.vue'
  import { uploadFile } from '@/api/files'
  import {
    createCandidateSet,
    createCompound,
    importCompounds,
    listCandidateSets,
    listCandidates,
    listCompounds
  } from '@/api/compounds'
  import { candidateLocationLabel, formatPropertyValue } from '@/domain/compounds'
  import type {
    Candidate,
    CandidateSet,
    Compound,
    CompoundImportResult,
    DedupeStrategy
  } from '@/types/compounds'

  type TabKey = 'compounds' | 'candidates' | 'candidateSets'

  const route = useRoute()
  const { t } = useI18n()

  const projectId = computed(() => String(route.params.projectId || ''))
  const pageSize = 20

  const activeTab = ref<TabKey>('compounds')
  const loading = ref(false)
  const loadError = ref(false)

  const compounds = ref<Compound[]>([])
  const compoundTotal = ref(0)
  const compoundPage = ref(1)
  const compoundKeyword = ref('')

  const candidates = ref<Candidate[]>([])
  const candidateTotal = ref(0)
  const candidatePage = ref(1)

  const candidateSets = ref<CandidateSet[]>([])
  const setTotal = ref(0)
  const setPage = ref(1)

  const hasAnyRecord = computed(
    () => compounds.value.length > 0 || candidates.value.length > 0 || candidateSets.value.length > 0
  )

  const compoundColumns = computed(() => [
    { title: t('compounds.columns.name'), key: 'name', width: 220 },
    { title: t('compounds.columns.inchikey'), dataIndex: 'inchikey', key: 'inchikey', width: 200 },
    { title: t('compounds.columns.smiles'), key: 'smiles', width: 220 },
    { title: t('compounds.columns.formula'), dataIndex: 'mol_formula', key: 'mol_formula', width: 120 },
    { title: t('compounds.columns.molWeight'), key: 'mol_weight', width: 110 },
    { title: t('compounds.columns.qed'), key: 'qed', width: 100 },
    { title: t('compounds.columns.createdAt'), key: 'created_at', width: 160 }
  ])

  const candidateColumns = computed(() => [
    { title: t('candidates.fields.name'), key: 'name', width: 220 },
    { title: t('candidates.fields.type'), key: 'type', width: 120 },
    { title: t('candidates.fields.source'), key: 'source', width: 120 },
    { title: t('candidates.fields.designScore'), key: 'design_score', width: 120 },
    { title: t('candidates.fields.createdAt'), key: 'created_at', width: 160 }
  ])

  const candidateSetColumns = computed(() => [
    { title: t('compounds.set.columns.name'), key: 'name', width: 220 },
    { title: t('compounds.set.columns.description'), key: 'description' },
    { title: t('compounds.set.columns.itemCount'), dataIndex: 'item_count', key: 'item_count', width: 100 },
    { title: t('compounds.set.columns.version'), dataIndex: 'version', key: 'version', width: 90 },
    { title: t('compounds.set.columns.updatedAt'), key: 'updated_at', width: 160 }
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

  const createVisible = ref(false)
  const creating = ref(false)
  const createName = ref('')
  const createSmiles = ref('')

  const createSetVisible = ref(false)
  const creatingSet = ref(false)
  const createSetName = ref('')
  const createSetDescription = ref('')

  function formatDate(value: string | null | undefined): string {
    return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '-'
  }

  function candidateTitle(candidate: Candidate): string {
    return candidate.name || candidate.code || candidate.peptide_sequence || candidate.id
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

  async function loadCandidates(): Promise<void> {
    if (!projectId.value) return
    const response = await listCandidates(projectId.value, {
      page: candidatePage.value,
      page_size: pageSize
    })
    candidates.value = response.data.items
    candidateTotal.value = response.data.total
  }

  async function loadCandidateSets(): Promise<void> {
    if (!projectId.value) return
    const response = await listCandidateSets(projectId.value, {
      page: setPage.value,
      page_size: pageSize
    })
    candidateSets.value = response.data.items
    setTotal.value = response.data.total
  }

  async function loadAll(): Promise<void> {
    if (!projectId.value) return
    loading.value = true
    loadError.value = false
    const settled = await Promise.allSettled([
      loadCompounds(),
      loadCandidates(),
      loadCandidateSets()
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

  async function submitCreateSet(): Promise<void> {
    const name = createSetName.value.trim()
    if (!name) {
      message.warning(t('compounds.set.create.name'))
      return
    }

    creatingSet.value = true
    try {
      const description = optionalText(createSetDescription.value)
      await createCandidateSet(projectId.value, {
        name,
        ...(description ? { description } : {})
      })
      message.success(t('compounds.set.create.success'))
      createSetVisible.value = false
      createSetName.value = ''
      createSetDescription.value = ''
      setPage.value = 1
      await loadCandidateSets()
    } catch {
      message.error(t('common.error'))
    } finally {
      creatingSet.value = false
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
