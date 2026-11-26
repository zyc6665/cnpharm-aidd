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

      <div class="design-workbench">
        <div class="design-workbench__main">
          <section class="design-section" data-testid="molecule-section-model">
            <h3 class="design-section__title">{{ t('design.modelSelect.label') }}</h3>
            <ModelSelect v-model="selectedSlug" :options="modelOptions" :loading="modelLoading" :disabled="submitting" />
          </section>

          <section class="design-section" data-testid="molecule-section-input">
            <div class="section-header-row">
              <h3 class="design-section__title">{{ t('design.section.inputs') }}</h3>
              <a-button
                size="small"
                :disabled="submitting"
                data-testid="molecule-load-sample"
                @click="handleLoadSample"
              >
                {{ t('design.molecule.loadSample') }}
              </a-button>
            </div>
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

      <section v-if="supportsGenerationMode" class="design-section mode-section" data-testid="molecule-generation-modes">
        <h3 class="design-section__title">{{ t('design.molecule.generationMode') }}</h3>
        <a-radio-group
          v-model:value="generationMode"
          class="mode-cards"
          :aria-label="t('design.molecule.generationMode')"
          :disabled="submitting"
        >
          <a-radio-button
            v-for="mode in generationModes"
            :key="mode"
            :value="mode"
            class="mode-card"
            :data-testid="`molecule-mode-${mode}`"
          >
            <span class="mode-card__body">
              <strong class="mode-card__title">{{ t(`modelParams.options.${modeTitles[mode]}`) }}</strong>
              <span class="mode-card__desc">{{ t(`design.molecule.modeDescription.${mode}`) }}</span>
            </span>
          </a-radio-button>
        </a-radio-group>
      </section>

      <section v-if="needsLigandFile" class="design-section fragment-section" data-testid="molecule-fragment-section">
        <h3 class="design-section__title">{{ t('design.molecule.fragmentTitle') }}</h3>
        <p class="fragment-hint">{{ t('design.molecule.fragmentHint') }}</p>
        <div class="source-upload">
          <a-upload
            :show-upload-list="false"
            :before-upload="handleFragmentFile"
            :disabled="submitting"
            accept=".sdf,.mol,.mol2,.pdb"
            data-testid="molecule-upload-fragment"
          >
            <a-button size="small" :disabled="submitting">{{ t('design.molecule.chooseFile') }}</a-button>
          </a-upload>
          <span v-if="fragmentFile" class="source-file" data-testid="molecule-fragment-name">{{ fragmentFile.name }}</span>
        </div>
        <div v-if="fragmentFile && !fragmentParsing" class="fragment-preview" data-testid="molecule-fragment-preview">
          <span>
            {{ fragmentCount === null
              ? t('design.molecule.fragmentFileReady')
              : t('design.molecule.fragmentAtomCount', { count: fragmentCount, lastIndex: fragmentCount - 1 }) }}
          </span>
          <span v-if="fragmentSubsetCropped && generationMode === 'fragment'" class="fragment-cropped-tag" data-testid="molecule-fragment-cropped">
            {{ t('design.molecule.subsetCroppedTag') }}
          </span>
        </div>
        <MoleculeInlineFragmentCard
          v-if="fragmentMolecule && !fragmentParsing && (generationMode === 'fragment' || generationMode === 'dock')"
          class="fragment-inline-card"
          :filename="fragmentFile?.name || fragmentMolecule.name"
          :atoms="fragmentMolecule.atoms"
          :bonds="fragmentMolecule.bonds"
          :selected-indices="activeSketchSelection"
          :mode="generationMode === 'dock' ? 'dock' : 'fragment'"
          :disabled="submitting"
          @open-sketch="sketchModalOpen = true"
        />
        <a-alert
          v-if="fragmentIssue"
          class="fragment-alert"
          :type="fragmentError ? 'error' : 'warning'"
          show-icon
          :message="t(fragmentIssue)"
          data-testid="molecule-fragment-required"
        />
        <div v-if="generationMode === 'fragment' && schema?.properties?.molecule_size" class="fragment-presets" data-testid="molecule-size-presets">
          <span>{{ t('design.molecule.moleculeSize') }}</span>
          <a-button
            v-for="preset in moleculeSizePresets"
            :key="preset.id"
            size="small"
            :disabled="submitting"
            :type="(form.params.molecule_size ?? '') === preset.value ? 'primary' : 'default'"
            :data-testid="`molecule-size-${preset.id}`"
            @click="form.params.molecule_size = preset.value"
          >
            {{ t(`design.molecule.sizePreset.${preset.id}`) }}
          </a-button>
        </div>
        <div v-if="generationMode === 'dock' && schema?.properties?.atoms_to_dock" class="source-field fragment-dock-field">
          <label class="source-label" for="atoms-to-dock">{{ t('design.molecule.atomsToDock') }}</label>
          <a-input
            id="atoms-to-dock"
            v-model:value="atomsToDock"
            :disabled="submitting"
            :status="atomsInvalid ? 'error' : undefined"
            aria-describedby="atoms-to-dock-hint"
            placeholder="0 1 2"
            data-testid="molecule-atoms-to-dock"
          />
          <span id="atoms-to-dock-hint" class="source-hint">{{ t(atomsInvalid ? 'design.molecule.atomsToDockInvalid' : 'design.molecule.atomsToDockHint') }}</span>
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

      <section class="design-section" data-testid="molecule-section-params">
        <div class="param-header">
          <h3 class="design-section__title">{{ t('design.section.parameters') }}</h3>
          <a-button size="small" :disabled="submitting" data-testid="molecule-reset-params" @click="resetParams">
            {{ t('design.molecule.resetParams') }}
          </a-button>
        </div>
        <ParameterPresets
          v-if="selectedOption?.parameterSchema"
          :schema="selectedOption.parameterSchema"
          :values="form.params"
          :storage-key="presetStorageKey"
          :disabled="submitting"
          @load="handlePresetLoad"
        />
        <ModelParameterForm
          v-if="selectedOption?.parameterSchema"
          v-model="form.params"
          :schema="selectedOption.parameterSchema"
          :overrides="hiddenParams"
          :disabled="submitting"
          :primary-keys="PRIMARY_PARAM_KEYS"
        />
        <p class="param-hint">{{ t('design.molecule.paramHint', { model: selectedOption?.name || 'Pocket2Mol' }) }}</p>
      </section>

      <div class="design-actions">
        <a-button
          v-if="submittedTaskId"
          data-testid="molecule-view-results-now"
          @click="goToResults"
        >
          {{ t('design.molecule.viewResultsNow') }}
        </a-button>
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
        </div>
        <aside class="design-workbench__context">
          <MoleculeDesignContextPanel
            :model-name="selectedOption?.name || selectedSlug"
            :mode-label="contextModeLabel"
            :pocket-label="pocketLabelText"
            :pocket-center="activeCenter"
            :pocket-box-size="activeBoxSize"
            :preview-scene="contextPreviewScene"
            :sample-count="contextSampleCount"
            :fragment-summary="contextFragmentSummary"
            :steps="contextSteps"
            :missing-items="contextMissingItems"
            :can-submit="canSubmit"
            @jump-to="scrollToSection"
          />
        </aside>
      </div>
    </a-spin>
  </main>
  <FragmentSketchModal
    v-if="generationMode === 'fragment' || generationMode === 'dock'"
    v-model:open="sketchModalOpen"
    :molecule="fragmentMolecule"
    :selected-indices="activeSketchSelection"
    :mode="generationMode === 'dock' ? 'dock' : 'fragment'"
    @confirm="handleSketchConfirm"
  />
  <TaskProgressCard
    v-if="submittedTaskId"
    :key="submittedTaskId"
    :task-id="submittedTaskId"
    :task-name="t('design.molecule.taskName')"
    @close="submittedTaskId = null"
  />
