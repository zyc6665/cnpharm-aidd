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

            <div class="input-stack">
              <!-- 1. 统一归档项目 -->
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

              <!-- 2. 蛋白结构来源（从项目结构选 / 本地上传） -->
              <div class="input-block">
                <div class="input-block__header">
                  <span class="source-label">{{ t('design.molecule.receptorSource') }}</span>
                  <a-radio-group
                    v-model:value="sourceMode"
                    size="small"
                    button-style="solid"
                    :disabled="submitting"
                    data-testid="molecule-source-mode"
                  >
                    <a-radio-button value="project">{{ t('design.molecule.sourceProject') }}</a-radio-button>
                    <a-radio-button value="upload">{{ t('design.molecule.sourceUpload') }}</a-radio-button>
                  </a-radio-group>
                </div>

                <div v-if="sourceMode === 'project'" class="source-body">
                  <PocketPicker
                    v-model="pocketSelection"
                    :default-project-id="defaultProjectId"
                    :project-id="uploadProjectId"
                    :initial-target-id="initialTargetId"
                    :initial-protein-id="initialProteinId"
                    :initial-structure-id="initialStructureId"
                    :initial-pocket-id="initialPocketId"
                    hide-project-select
                    :hide-pocket-select="activePocketMode !== 'project'"
                    @structure-change="handleProjectStructureChange"
                  />
                </div>

                <div v-else class="source-body" data-testid="molecule-upload-source">
                  <div class="source-field">
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
                    <div v-if="detectedHetatm" class="hetatm-banner" data-testid="molecule-hetatm-banner">
                      <span class="hetatm-banner__text">
                        {{ t('design.molecule.hetatmDetected', { count: detectedHetatm.pointCount }) }}
                      </span>
                      <a-button
                        type="link"
                        size="small"
                        data-testid="molecule-use-hetatm-center"
                        @click="applyDetectedHetatmCenter"
                      >
                        {{ t('design.molecule.useHetatmCenter') }}
                      </a-button>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 3. 口袋定位方式（与蛋白来源完全解耦，可任意组合） -->
              <div class="input-block">
                <PocketCoordinatePanel
                  ref="pocketPanelRef"
                  v-model="pocketDefineMode"
                  :allow-project-mode="sourceMode === 'project'"
                  :disabled="submitting"
                  @change="handlePocketStateChange"
                />
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
          v-if="fragmentMolecule && !fragmentParsing && generationMode === 'fragment'"
          class="fragment-inline-card"
          :filename="fragmentFile?.name || fragmentMolecule.name"
          :atoms="fragmentMolecule.atoms"
          :bonds="fragmentMolecule.bonds"
          :selected-indices="activeSketchSelection"
          mode="fragment"
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
        :message="pocketCenterMissingMessage"
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
        <div
          v-if="schema?.properties?.molecule_size"
          class="param-size-presets"
          data-testid="molecule-size-presets"
        >
          <div class="param-size-presets__row">
            <span class="source-label">{{ t('design.molecule.moleculeSize') }}</span>
            <div class="param-size-presets__buttons">
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
          </div>
          <span class="source-hint">{{ t('design.molecule.moleculeSizeHint') }}</span>
        </div>
        <!-- 参数是从上次提交的记忆里恢复的：明确告诉用户哪些值和默认不同，
             并给一个一键回到默认的出口，避免「怎么和我以为的不一样」 -->
        <a-alert
          v-if="restoredFromMemory"
          type="info"
          show-icon
          class="param-restored-alert"
          :message="t('design.molecule.paramsRestored')"
          :description="t('design.molecule.paramsRestoredDiff', { fields: restoredDiffLabel })"
          data-testid="params-restored-hint"
        >
          <template #action>
            <a-button size="small" type="link" data-testid="params-restored-reset" @click="resetParams">
              {{ t('design.molecule.resetToDefault') }}
            </a-button>
          </template>
        </a-alert>
        <ParameterPresets
          v-if="selectedOption?.parameterSchema && userId"
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
        <p class="param-hint">{{ t('design.molecule.paramHint', { model: selectedOption?.name || selectedSlug || 'Pocket2Mol' }) }}</p>
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
    v-if="generationMode === 'fragment'"
    v-model:open="sketchModalOpen"
    :molecule="fragmentMolecule"
    :selected-indices="activeSketchSelection"
    mode="fragment"
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
  import { useUserStore } from '@/stores/user'
  import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import PocketPicker from './components/PocketPicker.vue'
  import PocketCoordinatePanel, {
    type PocketCoordinateState,
    type PocketDefineMode
  } from '@/components/design/PocketCoordinatePanel.vue'
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
  import {
    extractProteinHetatmPocketGeometry,
    parsePocketGeometry,
    type PocketGeometry
  } from '@/domain/pockets/pocket-geometry'
  import { type FragmentMolecule } from '@/domain/molecules/fragment-graph'
  import { parseAndNormalizeLigandUpload } from '@/domain/molecules/ligand-upload'
  import { createSampleDesignFiles } from '@/domain/molecules/sample-inputs'
  import type { VisualizationScene } from '@/domain/tasks'
  import {
    buildDefaultValues,
    normalizeParameters,
    validateParameters,
    describeParameterError,
    type ParameterValues
  } from '@/domain/tools/parameterSchema'
  import type {
    DesignPocketSelection,
    DesignStructureSelection,
    ResolvedDesignTool
  } from '@/types/design'
  import type { ResearchProject } from '@/types/projects'
  import type { ToolSchema } from '@/types/models'
  import type { ParameterFieldOverride } from '@/components/design/ModelParameterForm.vue'
  import { MOLECULE_GENERATION_TOOL_SLUG } from '@/types/design'

  const router = useRouter()
  const route = useRoute()
  const { t } = useI18n()
  const userStore = useUserStore()

  const props = withDefaults(defineProps<{ initialProjectId?: string }>(), {
    initialProjectId: ''
  })

  const queryString = (value: unknown): string => (typeof value === 'string' ? value.trim() : '')

  const defaultProjectId = computed(() => {
    if (props.initialProjectId) return props.initialProjectId
    return queryString(route.query.project_id)
  })
  const initialTargetId = computed(() => queryString(route.query.target_id))
  const initialProteinId = computed(() => queryString(route.query.protein_id))
  const initialStructureId = computed(() => queryString(route.query.structure_id))
  const initialPocketId = computed(() => queryString(route.query.pocket_id))
  const hasPocketHandoffQuery = computed(() =>
    Boolean(
      initialTargetId.value ||
        initialProteinId.value ||
        initialStructureId.value ||
        initialPocketId.value
    )
  )

  const resolving = ref(false)
  const submitting = ref(false)
  const resolvedTool = ref<ResolvedDesignTool | null>(null)
  const toolError = ref(false)
  const pocketSelection = ref<DesignPocketSelection | null>(null)
  const projectStructure = ref<DesignStructureSelection | null>(null)

  /**
   * 输入模型：
   * 1. 归档项目统一选定；
   * 2. 蛋白结构来源（项目结构 / 本地上传）与口袋定位方式（项目已有口袋 / 参考配体 / 中心坐标 / 口袋文件）正交解耦，
   *    因此选了项目里的蛋白质后，依然可以直接上传参考配体或输入中心坐标。
   */
  const sourceMode = ref<'project' | 'upload'>('project')
  const pocketPanelRef = ref<InstanceType<typeof PocketCoordinatePanel> | null>(null)
  const pocketDefineMode = ref<PocketDefineMode>('project')
  const pocketPanelState = ref<PocketCoordinateState>({
    mode: 'project',
    center: null,
    boxSize: null,
    label: '-',
    parsing: false,
    hasAnyInput: false,
    refLigandFile: null,
    refLigandUpload: null,
    pocketFile: null
  })
  const activePocketMode = computed<PocketDefineMode>(() =>
    sourceMode.value === 'upload' && pocketDefineMode.value === 'project'
      ? 'ref_ligand'
      : pocketDefineMode.value
  )

  const activeProjectStructure = computed<DesignStructureSelection | null>(() => {
    if (projectStructure.value) return projectStructure.value
    if (!pocketSelection.value) return null
    return {
      projectId: pocketSelection.value.projectId,
      targetId: pocketSelection.value.targetId,
      proteinId: pocketSelection.value.proteinId,
      structureId: pocketSelection.value.structureId,
      structureFileId: pocketSelection.value.structureFileId,
      structureUrn: pocketSelection.value.structureUrn
    }
  })

  const projects = ref<ResearchProject[]>([])
  const uploadProjectId = ref<string>('')
  const activeProjectId = computed(() =>
    uploadProjectId.value || activeProjectStructure.value?.projectId || ''
  )
  const structureFile = ref<File | null>(null)
  const detectedHetatm = ref<PocketGeometry | null>(null)
  const hetatmCoordsApplied = ref(false)
  const structureSequence = useRequestSequence()
  let parsedStructureFile: File | null = null

  const pocketParsing = computed(() => pocketPanelState.value.parsing)
  const refLigandUpload = computed(() => pocketPanelState.value.refLigandUpload)

  const uploadStructureUrl = ref<string | null>(null)
  const uploadLigandUrl = ref<string | null>(null)
  const uploadRefLigandUrl = ref<string | null>(null)

  function revokeObjectUrl(urlRef: { value: string | null }): void {
    if (urlRef.value && typeof URL !== 'undefined' && typeof URL.revokeObjectURL === 'function') {
      URL.revokeObjectURL(urlRef.value)
    }
    urlRef.value = null
  }

  function revokeUploadUrl(): void {
    revokeObjectUrl(uploadStructureUrl)
  }

  function revokeLigandUrl(): void {
    revokeObjectUrl(uploadLigandUrl)
  }

  function revokeRefLigandUrl(): void {
    revokeObjectUrl(uploadRefLigandUrl)
  }

  function handlePocketStateChange(state: PocketCoordinateState): void {
    pocketPanelState.value = state
    if (!state.center || state.mode !== 'coords') {
      hetatmCoordsApplied.value = false
    }
  }

  function handleProjectStructureChange(value: DesignStructureSelection | null): void {
    projectStructure.value = value
  }

  watch(sourceMode, (mode, prevMode) => {
    if (mode === 'upload' && pocketDefineMode.value === 'project') {
      pocketDefineMode.value = 'ref_ligand'
    } else if (mode === 'project' && prevMode === 'upload') {
      detectedHetatm.value = null
      hetatmCoordsApplied.value = false
      pocketPanelRef.value?.clearCoordinates()
      if (pocketSelection.value) {
        pocketDefineMode.value = 'project'
      }
    }
  }, { flush: 'sync' })

  watch(pocketSelection, sel => {
    if (!sel) return
    if (sel.projectId && !uploadProjectId.value) uploadProjectId.value = sel.projectId
    pocketDefineMode.value = 'project'
  }, { flush: 'sync' })

  function applyDetectedHetatmCenter(): void {
    if (!detectedHetatm.value) return
    pocketPanelRef.value?.setCoordinates(detectedHetatm.value.center)
    hetatmCoordsApplied.value = true
    message.success(t('design.molecule.hetatmApplied'))
  }

  const projectOptions = computed(() =>
    projects.value.map((project) => ({ label: project.name, value: project.id }))
  )

  /** 用户已选择了部分输入时显示摘要与针对性提示。 */
  const hasSelection = computed(() =>
    Boolean(
      pocketSelection.value ||
        activeProjectStructure.value?.structureFileId ||
        structureFile.value ||
        pocketPanelState.value.hasAnyInput
    )
  )

  /** 受体结构是否就位：项目模式看结构附件，上传模式看用户是否选了文件。 */
  const structureReady = computed(() =>
    sourceMode.value === 'project'
      ? Boolean(activeProjectStructure.value?.structureFileId)
      : Boolean(structureFile.value)
  )

  const pocketLabelText = computed(() =>
    activePocketMode.value === 'project'
      ? pocketSelection.value?.pocketLabel || '-'
      : pocketPanelState.value.label
  )

  const pocketCenterMissingMessage = computed(() => {
    if (activePocketMode.value === 'ref_ligand') return t('design.molecule.missingRefLigand')
    if (activePocketMode.value === 'coords') return t('design.molecule.missingCoords')
    return t('design.molecule.pocketMissingCenter')
  })

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
    fragment: 'generationModeFragment'
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
  const fragmentSequence = useRequestSequence()
  const needsLigandFile = computed(() => supportsGenerationMode.value && generationMode.value !== 'denovo')
  const fragmentIssue = computed(() => fragmentError.value || (!fragmentFile.value ? 'design.molecule.fragmentRequired' : ''))
  const activeSketchSelection = computed<number[]>(() => fragmentSelectedIndices.value)
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
    fragmentSelectedIndices.value = fragmentMolecule.value ? fragmentMolecule.value.atoms.map(atom => atom.index) : []
  }, { flush: 'sync' })

  async function handleFragmentFile(file: File): Promise<false> {
    clearFragment()
    const seq = fragmentSequence.next()
    fragmentFile.value = file
    fragmentParsing.value = true
    try {
      const text = await file.text()
      if (!fragmentSequence.isCurrent(seq)) return false
      const prepared = await parseAndNormalizeLigandUpload(file, text, { convertNonSdfToSdf: false })
      if (!fragmentSequence.isCurrent(seq)) return false
      if (!prepared || (!prepared.molecule && /V3000/i.test(text))) {
        fragmentError.value = /V3000/i.test(text)
          ? 'design.molecule.fragmentV3000Unsupported'
          : 'design.molecule.fragmentUnreadable'
        return false
      }
      fragmentCount.value = prepared.atomCount
      originalFragmentUpload.value = prepared.uploadFile
      fragmentUpload.value = prepared.uploadFile
      fragmentMolecule.value = prepared.molecule
      if (prepared.molecule) {
        fragmentSelectedIndices.value = prepared.molecule.atoms.map(atom => atom.index)
      }
    } catch {
      if (fragmentSequence.isCurrent(seq)) fragmentError.value = 'design.molecule.fragmentUnreadable'
    } finally {
      if (fragmentSequence.isCurrent(seq)) fragmentParsing.value = false
    }
    return false
  }

  function handleSketchConfirm(payload: { selectedIndices: number[]; exportedFile: File | null }): void {
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
    ...(supportsGenerationMode.value ? { generation_mode: generationMode.value } : {})
  }))
  const parameterErrors = computed(() => validateParameters(schema.value, effectiveParams.value))
  const firstParameterError = computed(() => {
    const [error] = parameterErrors.value
    return error ? describeParameterError(schema.value, error, t) : ''
  })
  const structureMissingMessage = computed(() => t(activeProjectStructure.value?.structureId
    ? 'design.molecule.pocketMissingFile'
    : 'design.molecule.selectProteinStructure'))

  /** 提交成功后保留在当前页展示实时进度，而不是直接把用户踢到结果页。 */
  const submittedTaskId = ref<string | null>(null)

  /** 高频核心参数直接展示，采样超参统一收进「高级参数」。 */
  const PRIMARY_PARAM_KEYS = ['temperature', 'num_samples', 'n_samples']

  const userId = computed(() => userStore.userInfo?.id)
  const presetStorageKey = computed(() => `design:u:${userId.value}:parameter-presets:${selectedSlug.value}`)
  const paramStorageKey = computed(() => `design:u:${userId.value}:molecule-params:${selectedSlug.value}`)

  /** 参数来自上一次提交的记忆，且与当前 schema 默认值存在差异。 */
  const restoredFromMemory = ref(false)
  const restoredDiffKeys = ref<string[]>([])

  function paramLabel(key: string): string {
    const field = schema.value?.properties?.[key]
    const title = field && typeof field === 'object' && 'title' in field ? field.title : undefined
    return typeof title === 'string' && title ? title : key
  }

  const restoredDiffLabel = computed(() =>
    restoredDiffKeys.value.map(key => paramLabel(key)).join(', ')
  )

  interface StoredMoleculeParams {
    sourceMode: 'project' | 'upload'
    /** 上传模式下选过的目标项目；恢复时一并带回，避免用户重新选一次。 */
    uploadProjectId: string
    params: ParameterValues
  }

  function readStoredParams(): StoredMoleculeParams | null {
    if (!userId.value || typeof localStorage === 'undefined') return null
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
    if (!userId.value || typeof localStorage === 'undefined') return
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
    const diffKeys = Object.keys(restored).filter(key => restored[key] !== defaults[key])
    restoredDiffKeys.value = diffKeys
    restoredFromMemory.value = diffKeys.length > 0
    const explicit = defaultProjectId.value
    if (stored) {
      if (!explicit && stored.uploadProjectId) uploadProjectId.value = stored.uploadProjectId
      if (!explicit && !hasPocketHandoffQuery.value) sourceMode.value = stored.sourceMode
    }
    if (explicit) uploadProjectId.value = explicit
    if (hasPocketHandoffQuery.value) sourceMode.value = 'project'
    form.params = { ...defaults, ...restored, ...queryParamHints() }
    resetGeneration()
  }

  function resetParams(): void {
    if (userId.value && typeof localStorage !== 'undefined') {
      try {
        localStorage.removeItem(paramStorageKey.value)
      } catch {
        // ignore
      }
    }
    form.params = buildDefaultValues(schema.value, { omit: modeParamKeys.value })
    resetGeneration()
    restoredFromMemory.value = false
    restoredDiffKeys.value = []
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
          molecule_size: { hidden: true }
        }
      : {})
  }))

  const activeCenter = computed(() =>
    activePocketMode.value === 'project'
      ? pocketSelection.value?.center ?? null
      : pocketPanelState.value.center
  )

  const activeBoxSize = computed(() =>
    activePocketMode.value === 'project'
      ? pocketSelection.value?.boxSize ?? null
      : pocketPanelState.value.boxSize
  )

  const supportsRefLigandSlot = computed(() => {
    const slots = resolvedTool.value?.tool.contract?.artifacts?.inputs
    return Array.isArray(slots) && slots.some(slot => slot?.name === 'ref_ligand')
  })

  const supportsPocketSlot = computed(() => {
    const slots = resolvedTool.value?.tool.contract?.artifacts?.inputs
    return Array.isArray(slots) && slots.some(slot => slot?.name === 'pocket')
  })

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
          activeProjectId.value &&
          !resolving.value &&
          !pocketParsing.value &&
          !fragmentParsing.value &&
          (!needsLigandFile.value || Boolean(fragmentUpload.value)) &&
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
  async function handleStructureFile(file: File): Promise<false> {
    const seq = structureSequence.next()
    structureFile.value = file
    parsedStructureFile = file
    detectedHetatm.value = null
    if (hetatmCoordsApplied.value) {
      hetatmCoordsApplied.value = false
      pocketPanelRef.value?.clearCoordinates()
    }
    const lower = file.name.toLowerCase()
    if (!lower.endsWith('.pdb') && !lower.endsWith('.ent')) return false
    try {
      const text = await file.text()
      if (!structureSequence.isCurrent(seq) || parsedStructureFile !== file || structureFile.value !== file) {
        return false
      }
      detectedHetatm.value = extractProteinHetatmPocketGeometry(text)
    } catch {
      // 共晶配体嗅探失败不影响蛋白上传本身。
    }
    return false
  }

  function validate(): string | null {
    if (needsLigandFile.value && !fragmentUpload.value) return t(fragmentIssue.value || 'design.molecule.fragmentRequired')
    if (!activeProjectId.value) {
      return t('design.molecule.needProject')
    }
    if (!structureReady.value) {
      return structureMissingMessage.value
    }
    if (!hasCenter.value) {
      return pocketCenterMissingMessage.value
    }
    if (parameterErrors.value.length > 0) return firstParameterError.value
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
    if (
      submitting.value ||
      resolving.value ||
      pocketParsing.value ||
      fragmentParsing.value
    ) {
      return
    }
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
    const projectId = activeProjectId.value
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
      proteinFileId:
        pocketSelection.value?.structureFileId ?? activeProjectStructure.value?.structureFileId ?? '',
      fragmentFile: needsLigandFile.value ? fragmentUpload.value : null,
      refLigandFile:
        activePocketMode.value === 'ref_ligand' && supportsRefLigandSlot.value
          ? refLigandUpload.value
          : null,
      pocketFile:
        activePocketMode.value === 'pocket_file' && supportsPocketSlot.value
          ? pocketPanelState.value.pocketFile
          : null,
      name: t('design.molecule.taskName')
    }

    submitting.value = true
    try {
      let proteinPdbFileId = snapshot.proteinFileId
      const fragmentFileId = snapshot.fragmentFile ? (await uploadFile(snapshot.fragmentFile)).data.id : ''
      const refLigandFileId = snapshot.refLigandFile ? (await uploadFile(snapshot.refLigandFile)).data.id : ''
      const pocketFileId = snapshot.pocketFile ? (await uploadFile(snapshot.pocketFile)).data.id : ''
      if (snapshot.structureFile) {
        proteinPdbFileId = (await uploadFile(snapshot.structureFile)).data.id
        if (snapshot.projectId) {
          void Promise.resolve(
            uploadProjectArtifact(snapshot.projectId, {
              file: snapshot.structureFile,
              artifact_type: 'protein_structure',
              semantic_type: 'protein_structure',
              standard_type: 'protein_structure',
              standard_version: 1,
            })
          ).catch(() => {
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
      const response = await submitDesignTask(
        fragmentFileId || refLigandFileId || pocketFileId
          ? {
              ...taskInput,
              standardInputUploads: {
                ...taskInput.standardInputUploads,
                ...(pocketFileId ? { pocket: pocketFileId } : {}),
                ...(fragmentFileId ? { fragment_sdf: fragmentFileId } : {}),
                ...(refLigandFileId ? { ref_ligand: refLigandFileId } : {})
              }
            }
          : taskInput
      )
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
    let receptorFile = sample.receptorFile
    if (typeof fetch === 'function') {
      try {
        const res = await fetch('/demo/egfr-1m17.pdb')
        if (res.ok) {
          const pdbText = await res.text()
          if (pdbText.includes('ATOM')) {
            receptorFile = new File([pdbText], 'egfr-1m17.pdb', { type: 'chemical/x-pdb' })
          }
        }
      } catch {
        // Fallback to bundled inline PDB when static /demo asset is not served (e.g. unit tests).
      }
    }
    sourceMode.value = 'upload'
    pocketDefineMode.value = 'pocket_file'
    if (!uploadProjectId.value) {
      uploadProjectId.value = projectOptions.value[0]?.value ?? activeProjectStructure.value?.projectId ?? ''
    }
    structureFile.value = receptorFile
    detectedHetatm.value = null
    const parsedSampleGeometry = sample.pocketCenter
      ? { center: sample.pocketCenter, boxSize: sample.pocketBoxSize }
      : parsePocketGeometry(await sample.pocketFile.text())
    if (parsedSampleGeometry) {
      pocketPanelRef.value?.setPocketFileState(
        sample.pocketFile,
        parsedSampleGeometry.center,
        parsedSampleGeometry.boxSize
      )
    }
    if (needsLigandFile.value) {
      await handleFragmentFile(sample.ligandFile)
    }
    message.success(t('design.molecule.sampleLoaded'))
  }

  watch(structureFile, file => {
    revokeUploadUrl()
    if (file && typeof URL !== 'undefined' && typeof URL.createObjectURL === 'function') {
      uploadStructureUrl.value = URL.createObjectURL(file)
    }
  })

  watch(fragmentUpload, file => {
    revokeLigandUrl()
    if (file && typeof URL !== 'undefined' && typeof URL.createObjectURL === 'function') {
      uploadLigandUrl.value = URL.createObjectURL(file)
    }
  })

  watch(refLigandUpload, file => {
    revokeRefLigandUrl()
    if (file && typeof URL !== 'undefined' && typeof URL.createObjectURL === 'function') {
      uploadRefLigandUrl.value = URL.createObjectURL(file)
    }
  })

  onBeforeUnmount(() => {
    revokeUploadUrl()
    revokeLigandUrl()
    revokeRefLigandUrl()
  })

  const contextPreviewScene = computed<VisualizationScene | null>(() => {
    const entries: VisualizationScene['entries'] = []

    // Build receptor entry when available
    let receptorEntry: VisualizationScene['entries'][number] | null = null
    if (sourceMode.value === 'project') {
      const fileId = activeProjectStructure.value?.structureFileId
      if (fileId) {
        const urn = (activeProjectStructure.value?.structureUrn ?? '').toLowerCase()
        const isCif = urn.endsWith('.cif') || urn.endsWith('.mmcif')
        receptorEntry = {
          key: `context-pocket-${fileId}`,
          url: `/api/v1/files/${encodeURIComponent(fileId)}/download`,
          label: pocketSelection.value?.pocketLabel || 'receptor',
          source: 'input' as const,
          role: 'receptor' as const,
          format: isCif ? ('mmcif' as const) : ('pdb' as const),
          extension: isCif ? '.cif' : '.pdb'
        }
      }
    } else if (structureFile.value && uploadStructureUrl.value) {
      const lower = structureFile.value.name.toLowerCase()
      const isCif = lower.endsWith('.cif') || lower.endsWith('.mmcif')
      receptorEntry = {
        key: `context-upload-${structureFile.value.name}`,
        url: uploadStructureUrl.value,
        label: structureFile.value.name,
        source: 'input' as const,
        role: 'receptor' as const,
        format: isCif ? ('mmcif' as const) : ('pdb' as const),
        extension: isCif ? '.cif' : '.pdb'
      }
    }

    if (receptorEntry) entries.push(receptorEntry)

    const previewLigand =
      needsLigandFile.value && fragmentUpload.value && uploadLigandUrl.value
        ? { file: fragmentUpload.value, url: uploadLigandUrl.value }
        : activePocketMode.value === 'ref_ligand' && refLigandUpload.value && uploadRefLigandUrl.value
          ? { file: refLigandUpload.value, url: uploadRefLigandUrl.value }
          : null

    if (previewLigand) {
      const lower = previewLigand.file.name.toLowerCase()
      let format: 'pdb' | 'sdf' | 'mol2' = 'sdf'
      let extension = '.sdf'
      if (lower.endsWith('.pdb')) {
        format = 'pdb'
        extension = '.pdb'
      } else if (lower.endsWith('.mol2')) {
        format = 'mol2'
        extension = '.mol2'
      }
      entries.push({
        key: `context-ligand-${previewLigand.file.name}`,
        url: previewLigand.url,
        label: previewLigand.file.name,
        source: 'input' as const,
        role: 'ligand' as const,
        format,
        extension
      })
    }

    if (entries.length === 0) return null

    return {
      entries,
      inputEntries: entries,
      outputEntries: [],
      supportedOutputFiles: [],
      unsupportedOutputFiles: [],
      hasRenderableOutput: true,
      selectedOutputKey: entries[0]?.key ?? ''
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
        activeProjectId.value &&
        structureReady.value &&
        hasCenter.value
      ),
      detail: hasCenter.value ? pocketLabelText.value : undefined
    },
    {
      id: 'fragment-params',
      title: t('design.molecule.context.stepFragmentParams'),
      done: Boolean(resolvedTool.value && activeProjectId.value && structureReady.value && hasCenter.value) &&
        (!needsLigandFile.value || Boolean(fragmentUpload.value)) && parameterErrors.value.length === 0
    }
  ])

  const contextMissingItems = computed(() => {
    const items: Array<{ id: string; label: string; targetTestId?: string }> = []
    if (!resolvedTool.value) {
      items.push({ id: 'tool', label: t('design.molecule.toolMissing'), targetTestId: 'molecule-section-model' })
    }
    if (!activeProjectId.value) {
      items.push({ id: 'project', label: t('design.molecule.needProject'), targetTestId: 'molecule-section-input' })
    }
    if (!structureReady.value) {
      items.push({ id: 'structure', label: structureMissingMessage.value, targetTestId: 'molecule-section-input' })
    } else if (!hasCenter.value) {
      items.push({ id: 'center', label: pocketCenterMissingMessage.value, targetTestId: 'molecule-section-input' })
    }
    if (needsLigandFile.value && !fragmentUpload.value) {
      items.push({ id: 'fragment', label: t(fragmentIssue.value || 'design.molecule.fragmentRequired'), targetTestId: 'molecule-fragment-section' })
    }
    if (parameterErrors.value.length > 0) {
      items.push({ id: 'params', label: firstParameterError.value, targetTestId: 'molecule-section-params' })
    }
    return items
  })

  function scrollToSection(targetTestId: string): void {
    if (typeof document === 'undefined') return
    const target = document.querySelector(`[data-testid="${targetTestId}"]`)
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function parseQueryCoord(value: unknown): number | null {
    const raw = Array.isArray(value) ? value[0] : value
    if (typeof raw !== 'string' || raw.trim() === '') return null
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : null
  }

  let appliedPocketQueryKey = ''
  async function applyPocketQueryHandoff(): Promise<void> {
    const cx = parseQueryCoord(route.query.center_x)
    const cy = parseQueryCoord(route.query.center_y)
    const cz = parseQueryCoord(route.query.center_z)
    const hasCoords = cx !== null && cy !== null && cz !== null
    const key = [
      defaultProjectId.value,
      initialTargetId.value,
      initialProteinId.value,
      initialStructureId.value,
      initialPocketId.value,
      hasCoords ? `${cx},${cy},${cz}` : ''
    ].join('|')
    if (key === appliedPocketQueryKey) return
    if (!hasPocketHandoffQuery.value && !hasCoords) return
    appliedPocketQueryKey = key

    if (defaultProjectId.value) uploadProjectId.value = defaultProjectId.value
    if (hasPocketHandoffQuery.value) {
      sourceMode.value = 'project'
      if (initialPocketId.value) {
        pocketDefineMode.value = 'project'
        return
      }
    }
    if (hasCoords) {
      await nextTick()
      pocketPanelRef.value?.setCoordinates({ x: cx, y: cy, z: cz })
    }
  }

  watch(() => route.query, () => {
    void applyPocketQueryHandoff()
  })

  onMounted(() => {
    void applyPocketQueryHandoff()
    void loadModels().then(() => loadTool())
    void loadProjects()
  })

  watch([selectedSlug, userId], () => {
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

  .param-restored-alert {
    margin-bottom: 12px;
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

  .input-stack {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .input-block {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-top: 12px;
    border-top: 1px solid @border-color;
  }

  .input-block__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
  }

  .custom-pocket-panel {
    margin-top: 2px;
    padding: 14px;
    border: 1px dashed @border-color;
    border-radius: @border-radius-md;
    background: @bg-elevated;
  }

  .hetatm-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 4px;
    padding: 4px 10px;
    border-radius: @border-radius-sm;
    background: @accent-color-light;
    font-size: @font-size-xs;
    color: @text-secondary;
  }

  .param-size-presets {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 14px;
  }

  .param-size-presets__row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
  }

  .param-size-presets__buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
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
