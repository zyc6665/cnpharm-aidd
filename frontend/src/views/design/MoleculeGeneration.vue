<template>
  <main class="design-page" data-testid="molecule-generation-page">
    <AppPageHeader :title="t('design.molecule.title')" :subtitle="t('design.molecule.subtitle')" />

    <a-spin :spinning="resolving">
      <a-alert
        v-if="toolError"
        type="error"
        show-icon
        :message="t('design.molecule.toolMissing')"
        data-testid="molecule-tool-error"
      />

      <section class="design-section">
        <h3 class="design-section__title">{{ t('design.modelSelect.label') }}</h3>
        <ModelSelect v-model="selectedSlug" :options="modelOptions" :loading="modelLoading" />
      </section>

      <section class="design-section">
        <h3 class="design-section__title">{{ t('design.section.inputs') }}</h3>
        <a-radio-group
          v-model:value="sourceMode"
          button-style="solid"
          class="source-mode"
          data-testid="molecule-source-mode"
        >
          <a-radio-button value="project">{{ t('design.molecule.sourceProject') }}</a-radio-button>
          <a-radio-button value="upload">{{ t('design.molecule.sourceUpload') }}</a-radio-button>
        </a-radio-group>

        <div v-if="sourceMode === 'project'" class="source-body">
          <PocketPicker v-model="pocketSelection" :default-project-id="defaultProjectId" />
        </div>

        <div v-else class="source-body source-body--fields" data-testid="molecule-upload-source">
          <div class="source-field">
            <span class="source-label">{{ t('design.molecule.project') }}</span>
            <a-select
              v-model:value="uploadProjectId"
              class="source-control"
              show-search
              option-filter-prop="label"
              :options="projectOptions"
              :placeholder="t('design.molecule.projectPlaceholder')"
              data-testid="molecule-upload-project"
            />
          </div>
          <div class="source-field">
            <span class="source-label">{{ t('design.molecule.structureFile') }}</span>
            <div class="source-upload">
              <a-upload
                :show-upload-list="false"
                :before-upload="handleStructureFile"
                accept=".pdb,.cif,.ent"
                data-testid="molecule-upload-structure"
              >
                <a-button size="small">{{ t('design.molecule.chooseFile') }}</a-button>
              </a-upload>
              <span v-if="structureFile" class="source-file" data-testid="molecule-upload-structure-name">
                {{ structureFile.name }}
              </span>
              <span v-else class="source-hint">{{ t('design.molecule.structureFileHint') }}</span>
            </div>
          </div>
          <div class="source-field">
            <span class="source-label">{{ t('design.molecule.pocketFile') }}</span>
            <div class="source-upload">
              <a-upload
                :show-upload-list="false"
                :before-upload="handlePocketFile"
                accept=".pdb"
                data-testid="molecule-upload-pocket"
              >
                <a-button size="small">{{ t('design.molecule.chooseFile') }}</a-button>
              </a-upload>
              <span v-if="pocketFile" class="source-file" data-testid="molecule-upload-pocket-name">
                {{ pocketFile.name }}
              </span>
              <span class="source-hint">{{ t('design.molecule.pocketFileHint') }}</span>
            </div>
          </div>
        </div>
      </section>

      <a-alert
        v-if="hasSelection && !structureReady"
        type="warning"
        show-icon
        :message="t('design.molecule.pocketMissingFile')"
        class="pocket-alert"
      />
      <a-alert
        v-else-if="hasSelection && !hasCenter"
        type="warning"
        show-icon
        :message="t('design.molecule.pocketMissingCenter')"
        class="pocket-alert"
      />

      <section v-if="hasSelection" class="design-section pocket-summary" data-testid="molecule-pocket-summary">
        <h3 class="design-section__title">{{ t('design.molecule.pocketSummary') }}</h3>
        <a-descriptions :column="3" size="small" bordered>
          <a-descriptions-item :label="t('design.molecule.pocketLabel')">
            {{ pocketLabelText }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('design.molecule.pocketCenter')">
            {{ centerText }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('design.molecule.pocketBox')">
            {{ boxText }}
          </a-descriptions-item>
        </a-descriptions>
      </section>

      <section class="design-section">
        <h3 class="design-section__title">{{ t('design.section.parameters') }}</h3>
        <ModelParameterForm
          v-if="selectedOption?.parameterSchema"
          v-model="form.params"
          :schema="selectedOption.parameterSchema"
          :overrides="hiddenParams"
          :disabled="submitting"
        />
        <p class="param-hint">{{ t('design.molecule.paramHint') }}</p>
      </section>

      <div class="design-actions">
        <a-button
          type="primary"
          :loading="submitting"
          :disabled="!canSubmit"
          data-testid="molecule-submit"
          @click="handleSubmit"
        >
          {{ t('design.molecule.submit') }}
        </a-button>
      </div>
    </a-spin>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, reactive, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import PocketPicker from './components/PocketPicker.vue'
  import ModelSelect from '@/components/design/ModelSelect.vue'
  import ModelParameterForm from '@/components/design/ModelParameterForm.vue'
  import { useModelOptions } from '@/composables/useModelOptions'
  import { resolveToolBySlug, submitDesignTask } from '@/api/design'
  import { uploadFile } from '@/api/files'
  import { listProjects } from '@/api/projects'
  import { parsePocketGeometry, radiusOf } from '@/domain/pockets/pocket-geometry'
  import {
    buildDefaultValues,
    normalizeParameters,
    validateParameters,
    type ParameterValues
  } from '@/domain/tools/parameterSchema'
  import type { DesignPocketSelection, ResolvedDesignTool } from '@/types/design'
  import type { ResearchProject } from '@/types/projects'
  import type { ParameterFieldOverride } from '@/components/design/ModelParameterForm.vue'
  import { MOLECULE_GENERATION_TOOL_SLUG } from '@/types/design'

  const router = useRouter()
  const route = useRoute()
  const { t } = useI18n()

  const props = withDefaults(defineProps<{ initialProjectId?: string }>(), {
    initialProjectId: ''
  })

  const defaultProjectId = computed(() => {
    if (props.initialProjectId) return props.initialProjectId
    return typeof route.query.project_id === 'string' ? route.query.project_id : ''
  })

  const resolving = ref(false)
  const submitting = ref(false)
  const resolvedTool = ref<ResolvedDesignTool | null>(null)
  const toolError = ref(false)
  const pocketSelection = ref<DesignPocketSelection | null>(null)

  /**
   * 输入来源：项目里挑口袋，或者直接上传「结构 + 口袋文件」。
   *
   * 分子生成的核心输入只有两样：受体结构、口袋中心与半径。前者可以来自项目里的
   * 准备产物，也可以是用户手上的一个 PDB；后者在项目模式下由口袋记录给出，
   * 上传模式下从口袋文件里算（`pocket0.pdb` 的 UNL 点最准）。
   */
  const sourceMode = ref<'project' | 'upload'>('project')
  const projects = ref<ResearchProject[]>([])
  const uploadProjectId = ref<string>(route.query.project_id as string || '')
  const structureFile = ref<File | null>(null)
  const pocketFile = ref<File | null>(null)
  const uploadCenter = ref<{ x: number; y: number; z: number } | null>(null)
  const uploadBoxSize = ref<{ x: number; y: number; z: number } | null>(null)

  const projectOptions = computed(() =>
    projects.value.map((project) => ({ label: project.name, value: project.id }))
  )

  /** 上传模式下「用户已经选了东西」——用来决定要不要显示提示与摘要。 */
  const hasSelection = computed(() =>
    sourceMode.value === 'project'
      ? Boolean(pocketSelection.value)
      : Boolean(structureFile.value || pocketFile.value)
  )

  /** 受体结构是否就位：项目模式看口袋附件，上传模式看用户是否选了文件。 */
  const structureReady = computed(() =>
    sourceMode.value === 'project'
      ? Boolean(pocketSelection.value?.structureFileId)
      : Boolean(structureFile.value)
  )

  const pocketLabelText = computed(() =>
    sourceMode.value === 'project'
      ? pocketSelection.value?.pocketLabel || '-'
      : pocketFile.value?.name || '-'
  )

  // 同类分子生成模型可自由选择；默认 pocket2mol；参数 schema 随模型切换。
  const {
    options: modelOptions,
    selectedSlug,
    selectedOption,
    loading: modelLoading,
    load: loadModels
  } = useModelOptions('molecule_generation', { defaultSlug: MOLECULE_GENERATION_TOOL_SLUG })

  const form = reactive<{ params: ParameterValues }>({ params: {} })

  const hiddenParams: Record<string, ParameterFieldOverride> = {
    center_x: { hidden: true },
    center_y: { hidden: true },
    center_z: { hidden: true },
    pocket_radius: { hidden: false }
  }

  const activeCenter = computed(() =>
    sourceMode.value === 'project' ? pocketSelection.value?.center ?? null : uploadCenter.value
  )

  const activeBoxSize = computed(() =>
    sourceMode.value === 'project' ? pocketSelection.value?.boxSize ?? null : uploadBoxSize.value
  )

  const hasCenter = computed(() => {
    const center = activeCenter.value
    return Boolean(
      center &&
        center.x !== null &&
        center.y !== null &&
        center.z !== null &&
        Number.isFinite(center.x) &&
        Number.isFinite(center.y) &&
        Number.isFinite(center.z)
    )
  })

  const canSubmit = computed(
    () =>
      Boolean(
        resolvedTool.value &&
          structureReady.value &&
          hasCenter.value &&
          validateParameters(selectedOption.value?.parameterSchema ?? null, form.params).length === 0
      )
  )

  const centerText = computed(() => {
    const center = activeCenter.value
    if (!center || center.x === null || center.y === null || center.z === null) return '-'
    return `${center.x.toFixed(2)}, ${center.y.toFixed(2)}, ${center.z.toFixed(2)} Å`
  })

  const boxText = computed(() => {
    const box = activeBoxSize.value
    if (!box || box.x === null || box.y === null || box.z === null) return '-'
    return `${box.x.toFixed(1)} × ${box.y.toFixed(1)} × ${box.z.toFixed(1)} Å`
  })

  function toNumber(value: unknown, fallback: number): number {
    const parsed = typeof value === 'number' ? value : Number(value)
    return Number.isFinite(parsed) ? parsed : fallback
  }

  async function loadProjects(): Promise<void> {
    try {
      const response = await listProjects()
      projects.value = response.data.items ?? []
    } catch {
      projects.value = []
    }
  }

  /** a-upload 的 before-upload 返回 false 就只拿文件、不发请求。 */
  function handleStructureFile(file: File): boolean {
    structureFile.value = file
    return false
  }

  async function handlePocketFile(file: File): Promise<boolean> {
    pocketFile.value = file
    let geometry = null
    try {
      geometry = parsePocketGeometry(await file.text())
    } catch {
      geometry = null
    }
    if (!geometry) {
      uploadCenter.value = null
      uploadBoxSize.value = null
      message.warning(t('design.molecule.pocketFileUnreadable'))
      return false
    }
    uploadCenter.value = geometry.center
    uploadBoxSize.value = geometry.boxSize
    const radius = radiusOf(geometry)
    if (radius > 0) {
      form.params = { ...form.params, pocket_radius: radius }
    }
    return false
  }

  function validate(): string | null {
    if (!structureReady.value) {
      return t('design.molecule.pocketMissingFile')
    }
    if (sourceMode.value === 'upload' && !uploadProjectId.value) {
      return t('design.molecule.needProject')
    }
    if (!hasCenter.value) {
      return t('design.molecule.pocketMissingCenter')
    }
    const errors = validateParameters(selectedOption.value?.parameterSchema ?? null, form.params)
    if (errors.length > 0) return t('design.molecule.invalidNum')
    return null
  }

  async function loadTool(): Promise<void> {
    resolving.value = true
    toolError.value = false
    try {
      resolvedTool.value = await resolveToolBySlug(selectedSlug.value)
      if (!resolvedTool.value) {
        toolError.value = true
      }
    } catch {
      toolError.value = true
    } finally {
      resolving.value = false
    }
  }

  async function handleSubmit(): Promise<void> {
    if (!resolvedTool.value) {
      message.warning(t('design.molecule.selectPocketFirst'))
      return
    }
    const invalid = validate()
    if (invalid) {
      message.warning(invalid)
      return
    }

    const center = activeCenter.value
    const schema = selectedOption.value?.parameterSchema ?? null
    const params = {
      ...normalizeParameters(schema, form.params),
      center_x: toNumber(center?.x, 0),
      center_y: toNumber(center?.y, 0),
      center_z: toNumber(center?.z, 0)
    }

    submitting.value = true
    try {
      let projectId = pocketSelection.value?.projectId ?? ''
      let proteinPdbFileId = pocketSelection.value?.structureFileId ?? ''
      if (sourceMode.value === 'upload') {
        projectId = uploadProjectId.value
        // 上传模式自己把结构传上去；项目模式的文件早就在库里，直接用 id。
        if (structureFile.value) {
          proteinPdbFileId = (await uploadFile(structureFile.value)).data.id
        }
      }
      const response = await submitDesignTask({
        name: t('design.molecule.taskName'),
        projectId,
        toolId: resolvedTool.value.tool.id,
        toolVersionId: resolvedTool.value.version.id,
        params,
        standardInputUploads: { protein_pdb: proteinPdbFileId }
      })
      message.success(t('design.molecule.submitted'))
      await router.push({ name: 'GenerationResults', params: { id: response.data.id } })
    } catch {
      message.error(t('design.molecule.failed'))
    } finally {
      submitting.value = false
    }
  }

  watch(
    selectedOption,
    option => {
      form.params = buildDefaultValues(option?.parameterSchema ?? null)
    },
    { immediate: true }
  )

  watch(
    pocketSelection,
    selection => {
      const box = selection?.boxSize
      if (!box) return
      const dims = [box.x, box.y, box.z].filter(
        (value): value is number => typeof value === 'number' && Number.isFinite(value) && value > 0
      )
      if (dims.length > 0) {
        form.params = {
          ...form.params,
          pocket_radius: Number((Math.max(...dims) / 2).toFixed(1))
        }
      }
    },
    { deep: true }
  )

  onMounted(() => {
    void loadModels().then(() => loadTool())
    void loadProjects()
  })

  watch(selectedSlug, () => {
    void loadTool()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .design-page {
    max-width: @page-max-width;
    margin: 0 auto;
    padding: 32px 24px 48px;
  }

  .design-section {
    margin-bottom: 24px;
    padding: 20px;
    border: 1px solid @border-color;
    border-radius: 8px;
    background: @bg-surface;
  }

  .design-section__title {
    margin: 0 0 16px;
    font-size: 16px;
    font-weight: 600;
  }

  .pocket-alert {
    margin-bottom: 24px;
  }

  .source-mode {
    margin-bottom: 16px;
  }

  .source-body {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  // 上传模式的几个字段：宽屏时并排铺开，窄屏自动退成单列
  .source-body--fields {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(@field-grid-min, 1fr));
    gap: 16px;
    align-items: start;
  }

  .source-field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .source-label {
    color: @text-secondary;
    font-size: @font-size-sm;
  }

  .source-control {
    width: 100%;
  }

  .source-upload {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .source-file {
    color: @text-primary;
    font-size: @font-size-sm;
    word-break: break-all;
  }

  .source-hint {
    color: @text-tertiary;
    font-size: @font-size-sm;
    line-height: 1.5;
  }

  .number-input {
    width: 100%;
  }

  .param-hint {
    margin: 0;
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .design-actions {
    display: flex;
    justify-content: flex-end;
  }
</style>