</template>

<script setup lang="ts">
  import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import PocketPicker from './components/PocketPicker.vue'
  import ModelSelect from '@/components/design/ModelSelect.vue'
  import ModelParameterForm from '@/components/design/ModelParameterForm.vue'
  import ParameterPresets from '@/components/design/ParameterPresets.vue'
  import FragmentSketchModal from '@/components/design/FragmentSketchModal.vue'
  import MoleculeInlineFragmentCard from '@/components/design/MoleculeInlineFragmentCard.vue'
  import MoleculeDesignContextPanel from '@/components/design/MoleculeDesignContextPanel.vue'
  import TaskProgressCard from '@/components/tasks/TaskProgressCard.vue'
  import { useModelOptions } from '@/composables/useModelOptions'
  import { useRequestSequence } from '@/composables/useRequestSequence'
  import { resolveToolBySlug, submitDesignTask } from '@/api/design'
  import { uploadProjectArtifact } from '@/api/artifacts'
  import { uploadFile } from '@/api/files'
  import { listProjects } from '@/api/projects'
  import { parsePocketGeometry } from '@/domain/pockets/pocket-geometry'
  import {
    formatAtomIndices,
    parseAtomIndices,
    parseFragmentMolecule,
    type FragmentMolecule
  } from '@/domain/molecules/fragment-graph'
  import { createSampleDesignFiles } from '@/domain/molecules/sample-inputs'
  import type { VisualizationScene } from '@/domain/tasks'
  import {
    buildDefaultValues,
    normalizeParameters,
    validateParameters,
    type ParameterValues
  } from '@/domain/tools/parameterSchema'
  import type { DesignPocketSelection, ResolvedDesignTool } from '@/types/design'
  import type { ResearchProject } from '@/types/projects'
  import type { ToolSchema } from '@/types/models'
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
  const uploadProjectId = ref<string>('')
  const structureFile = ref<File | null>(null)
  const pocketFile = ref<File | null>(null)
  const uploadCenter = ref<{ x: number; y: number; z: number } | null>(null)
  const uploadBoxSize = ref<{ x: number; y: number; z: number } | null>(null)
  const pocketParsing = ref(false)
  const pocketSequence = useRequestSequence()
  let parsedPocketFile: File | null = null

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
  const modeTitles = {
    denovo: 'generationModeDenovo',
    fragment: 'generationModeFragment',
    dock: 'generationModeDock'
  } as const
  type GenerationMode = keyof typeof modeTitles
  const schema = computed(() => selectedOption.value?.parameterSchema ?? null)
  const generationModes = computed(() => {
    const field = schema.value?.properties?.generation_mode
    return field
      ? (Object.keys(modeTitles) as GenerationMode[]).filter(mode => !field.enum || field.enum.includes(mode))
      : []
  })
  const supportsGenerationMode = computed(() => generationModes.value.length > 0)
  const modeParamKeys = computed(() => supportsGenerationMode.value ? ['generation_mode', 'atoms_to_dock'] : [])
  const generationMode = ref<GenerationMode>('denovo')
  const fragmentFile = ref<File | null>(null)
  const fragmentUpload = ref<File | null>(null)
  const originalFragmentUpload = ref<File | null>(null)
  const fragmentMolecule = ref<FragmentMolecule | null>(null)
  const fragmentSelectedIndices = ref<number[]>([])
  const fragmentSubsetCropped = ref(false)
  const sketchModalOpen = ref(false)
  const fragmentCount = ref<number | null>(null)
  const fragmentParsing = ref(false)
  const fragmentError = ref('')
  const atomsToDock = ref('')
  const fragmentSequence = useRequestSequence()
  const needsLigandFile = computed(() => supportsGenerationMode.value && generationMode.value !== 'denovo')
  const fragmentIssue = computed(() => fragmentError.value || (!fragmentFile.value ? 'design.molecule.fragmentRequired' : ''))
  const atomsInvalid = computed(() => {
    const value = atomsToDock.value.trim()
    if (!value || generationMode.value !== 'dock') return false
    return !parseAtomIndices(value, fragmentCount.value).valid
  })
  const activeSketchSelection = computed<number[]>(() => {
    if (generationMode.value === 'dock') {
      const parsed = parseAtomIndices(atomsToDock.value, fragmentCount.value)
      return parsed.valid ? parsed.indices : []
    }
    return fragmentSelectedIndices.value
  })
  const moleculeSizePresets = [
    { id: 'auto', value: '' },
    { id: 'small', value: 'uniform_12_20' },
    { id: 'medium', value: 'uniform_20_30' },
    { id: 'large', value: 'uniform_30_40' }
  ]

  function clearFragment(): void {
    fragmentSequence.next()
    fragmentFile.value = null
    fragmentUpload.value = null
    originalFragmentUpload.value = null
    fragmentMolecule.value = null
    fragmentSelectedIndices.value = []
    fragmentSubsetCropped.value = false
    sketchModalOpen.value = false
    fragmentCount.value = null
    fragmentParsing.value = false
    fragmentError.value = ''
    atomsToDock.value = ''
  }

  function resetGeneration(): void {
    generationMode.value = generationModes.value.find(mode => mode === schema.value?.properties?.generation_mode?.default)
      ?? generationModes.value[0] ?? 'denovo'
    clearFragment()
  }

  watch(generationMode, mode => {
    if (mode === 'denovo') {
      clearFragment()
      return
    }
    fragmentSubsetCropped.value = false
    if (originalFragmentUpload.value) fragmentUpload.value = originalFragmentUpload.value
    if (mode === 'fragment') {
      atomsToDock.value = ''
      fragmentSelectedIndices.value = fragmentMolecule.value ? fragmentMolecule.value.atoms.map(atom => atom.index) : []
    }
  }, { flush: 'sync' })

  async function handleFragmentFile(file: File): Promise<false> {
    clearFragment()
    const seq = fragmentSequence.next()
    fragmentFile.value = file
    fragmentParsing.value = true
    const extension = file.name.split('.').pop()?.toLowerCase()
    try {
      const text = await file.text()
      if (!fragmentSequence.isCurrent(seq)) return false
      const lines = text.split(/\r?\n/)
      let resolvedUpload: File | null = null
      if (extension === 'pdb') {
        const count = lines.filter(line => /^(ATOM|HETATM)/.test(line)).length
        if (count > 0) {
          fragmentCount.value = count
          resolvedUpload = file
        } else {
          fragmentError.value = 'design.molecule.fragmentUnreadable'
        }
      } else if (extension === 'mol2') {
        const hasTripos = /@<TRIPOS>MOLECULE/i.test(text)
        const atomIndex = lines.findIndex(line => line.trim().toUpperCase() === '@<TRIPOS>ATOM')
        const nextSection = atomIndex >= 0
          ? lines.slice(atomIndex + 1).findIndex(line => line.trim().startsWith('@<TRIPOS>'))
          : -1
        if (atomIndex >= 0) {
          const slice = nextSection >= 0
            ? lines.slice(atomIndex + 1, atomIndex + 1 + nextSection)
            : lines.slice(atomIndex + 1)
          const count = slice.filter(line => line.trim().length > 0).length
          if (count > 0) fragmentCount.value = count
        }
        if (hasTripos) {
          resolvedUpload = file
        } else {
          fragmentError.value = 'design.molecule.fragmentUnreadable'
        }
      } else {
        const countsLine = lines[3] ?? ''
        const count = /V2000\s*$/.test(countsLine) ? Number(countsLine.slice(0, 3)) : 0
        if (Number.isInteger(count) && count > 0) fragmentCount.value = count
        if (extension === 'sdf' && lines.some(line => line.trim() === '$$$$')) {
          resolvedUpload = file
        } else if (extension === 'mol' && /V(?:2000|3000)\s*$/.test(countsLine) && /(?:^|\n)M  END\s*$/.test(text)) {
          // Wrap the MOL block as a single SD record without changing bonds or atom order.
          resolvedUpload = new File([`${text.trimEnd()}\n$$$$\n`], file.name.replace(/\.mol$/i, '.sdf'), {
            type: 'chemical/x-mdl-sdfile'
          })
        } else {
          fragmentError.value = 'design.molecule.fragmentUnreadable'
        }
      }
      if (resolvedUpload) {
        originalFragmentUpload.value = resolvedUpload
        fragmentUpload.value = resolvedUpload
        const parsed = parseFragmentMolecule(text, file.name)
        fragmentMolecule.value = parsed
        if (parsed) {
          if (fragmentCount.value === null) fragmentCount.value = parsed.atoms.length
          fragmentSelectedIndices.value = parsed.atoms.map(atom => atom.index)
        }
      }
    } catch {
      if (fragmentSequence.isCurrent(seq)) fragmentError.value = 'design.molecule.fragmentUnreadable'
    } finally {
      if (fragmentSequence.isCurrent(seq)) fragmentParsing.value = false
    }
    return false
  }

  function handleSketchConfirm(payload: { selectedIndices: number[]; exportedFile: File | null }): void {
    if (generationMode.value === 'dock') {
      atomsToDock.value = formatAtomIndices(payload.selectedIndices)
      return
    }
    fragmentSelectedIndices.value = [...payload.selectedIndices]
    if (payload.exportedFile) {
      fragmentUpload.value = payload.exportedFile
      fragmentSubsetCropped.value = true
    } else if (originalFragmentUpload.value) {
      fragmentUpload.value = originalFragmentUpload.value
      fragmentSubsetCropped.value = false
    }
  }

  const effectiveParams = computed<ParameterValues>(() => ({
    ...form.params,
    ...(supportsGenerationMode.value ? { generation_mode: generationMode.value } : {}),
    ...(generationMode.value === 'dock' && schema.value?.properties?.atoms_to_dock
      ? { atoms_to_dock: atomsToDock.value.trim() }
      : {})
  }))
  const parameterErrors = computed(() => validateParameters(schema.value, effectiveParams.value))

  /** 提交成功后保留在当前页展示实时进度，而不是直接把用户踢到结果页。 */
  const submittedTaskId = ref<string | null>(null)

  /** 常用参数展开、其余收进「高级参数」；键名不存在时分组自然为空。 */
  const PRIMARY_PARAM_KEYS = ['temperature', 'num_samples', 'n_samples', 'n_steps', 'molecule_size']

  const PARAM_STORAGE_PREFIX = 'design:molecule-params:'
  const presetStorageKey = computed(() => `design:parameter-presets:${selectedSlug.value}`)
  const paramStorageKey = computed(() => `${PARAM_STORAGE_PREFIX}${selectedSlug.value}`)

  interface StoredMoleculeParams {
    sourceMode: 'project' | 'upload'
    /** 上传模式下选过的目标项目；恢复时一并带回，避免用户重新选一次。 */
    uploadProjectId: string
    params: ParameterValues
  }

  function readStoredParams(): StoredMoleculeParams | null {
    if (typeof localStorage === 'undefined') return null
    try {
      const raw = localStorage.getItem(paramStorageKey.value)
      if (!raw) return null
      const parsed = JSON.parse(raw) as Partial<StoredMoleculeParams>
      if (!parsed || typeof parsed !== 'object' || !parsed.params) return null
      return {
        sourceMode: parsed.sourceMode === 'upload' ? 'upload' : 'project',
        uploadProjectId:
          typeof parsed.uploadProjectId === 'string' ? parsed.uploadProjectId : '',
        params: { ...parsed.params }
      }
    } catch {
      return null
    }
  }

  function persistParams(): void {
    if (typeof localStorage === 'undefined') return
    const storedParams: ParameterValues = {}
    for (const [key, value] of Object.entries(form.params)) {
      // 中心坐标来自当前口袋，不属于「用户配置」，不写入记忆。
      if (key.startsWith('center_') || modeParamKeys.value.includes(key)) continue
      storedParams[key] = value
    }
    try {
      localStorage.setItem(
        paramStorageKey.value,
        JSON.stringify({
          sourceMode: sourceMode.value,
          uploadProjectId: uploadProjectId.value,
          params: storedParams
        })
      )
    } catch {
      // 存储不可用时不阻断提交。
    }
  }

  /** 只接受当前 schema 声明的键，避免旧模型的历史参数污染新模型。 */
  function schemaOnly(values: ParameterValues): ParameterValues {
    const properties = selectedOption.value?.parameterSchema?.properties ?? {}
    const allowed = new Set(Object.keys(properties))
    const next: ParameterValues = {}
    for (const [key, value] of Object.entries(values)) {
      if (key.startsWith('center_') || modeParamKeys.value.includes(key)) continue
      if (allowed.size > 0 && !allowed.has(key)) continue
      next[key] = value
    }
    return next
  }

  function queryParamHints(): ParameterValues {
    const hints: ParameterValues = {}
    const properties = selectedOption.value?.parameterSchema?.properties ?? {}
    for (const key of Object.keys(properties)) {
      if (modeParamKeys.value.includes(key)) continue
      const raw = route.query[key]
      const value = Array.isArray(raw) ? raw[0] : raw
      if (typeof value !== 'string' || value.trim() === '') continue
      const parsed = Number(value)
      if (Number.isFinite(parsed)) hints[key] = parsed
    }
    return hints
  }

  function applyDefaults(option: { parameterSchema: ToolSchema | null } | null): void {
    const defaults = buildDefaultValues(option?.parameterSchema ?? null, { omit: modeParamKeys.value })
    const stored = readStoredParams()
    const restored = stored ? schemaOnly(stored.params) : {}
    const explicit = defaultProjectId.value
    if (stored) {
      if (!explicit && stored.uploadProjectId) uploadProjectId.value = stored.uploadProjectId
      if (!explicit) sourceMode.value = stored.sourceMode
    }
    if (explicit) uploadProjectId.value = explicit
    form.params = { ...defaults, ...restored, ...queryParamHints() }
    resetGeneration()
  }

  function resetParams(): void {
    if (typeof localStorage !== 'undefined') {
      try {
        localStorage.removeItem(paramStorageKey.value)
      } catch {
        // ignore
      }
    }
    form.params = buildDefaultValues(schema.value, { omit: modeParamKeys.value })
    resetGeneration()
    message.success(t('design.molecule.paramsReset'))
  }

  function handlePresetLoad(params: ParameterValues): void {
    form.params = { ...form.params, ...schemaOnly(params) }
  }

  const hiddenParams = computed<Record<string, ParameterFieldOverride>>(() => ({
    center_x: { hidden: true },
    center_y: { hidden: true },
    center_z: { hidden: true },
    ...(supportsGenerationMode.value
      ? {
          generation_mode: { hidden: true },
          atoms_to_dock: { hidden: true },
          ...(generationMode.value === 'dock' ? { molecule_size: { hidden: true } } : {})
        }
      : {})
  }))

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
          (sourceMode.value !== 'upload' || uploadProjectId.value) &&
          !resolving.value &&
          !pocketParsing.value &&
          (!needsLigandFile.value || Boolean(fragmentUpload.value)) &&
          !atomsInvalid.value &&
          structureReady.value &&
          hasCenter.value &&
          parameterErrors.value.length === 0
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
    const seq = pocketSequence.next()
    pocketFile.value = file
    parsedPocketFile = file
    pocketParsing.value = true
    uploadCenter.value = null
    uploadBoxSize.value = null
    try {
      const geometry = parsePocketGeometry(await file.text())
      if (!pocketSequence.isCurrent(seq) || parsedPocketFile !== file || pocketFile.value !== file) return false
      if (!geometry) throw new Error('invalid geometry')
      uploadCenter.value = geometry.center
      uploadBoxSize.value = geometry.boxSize
    } catch {
      if (pocketSequence.isCurrent(seq) && parsedPocketFile === file) message.warning(t('design.molecule.pocketFileUnreadable'))
    } finally {
      if (pocketSequence.isCurrent(seq) && parsedPocketFile === file) pocketParsing.value = false
    }
    return false
  }

  function validate(): string | null {
    if (needsLigandFile.value && !fragmentUpload.value) return t(fragmentIssue.value || 'design.molecule.fragmentRequired')
    if (atomsInvalid.value) return t('design.molecule.atomsToDockInvalid')
    if (!structureReady.value) {
      return t('design.molecule.pocketMissingFile')
    }
    if (sourceMode.value === 'upload' && !uploadProjectId.value) {
      return t('design.molecule.needProject')
    }
    if (!hasCenter.value) {
      return t('design.molecule.pocketMissingCenter')
    }
    if (parameterErrors.value.length > 0) return t('design.molecule.invalidNum')
    return null
  }

  const loadSequence = useRequestSequence()

  async function loadTool(): Promise<void> {
    const seq = loadSequence.next()
    const slug = selectedSlug.value
    resolving.value = true
    toolError.value = false
    try {
      const tool = await resolveToolBySlug(slug)
      if (loadSequence.isCurrent(seq) && selectedSlug.value === slug) {
        resolvedTool.value = tool
        toolError.value = !tool
      }
    } catch {
      if (loadSequence.isCurrent(seq) && selectedSlug.value === slug) {
        resolvedTool.value = null
        toolError.value = true
      }
    } finally {
      if (loadSequence.isCurrent(seq) && selectedSlug.value === slug) resolving.value = false
    }
  }

  async function handleSubmit(): Promise<void> {
    if (submitting.value || resolving.value || pocketParsing.value || fragmentParsing.value) return
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
    const projectId = sourceMode.value === 'upload' ? uploadProjectId.value : pocketSelection.value?.projectId ?? ''
    const snapshot = {
      projectId,
      toolId: resolvedTool.value.tool.id,
      toolVersionId: resolvedTool.value.version.id,
      params: {
        ...normalizeParameters(schema.value, effectiveParams.value),
        center_x: toNumber(center?.x, 0),
        center_y: toNumber(center?.y, 0),
        center_z: toNumber(center?.z, 0)
      },
      structureFile: sourceMode.value === 'upload' ? structureFile.value : null,
      proteinFileId: pocketSelection.value?.structureFileId ?? '',
      fragmentFile: needsLigandFile.value ? fragmentUpload.value : null,
      name: t('design.molecule.taskName')
    }

    submitting.value = true
    try {
      let proteinPdbFileId = snapshot.proteinFileId
      const fragmentFileId = snapshot.fragmentFile ? (await uploadFile(snapshot.fragmentFile)).data.id : ''
      if (snapshot.structureFile) {
        proteinPdbFileId = (await uploadFile(snapshot.structureFile)).data.id
        if (snapshot.projectId) {
          void uploadProjectArtifact(snapshot.projectId, {
            file: snapshot.structureFile,
            artifact_type: 'protein_structure',
            semantic_type: 'protein_structure',
            standard_type: 'protein_structure',
            standard_version: 1,
          }).catch(() => {
            message.warning(t('design.molecule.archiveStructureFailed'))
          })
        }
      }
      const taskInput = {
        name: snapshot.name,
        projectId: snapshot.projectId,
        toolId: snapshot.toolId,
        toolVersionId: snapshot.toolVersionId,
        params: snapshot.params,
        standardInputUploads: { protein_pdb: proteinPdbFileId }
      }
      const response = await submitDesignTask(fragmentFileId ? {
        ...taskInput,
        standardInputUploads: { ...taskInput.standardInputUploads, fragment_sdf: fragmentFileId }
      } : taskInput)
      persistParams()
      submittedTaskId.value = response.data.id
      message.success(t('design.molecule.submittedStay'))
    } catch {
      message.error(t('design.molecule.failed'))
    } finally {
      submitting.value = false
    }
  }

  function goToResults(): void {
    if (!submittedTaskId.value) return
    void router.push({ name: 'GenerationResults', params: { id: submittedTaskId.value } })
  }

  watch(
    selectedOption,
    option => {
      applyDefaults(option)
    },
    { immediate: true }
  )

  async function handleLoadSample(): Promise<void> {
    const sample = createSampleDesignFiles()
    sourceMode.value = 'upload'
    if (!uploadProjectId.value) {
      uploadProjectId.value = projectOptions.value[0]?.value ?? pocketSelection.value?.projectId ?? ''
    }
    structureFile.value = sample.receptorFile
    pocketFile.value = sample.pocketFile
    parsedPocketFile = sample.pocketFile
    uploadCenter.value = sample.pocketCenter
    uploadBoxSize.value = sample.pocketBoxSize
    if (needsLigandFile.value) {
      await handleFragmentFile(sample.ligandFile)
    }
    message.success(t('design.molecule.sampleLoaded'))
  }

  let uploadStructureUrl = ''
  function revokeUploadUrl(): void {
    if (uploadStructureUrl && typeof URL !== 'undefined' && typeof URL.revokeObjectURL === 'function') {
      URL.revokeObjectURL(uploadStructureUrl)
    }
    uploadStructureUrl = ''
  }

  watch(structureFile, file => {
    revokeUploadUrl()
    if (file && typeof URL !== 'undefined' && typeof URL.createObjectURL === 'function') {
      uploadStructureUrl = URL.createObjectURL(file)
    }
  })

  onBeforeUnmount(() => revokeUploadUrl())

  const contextPreviewScene = computed<VisualizationScene | null>(() => {
    if (sourceMode.value === 'project') {
      const fileId = pocketSelection.value?.structureFileId
      if (!fileId) return null
      const urn = (pocketSelection.value?.structureUrn ?? '').toLowerCase()
      const isCif = urn.endsWith('.cif') || urn.endsWith('.mmcif')
      const entry = {
        key: `context-pocket-${fileId}`,
        url: `/api/v1/files/${encodeURIComponent(fileId)}/download`,
        label: pocketSelection.value?.pocketLabel || 'receptor',
        source: 'input' as const,
        role: 'receptor' as const,
        format: isCif ? ('mmcif' as const) : ('pdb' as const),
        extension: isCif ? '.cif' : '.pdb'
      }
      return {
        entries: [entry],
        inputEntries: [entry],
        outputEntries: [],
        supportedOutputFiles: [],
        unsupportedOutputFiles: [],
        hasRenderableOutput: true,
        selectedOutputKey: entry.key
      }
    }
    if (!structureFile.value || !uploadStructureUrl) return null
    const lower = structureFile.value.name.toLowerCase()
    const isCif = lower.endsWith('.cif') || lower.endsWith('.mmcif')
    const entry = {
      key: `context-upload-${structureFile.value.name}`,
      url: uploadStructureUrl,
      label: structureFile.value.name,
      source: 'input' as const,
      role: 'receptor' as const,
      format: isCif ? ('mmcif' as const) : ('pdb' as const),
      extension: isCif ? '.cif' : '.pdb'
    }
    return {
      entries: [entry],
      inputEntries: [entry],
      outputEntries: [],
      supportedOutputFiles: [],
      unsupportedOutputFiles: [],
      hasRenderableOutput: true,
      selectedOutputKey: entry.key
    }
  })

  const contextModeLabel = computed(() => {
    if (!supportsGenerationMode.value) return t('modelParams.options.generationModeDenovo')
    return t(`modelParams.options.${modeTitles[generationMode.value]}`)
  })

  const contextSampleCount = computed(() => {
    const val = form.params.n_samples ?? form.params.num_samples
    return typeof val === 'number' || typeof val === 'string' ? val : null
  })

  const contextFragmentSummary = computed(() => {
    if (!needsLigandFile.value || !fragmentFile.value) return undefined
    const total = fragmentCount.value ?? fragmentMolecule.value?.atoms.length ?? 0
    if (generationMode.value === 'dock') {
      const selected = activeSketchSelection.value.length
      return selected > 0
        ? t('design.molecule.dockSummary', { selected, total })
        : t('design.molecule.dockWholeSummary', { total })
    }
    const selected = fragmentSelectedIndices.value.length || total
    return t('design.molecule.keptSummary', { selected, total })
  })

  const contextSteps = computed(() => [
    {
      id: 'model',
      title: t('design.molecule.context.stepModel'),
      done: Boolean(resolvedTool.value),
      detail: selectedOption.value?.name || selectedSlug.value
    },
    {
      id: 'input',
      title: t('design.molecule.context.stepInput'),
      done: Boolean(
        structureReady.value &&
        hasCenter.value &&
        (sourceMode.value !== 'upload' || uploadProjectId.value)
      ),
      detail: hasCenter.value ? pocketLabelText.value : undefined
    },
    {
      id: 'fragment-params',
      title: t('design.molecule.context.stepFragmentParams'),
      done: (!needsLigandFile.value || Boolean(fragmentUpload.value)) && !atomsInvalid.value && parameterErrors.value.length === 0
    }
  ])

  const contextMissingItems = computed(() => {
    const items: Array<{ id: string; label: string; targetTestId?: string }> = []
    if (!resolvedTool.value) {
      items.push({ id: 'tool', label: t('design.molecule.toolMissing'), targetTestId: 'molecule-section-model' })
    }
    if (sourceMode.value === 'upload' && !uploadProjectId.value) {
      items.push({ id: 'project', label: t('design.molecule.needProject'), targetTestId: 'molecule-section-input' })
    }
    if (!structureReady.value) {
      items.push({ id: 'structure', label: t('design.molecule.pocketMissingFile'), targetTestId: 'molecule-section-input' })
    } else if (!hasCenter.value) {
      items.push({ id: 'center', label: t('design.molecule.pocketMissingCenter'), targetTestId: 'molecule-section-input' })
    }
    if (needsLigandFile.value && !fragmentUpload.value) {
      items.push({ id: 'fragment', label: t(fragmentIssue.value || 'design.molecule.fragmentRequired'), targetTestId: 'molecule-fragment-section' })
    }
    if (atomsInvalid.value) {
      items.push({ id: 'atoms', label: t('design.molecule.atomsToDockInvalid'), targetTestId: 'molecule-fragment-section' })
    }
    if (parameterErrors.value.length > 0) {
      items.push({ id: 'params', label: t('design.molecule.invalidNum'), targetTestId: 'molecule-section-params' })
    }
    return items
  })

  function scrollToSection(targetTestId: string): void {
    if (typeof document === 'undefined') return
    const target = document.querySelector(`[data-testid="${targetTestId}"]`)
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

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

  .mode-cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
    gap: 12px;
    width: 100%;

    :deep(.ant-radio-button-wrapper) {
      height: auto;
      padding: 12px 14px;
      white-space: normal;
      text-align: left;
      background: @bg-elevated;
      border: 1px solid @border-color;
      border-radius: @border-radius-md;
      transition: all @transition-fast;

      &::before {
        display: none;
      }

      &:hover {
        border-color: @border-color-hover;
      }

      &.ant-radio-button-wrapper-checked {
        border-color: @accent-color;
        background: @accent-color-light;
        box-shadow: 0 0 0 1px @accent-color-border;

        .mode-card__title {
          color: @accent-color;
        }
      }
    }
  }

  .mode-card__body {
    display: flex;
    flex-direction: column;
    gap: 6px;
    width: 100%;
  }

  .mode-card__title {
    display: block;
    color: @text-primary;
    font-size: @font-size-sm;
    font-weight: @font-weight-semibold;
    line-height: 1.4;
  }

  .mode-card__desc {
    display: block;
    color: @text-secondary;
    font-size: @font-size-xs;
    font-weight: @font-weight-regular;
    line-height: 1.5;
  }

  .fragment-hint {
    margin: 0 0 12px;
    color: @text-secondary;
    font-size: @font-size-sm;
    line-height: 1.5;
  }

  .fragment-presets {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 16px;
  }

  .fragment-alert,
  .fragment-dock-field {
    margin-top: 12px;
  }

  .fragment-preview {
    margin-top: 8px;
    color: @text-secondary;
    font-size: @font-size-sm;
  }

  .design-page {
    max-width: @page-max-width;
    margin: 0 auto;
    padding: 32px 24px 48px;
  }

  .design-workbench {
    display: grid;
    grid-template-columns: minmax(0, 1.35fr) minmax(340px, 0.9fr);
    gap: 24px;
    align-items: start;
  }

  .design-workbench__main {
    min-width: 0;
  }

  .design-workbench__context {
    min-width: 0;
    position: sticky;
    top: 20px;
  }

  @media (max-width: 1180px) {
    .design-workbench {
      grid-template-columns: minmax(0, 1fr);
    }

    .design-workbench__context {
      position: static;
    }
  }

  .section-header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 16px;

    .design-section__title {
      margin-bottom: 0;
    }
  }

  .fragment-cropped-tag {
    display: inline-block;
    margin-left: 8px;
    padding: 1px 8px;
    border-radius: 999px;
    background: @accent-color-light;
    color: @accent-color;
    font-size: @font-size-xs;
  }

  .fragment-inline-card {
    margin-top: 12px;
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

  .param-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 16px;

    .design-section__title {
      margin-bottom: 0;
    }
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
