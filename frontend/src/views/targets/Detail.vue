<template>
  <main class="target-detail-page" data-testid="target-detail-page">
    <router-link :to="`/projects/${projectId}`" class="back-link">
      {{ t('targets.backToProject') }}
    </router-link>

    <AppPageHeader
      :title="target ? target.name : t('targets.detail.title')"
      :subtitle="t('targets.detail.subtitle')"
    >
      <template #actions>
        <a-button :loading="loading" @click="load">{{ t('targets.refresh') }}</a-button>
        <a-button type="primary" data-testid="add-protein-button" @click="openProteinModal">
          {{ t('targets.detail.addProtein') }}
        </a-button>
      </template>
    </AppPageHeader>

    <AppErrorState
      v-if="loadError"
      data-testid="target-detail-error"
      code="ERR"
      :title="t('targets.loadFailed')"
      :description="t('targets.loadFailedHint')"
      :action-text="t('targets.backToProject')"
      :to="projectId ? `/projects/${projectId}` : '/'"
    />

    <template v-else>
      <SkeletonDetail v-if="loading && !target" />

      <template v-else-if="target">
        <section class="target-info" data-testid="target-info">
          <h3 class="section-title">{{ t('targets.detail.info') }}</h3>
          <AppDescriptionList :sections="infoSections" :columns="2" />
        </section>

        <section class="protein-section" data-testid="protein-section">
          <h2 class="section-title">
            {{ t('targets.detail.proteins', { count: proteins.length }) }}
          </h2>

          <AppEmptyState
            v-if="proteins.length === 0"
            class="protein-empty"
            data-testid="protein-empty"
            :title="t('targets.detail.empty')"
            description="一条蛋白记录对应一个靶点的氨基酸序列；有了序列才能发起结构预测或导入实测结构。"
          >
            <a-button type="primary" @click="openProteinModal">
              {{ t('targets.detail.addProtein') }}
            </a-button>
          </AppEmptyState>

          <a-spin v-else :spinning="structuresLoading">
            <div class="protein-list">
              <article
                v-for="protein in proteins"
                :key="protein.id"
                class="protein-card"
                data-testid="protein-card"
              >
                <header class="protein-card-head">
                  <div class="protein-title">
                    <h3>{{ protein.name }}</h3>
                    <span class="protein-meta">
                      {{ t('targets.detail.seqLength') }}:
                      {{ protein.seq_length ?? '-' }}
                      · {{ t('targets.detail.currentVersion') }}:
                      {{ protein.current_version ?? '-' }}
                    </span>
                  </div>
                  <div class="protein-actions">
                    <router-link :to="`/proteins/${protein.id}/predict`">
                      <a-button size="small" data-testid="protein-predict-entry">
                        {{ t('targets.detail.predict') }}
                      </a-button>
                    </router-link>
                    <a-button
                      size="small"
                      data-testid="protein-import-entry"
                      @click="openImportModal(protein)"
                    >
                      {{ t('targets.detail.importStructure') }}
                    </a-button>
                  </div>
                </header>

                <p v-if="protein.sequence" class="protein-sequence">
                  {{ truncateSequence(protein.sequence) }}
                </p>

                <div class="structure-block">
                  <span class="structure-label">
                    {{ t('targets.detail.structures', { count: structuresOf(protein.id).length }) }}
                  </span>
                  <p v-if="structuresOf(protein.id).length === 0" class="structure-empty">
                    {{ t('targets.detail.structuresEmpty') }}
                  </p>
                  <ul v-else class="structure-list">
                    <li v-for="structure in structuresOf(protein.id)" :key="structure.id">
                      <router-link
                        :to="`/structures/${structure.id}`"
                        data-testid="structure-link"
                      >
                        {{ formatOptionalText(structure.source_type) }}
                        · {{ formatTargetDateTime(structure.created_at) }}
                        · pLDDT {{ formatPlddtMean(structure.plddt_mean) }}<span v-if="plddtBand(structure.plddt_mean)">（{{ t(`targets.structure.plddtBand.${plddtBand(structure.plddt_mean)}`) }}）</span>
                      </router-link>
                    </li>
                  </ul>
                </div>
              </article>
            </div>
          </a-spin>
        </section>
      </template>
    </template>

    <a-modal
      v-model:open="proteinModalOpen"
      :title="t('targets.detail.addProteinTitle')"
      :confirm-loading="savingProtein"
      :ok-text="t('common.save')"
      :cancel-text="t('common.cancel')"
      @ok="handleCreateProtein"
    >
      <a-form layout="vertical" class="protein-form">
        <a-form-item :label="t('targets.detail.name')" required>
          <a-input
            v-model:value="proteinForm.name"
            :placeholder="t('targets.detail.namePlaceholder')"
            data-testid="protein-name-input"
            allow-clear
          />
        </a-form-item>
        <a-form-item :label="t('targets.detail.sequence')">
          <a-textarea
            v-model:value="proteinForm.sequence"
            :placeholder="t('targets.detail.sequencePlaceholder')"
            :rows="6"
            data-testid="protein-sequence-input"
          />
          <p class="field-hint">{{ t('targets.detail.sequenceHint') }}</p>
        </a-form-item>
        <a-form-item :label="t('targets.detail.uploadFile')">
          <a-upload
            :file-list="sequenceUploadList"
            accept=".fasta,.fa,.txt,.seq"
            :before-upload="() => false"
            :max-count="1"
            @update:file-list="handleSequenceUploadChange"
          >
            <a-button data-testid="protein-upload-button">
              {{ t('targets.detail.uploadFile') }}
            </a-button>
          </a-upload>
          <p v-if="proteinForm.fileName" class="field-hint">
            {{ t('targets.detail.fileSelected', { name: proteinForm.fileName }) }}
          </p>
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="importModalOpen"
      :title="t('targets.detail.importTitle')"
      :confirm-loading="importing"
      :ok-text="t('targets.detail.importStructure')"
      :cancel-text="t('common.cancel')"
      @ok="handleImportStructure"
    >
      <p class="field-hint">{{ t('targets.detail.importHint') }}</p>
      <a-upload
        :file-list="structureUploadList"
        accept=".pdb,.cif,.mmcif"
        :before-upload="() => false"
        :max-count="1"
        @update:file-list="handleStructureUploadChange"
      >
        <a-button data-testid="structure-upload-button">
          {{ t('targets.detail.structureFileHint') }}
        </a-button>
      </a-upload>
      <p v-if="structureFileName" class="field-hint">
        {{ t('targets.detail.fileSelected', { name: structureFileName }) }}
      </p>
      <a-checkbox v-model:checked="prepareAfterImport" data-testid="structure-import-prepare">
        {{ t('targets.detail.prepareAfterImport') }}
      </a-checkbox>
      <p class="field-hint">{{ t('targets.detail.prepareAfterImportHint') }}</p>
    </a-modal>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, reactive, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { message } from 'ant-design-vue'
  import type { UploadFile } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AppErrorState from '@/components/common/AppErrorState.vue'
  import AppEmptyState from '@/components/common/AppEmptyState.vue'
  import AppDescriptionList from '@/components/common/AppDescriptionList.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import {
    createProtein,
    getTarget,
    importStructure,
    prepareStructure,
    listStructures
  } from '@/api/targets'
  import { uploadFile } from '@/api/files'
  import { formatOptionalText, formatPlddtMean, formatTargetDateTime, formatTargetType, plddtBand, resolveTargetErrorMessage } from '@/domain/targets/display'
  import type { DescriptionSection } from '@/components/common/AppDescriptionList.vue'
  import type {
    ProteinDetail,
    ProteinStructureDetail,
    TargetSummary
  } from '@/types/targets'

  const SEQUENCE_PREVIEW_LENGTH = 120

  const route = useRoute()
  const { t } = useI18n()

  const targetId = computed(() => String(route.params.targetId || ''))
  const projectId = computed(() => target.value?.project_id || '')

  const target = ref<TargetSummary | null>(null)
  const structures = ref<Record<string, ProteinStructureDetail[]>>({})
  const loading = ref(false)
  const structuresLoading = ref(false)
  const loadError = ref(false)

  const proteinModalOpen = ref(false)
  const savingProtein = ref(false)
  const importModalOpen = ref(false)
  const importing = ref(false)
  const importTargetProtein = ref<ProteinDetail | null>(null)

  const proteinForm = reactive({
    name: '',
    sequence: '',
    fileName: '',
    fileId: '',
    uploadList: [] as UploadFile[]
  })
  const structureUploadList = ref<UploadFile[]>([])
  /** 导入后直接跑结构准备：用户上传的 PDB 通常就是为了拿可对接的受体。 */
  const prepareAfterImport = ref(true)
  const structureFileName = ref('')

  const proteins = computed<ProteinDetail[]>(() => target.value?.proteins ?? [])
  const sequenceUploadList = computed(() => proteinForm.uploadList)

  function structuresOf(proteinId: string): ProteinStructureDetail[] {
    return structures.value[proteinId] ?? []
  }

  function truncateSequence(sequence: string): string {
    if (sequence.length <= SEQUENCE_PREVIEW_LENGTH) {
      return sequence
    }
    return `${sequence.slice(0, SEQUENCE_PREVIEW_LENGTH)}…`
  }

  async function loadStructures(proteinList: ProteinDetail[]) {
    if (proteinList.length === 0) {
      return
    }
    structuresLoading.value = true
    try {
      const entries = await Promise.all(
        proteinList.map(async (protein) => {
          const response = await listStructures(protein.id)
          return [protein.id, response.data.items] as const
        })
      )
      structures.value = Object.fromEntries(entries)
    } catch {
      structures.value = {}
    } finally {
      structuresLoading.value = false
    }
  }

  async function load() {
    if (!targetId.value) {
      return
    }
    loading.value = true
    loadError.value = false
    try {
      const response = await getTarget(targetId.value)
      target.value = response.data
      await loadStructures(response.data.proteins ?? [])
    } catch {
      loadError.value = true
      target.value = null
    } finally {
      loading.value = false
    }
  }

  function openProteinModal() {
    proteinForm.name = ''
    proteinForm.sequence = ''
    proteinForm.fileName = ''
    proteinForm.fileId = ''
    proteinForm.uploadList = []
    proteinModalOpen.value = true
  }

  function handleSequenceUploadChange(files: UploadFile[]) {
    proteinForm.uploadList = files.slice(-1)
    const file = proteinForm.uploadList[0]
    proteinForm.fileName = file?.name ? String(file.name) : ''
    if (!proteinForm.fileName) {
      proteinForm.fileId = ''
    }
  }

  async function uploadSequenceFile(): Promise<string | null> {
    const file = proteinForm.uploadList[0]?.originFileObj
    if (!file) {
      return null
    }
    try {
      const response = await uploadFile(file)
      return response.data.id
    } catch (cause) {
      message.error(resolveTargetErrorMessage(cause, t('targets.detail.uploadFailed')))
      return null
    }
  }

  async function handleCreateProtein() {
    const name = proteinForm.name.trim()
    if (!name) {
      message.warning(t('targets.detail.nameRequired'))
      return
    }
    if (!proteinForm.sequence.trim() && proteinForm.uploadList.length === 0) {
      message.warning(t('targets.detail.sequenceRequired'))
      return
    }

    savingProtein.value = true
    try {
      let fileId: string | undefined
      if (!proteinForm.sequence.trim()) {
        const uploaded = await uploadSequenceFile()
        if (!uploaded) {
          return
        }
        fileId = uploaded
      }

      const payload = proteinForm.sequence.trim()
        ? { name, sequence: proteinForm.sequence.trim(), source: 'MANUAL' }
        : { name, file_id: fileId, source: 'IMPORT' }

      await createProtein(targetId.value, payload)
      proteinModalOpen.value = false
      message.success(t('targets.detail.addSuccess'))
      await load()
    } catch (cause) {
      message.error(resolveTargetErrorMessage(cause, t('targets.detail.addFailed')))
    } finally {
      savingProtein.value = false
    }
  }

  function openImportModal(protein: ProteinDetail) {
    importTargetProtein.value = protein
    structureUploadList.value = []
    structureFileName.value = ''
    importModalOpen.value = true
  }

  function handleStructureUploadChange(files: UploadFile[]) {
    structureUploadList.value = files.slice(-1)
    const file = structureUploadList.value[0]
    structureFileName.value = file?.name ? String(file.name) : ''
  }

  async function handleImportStructure() {
    const file = structureUploadList.value[0]?.originFileObj
    const protein = importTargetProtein.value
    if (!file || !protein) {
      message.warning(t('targets.detail.importFileRequired'))
      return
    }

    importing.value = true
    try {
      const uploaded = await uploadFile(file)
      const imported = await importStructure(protein.id, { file_id: uploaded.data.id })
      if (prepareAfterImport.value) {
        await prepareStructure(imported.data.id, {})
        message.success(t('targets.detail.importAndPrepareSuccess'))
      } else {
        message.success(t('targets.detail.importSuccess'))
      }
      importModalOpen.value = false
      await load()
    } catch (cause) {
      message.error(resolveTargetErrorMessage(cause, t('targets.detail.importFailed')))
    } finally {
      importing.value = false
    }
  }

  onMounted(() => {
    void load()
  })


  const infoSections = computed<DescriptionSection[]>(() => {
    const item = target.value
    if (!item) {
      return []
    }
    return [
      {
        key: 'target',
        fields: [
          { key: 'type', label: t('targets.list.type'), value: formatTargetType(item.target_type) },
          { key: 'uniprot', label: t('targets.list.uniprot'), value: formatOptionalText(item.uniprot_id), mono: true },
          { key: 'gene', label: t('targets.list.gene'), value: formatOptionalText(item.gene_name) },
          { key: 'createdAt', label: t('targets.createdAt'), value: formatTargetDateTime(item.created_at) },
          { key: 'description', label: t('targets.list.description'), value: formatOptionalText(item.description), span: 2 },
        ],
      },
    ]
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .target-detail-page {
    max-width: 1080px;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .back-link {
    display: inline-block;
    margin-bottom: @spacing-lg;
    color: @text-tertiary;

    &:hover {
      color: @accent-color;
    }
  }

  .target-info {
    margin-bottom: @spacing-xl;
  }

  .section-title {
    margin: 0 0 @spacing-md;
    color: @text-primary;
    font-size: @font-size-lg;
    font-weight: @font-weight-semibold;
  }

  .protein-empty {
    padding: @spacing-xl 0;
  }

  .protein-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-md;
  }

  .protein-card {
    padding: @spacing-md;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    background: @bg-surface;
  }

  .protein-card-head {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    justify-content: space-between;
    gap: @spacing-sm;
  }

  .protein-title h3 {
    margin: 0 0 2px;
    color: @text-primary;
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
  }

  .protein-meta {
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .protein-actions {
    display: flex;
    gap: @spacing-xs;
  }

  .protein-sequence {
    margin: @spacing-sm 0;
    color: @text-secondary;
    font-family: @font-family-mono;
    font-size: @font-size-xs;
    word-break: break-all;
  }

  .structure-block {
    margin-top: @spacing-sm;
    padding-top: @spacing-sm;
    border-top: 1px dashed @border-color;
  }

  .structure-label {
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .structure-empty {
    margin: @spacing-xs 0 0;
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .structure-list {
    margin: @spacing-xs 0 0;
    padding-left: @spacing-md;

    li {
      color: @text-secondary;
      font-size: @font-size-sm;
      line-height: @line-height-loose;
    }

    a {
      color: @accent-color;
    }
  }

  .field-hint {
    margin: @spacing-xs 0 0;
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .protein-form {
    padding-top: @spacing-sm;
  }
</style>
