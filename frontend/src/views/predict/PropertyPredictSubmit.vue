<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import { uploadFile } from '@/api/files'
import { exportCandidateSet, listCandidateSets } from '@/api/compounds'
import { submitToolTask } from '@/api/predict'
import ModelSelect from '@/components/design/ModelSelect.vue'
import { useModelOptions } from '@/composables/useModelOptions'
import {
  ADMET_TOOL_SLUG,
  PREDICT_DEFAULT_TASK_GROUPS,
  PREDICT_GROUP_I18N,
  PREDICT_TASK_GROUPS
} from '@/types/predict'
import type { PredictTaskGroup } from '@/types/predict'
import type { CandidateSet } from '@/types/compounds'

const props = withDefaults(
  defineProps<{ projectIdOverride?: string; initialGroups?: PredictTaskGroup[] }>(),
  { projectIdOverride: '', initialGroups: undefined }
)

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const projectId = computed(() => {
  if (props.projectIdOverride) return props.projectIdOverride
  const raw = route.query.project_id
  if (typeof raw === 'string' && raw) return raw
  const paramId = route.params?.projectId
  return typeof paramId === 'string' ? paramId : ''
})

const source = ref<'upload' | 'candidate'>('upload')
const smilesFile = ref<File | null>(null)
const smilesFileName = ref('')
const candidateSets = ref<CandidateSet[]>([])
const candidateSetId = ref<string>('')
const admetDevice = ref<'auto' | 'cpu' | 'gpu'>('auto')

// 同类 ADMET/性质预测模型可自由选择；默认 molp-pc。
const {
  options: modelOptions,
  selectedSlug,
  loading: modelLoading,
  load: loadModels
} = useModelOptions('admet_prediction', { defaultSlug: ADMET_TOOL_SLUG })

// 预测类型：ADMET 分子性质 / 结合亲和力（亲和力属于评估验证→性质预测环节）。
const predictType = ref<'admet' | 'affinity'>(route.query.type === 'affinity' ? 'affinity' : 'admet')
const {
  options: affinityOptions,
  selectedSlug: affinitySlug,
  selectedOption: affinitySelected,
  loading: affinityLoading,
  load: loadAffinityModels
} = useModelOptions('affinity', { defaultSlug: 'msign-affinity-prediction' })

const proteinPdbFile = ref<File | null>(null)
const proteinPdbName = ref('')
const ligandSdfFile = ref<File | null>(null)
const ligandSdfName = ref('')
const ligandSmilesFile = ref<File | null>(null)
const ligandSmilesName = ref('')
const affinitySequence = ref('')

const affinityInputFields = computed(() => affinitySelected.value?.inputFields ?? [])
const affinityNeedsSequence = computed(() => affinitySlug.value === 'boltz2-affinity-prediction')
const affinityCanSubmit = computed(() => {
  if (submitting.value) return false
  const fields = affinityInputFields.value
  if (fields.includes('protein_pdb') && !proteinPdbFile.value) return false
  const needsLigand = fields.includes('ligand_sdf') || fields.includes('ligand_smiles')
  if (needsLigand) {
    const hasLigand =
      (fields.includes('ligand_sdf') && Boolean(ligandSdfFile.value)) ||
      (fields.includes('ligand_smiles') && Boolean(ligandSmilesFile.value))
    if (!hasLigand) return false
  }
  if (affinityNeedsSequence.value && affinitySequence.value.trim().length < 4) return false
  return true
})
const selectedGroups = ref<PredictTaskGroup[]>(
  props.initialGroups?.length ? [...props.initialGroups] : [...PREDICT_DEFAULT_TASK_GROUPS]
)
const submitting = ref(false)
const formError = ref('')

const groupOptions = computed(() =>
  PREDICT_TASK_GROUPS.map(group => ({
    label: t(`predict.submit.${PREDICT_GROUP_I18N[group]}`),
    value: group
  }))
)

const candidateSetOptions = computed(() =>
  candidateSets.value.map(item => ({ label: item.name, value: item.id }))
)

const admetDeviceOptions = computed(() => [
  { value: 'auto', label: t('predict.submit.deviceAuto') },
  { value: 'cpu', label: 'CPU' },
  { value: 'gpu', label: 'GPU' }
])

const canSubmit = computed(() => {
  if (predictType.value === 'affinity') {
    return affinityCanSubmit.value
  }
  if (submitting.value || !selectedGroups.value.length) {
    return false
  }
  return source.value === 'upload' ? Boolean(smilesFile.value) : Boolean(candidateSetId.value)
})

function handleBeforeUpload(file: File): boolean {
  smilesFile.value = file
  smilesFileName.value = file.name
  return false
}

function handleProteinUpload(file: File): boolean {
  proteinPdbFile.value = file
  proteinPdbName.value = file.name
  return false
}

function handleLigandSdfUpload(file: File): boolean {
  ligandSdfFile.value = file
  ligandSdfName.value = file.name
  return false
}

function handleLigandSmilesUpload(file: File): boolean {
  ligandSmilesFile.value = file
  ligandSmilesName.value = file.name
  return false
}

async function handleAffinitySubmit(): Promise<void> {
  formError.value = ''
  if (!affinityCanSubmit.value) {
    return
  }
  submitting.value = true
  try {
    const fields = new Set(affinityInputFields.value)
    const standardInputUploads: Record<string, string> = {}
    if (fields.has('protein_pdb') && proteinPdbFile.value) {
      standardInputUploads.protein_pdb = (await uploadFile(proteinPdbFile.value)).data.id
    }
    if (fields.has('ligand_sdf') && ligandSdfFile.value) {
      standardInputUploads.ligand_sdf = (await uploadFile(ligandSdfFile.value)).data.id
    }
    if (fields.has('ligand_smiles') && ligandSmilesFile.value) {
      standardInputUploads.ligand_smiles = (await uploadFile(ligandSmilesFile.value)).data.id
    }
    const task = await submitToolTask({
      toolSlug: affinitySlug.value,
      projectId: projectId.value || undefined,
      name: `亲和力预测 ${new Date().toISOString().slice(0, 10)}`,
      params: affinityNeedsSequence.value ? { sequence: affinitySequence.value.trim() } : {},
      standardInputUploads
    })
    message.success(t('predict.submit.success'))
    await router.push(`/tasks/${task.id}`)
  } catch (error) {
    formError.value = error instanceof Error ? error.message : t('predict.submit.submitFailed')
  } finally {
    submitting.value = false
  }
}

async function loadCandidateSets(): Promise<void> {
  if (!projectId.value) {
    return
  }
  try {
    const response = await listCandidateSets(projectId.value, { page: 1, page_size: 100 })
    candidateSets.value = response.data.items
  } catch {
    candidateSets.value = []
  }
}

async function resolveMoleculesFileId(): Promise<string> {
  if (source.value === 'upload') {
    if (!smilesFile.value) {
      throw new Error(t('predict.submit.needFile'))
    }
    const uploaded = await uploadFile(smilesFile.value)
    return uploaded.data.id
  }
  if (!candidateSetId.value) {
    throw new Error(t('predict.submit.needFile'))
  }
  const exported = await exportCandidateSet(candidateSetId.value)
  const fileId = exported.data.file_id
  if (!fileId) {
    throw new Error(t('predict.submit.uploadFailed'))
  }
  return fileId
}

async function handleSubmit(): Promise<void> {
  if (predictType.value === 'affinity') {
    await handleAffinitySubmit()
    return
  }
  formError.value = ''
  if (source.value === 'upload' && !smilesFile.value) {
    formError.value = t('predict.submit.needFile')
    return
  }
  if (source.value === 'candidate' && !candidateSetId.value) {
    formError.value = t('predict.submit.needFile')
    return
  }
  if (!selectedGroups.value.length) {
    formError.value = t('predict.submit.needGroups')
    return
  }

  submitting.value = true
  try {
    const fileId = await resolveMoleculesFileId()
    const task = await submitToolTask({
      toolSlug: selectedSlug.value,
      projectId: projectId.value || undefined,
      name: `ADMET 性质预测 ${new Date().toISOString().slice(0, 10)}`,
      params: { device: admetDevice.value },
      standardInputUploads: { smiles_csv: fileId }
    })
    message.success(t('predict.submit.success'))
    await router.push(`/tasks/${task.id}/predictions`)
  } catch (error) {
    formError.value = error instanceof Error ? error.message : t('predict.submit.submitFailed')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  void loadModels()
  void loadAffinityModels()
  void loadCandidateSets()
})
</script>

<template>
  <main class="predict-submit" data-testid="predict-submit-page">
    <AppPageHeader :title="t('predict.submit.title')" :subtitle="t('predict.submit.subtitle')" />

    <a-card class="predict-submit__card" :title="t('predict.submit.type')">
      <a-radio-group v-model:value="predictType" button-style="solid">
        <a-radio-button value="admet" data-testid="predict-type-admet">
          {{ t('predict.submit.typeAdmet') }}
        </a-radio-button>
        <a-radio-button value="affinity" data-testid="predict-type-affinity">
          {{ t('predict.submit.typeAffinity') }}
        </a-radio-button>
      </a-radio-group>
    </a-card>

    <a-card v-if="predictType === 'admet'" class="predict-submit__card" :title="t('design.modelSelect.label')">
      <ModelSelect v-model="selectedSlug" :options="modelOptions" :loading="modelLoading" />
      <div class="predict-submit__block">
        <p class="predict-submit__hint">{{ t('predict.submit.device') }}</p>
        <a-select v-model:value="admetDevice" :options="admetDeviceOptions" style="width: 180px" />
      </div>
    </a-card>
    <a-card v-else class="predict-submit__card" :title="t('design.modelSelect.label')">
      <ModelSelect v-model="affinitySlug" :options="affinityOptions" :loading="affinityLoading" />
    </a-card>

    <a-card v-if="predictType === 'admet'" class="predict-submit__card" :title="t('predict.submit.source')">
      <a-radio-group v-model:value="source" button-style="solid">
        <a-radio-button value="upload" data-testid="predict-submit-source-upload">
          {{ t('predict.submit.sourceUpload') }}
        </a-radio-button>
        <a-radio-button value="candidate" data-testid="predict-submit-source-candidate">
          {{ t('predict.submit.sourceCandidateSet') }}
        </a-radio-button>
      </a-radio-group>

      <div v-if="source === 'upload'" class="predict-submit__block">
        <a-upload
          :before-upload="handleBeforeUpload"
          :max-count="1"
          accept=".csv"
          :file-list="[]"
        >
          <a-button>{{ t('predict.submit.chooseFile') }}</a-button>
        </a-upload>
        <p class="predict-submit__hint">{{ t('predict.submit.uploadHint') }}</p>
        <p v-if="smilesFileName" class="predict-submit__selected">
          {{ t('predict.submit.selectedFile') }}: {{ smilesFileName }}
        </p>
      </div>

      <div v-else class="predict-submit__block">
        <a-select
          v-model:value="candidateSetId"
          style="width: 320px"
          :options="candidateSetOptions"
          :placeholder="t('predict.submit.candidateSetPlaceholder')"
          :not-found-content="t('predict.submit.noCandidateSets')"
        />
        <p v-if="!projectId" class="predict-submit__hint">{{ t('predict.submit.needProject') }}</p>
      </div>
    </a-card>

    <a-card v-if="predictType === 'admet'" class="predict-submit__card" :title="t('predict.submit.groups')">
      <p class="predict-submit__hint">{{ t('predict.submit.groupsHint') }}</p>
      <a-checkbox-group
        v-model:value="selectedGroups"
        :options="groupOptions"
        data-testid="predict-submit-groups"
      />
    </a-card>

    <a-card v-if="predictType === 'affinity'" class="predict-submit__card" :title="t('predict.submit.affinityInputs')">
      <div v-if="affinityNeedsSequence" class="predict-submit__block">
        <p class="predict-submit__hint">{{ t('predict.submit.affinitySequence') }}</p>
        <a-textarea
          v-model:value="affinitySequence"
          :rows="4"
          :maxlength="2000"
          show-count
          :placeholder="t('predict.submit.affinitySequenceHint')"
        />
      </div>
      <div v-if="affinityInputFields.includes('protein_pdb')" class="predict-submit__block">
        <p class="predict-submit__hint">{{ t('predict.submit.proteinPdb') }}</p>
        <a-upload :before-upload="handleProteinUpload" :max-count="1" accept=".pdb,.cif,.ent" :file-list="[]">
          <a-button>{{ t('predict.submit.chooseInputFile') }}</a-button>
        </a-upload>
        <p v-if="proteinPdbName" class="predict-submit__selected">{{ proteinPdbName }}</p>
      </div>
      <div v-if="affinityInputFields.includes('ligand_sdf')" class="predict-submit__block">
        <p class="predict-submit__hint">{{ t('predict.submit.ligandSdf') }}</p>
        <a-upload :before-upload="handleLigandSdfUpload" :max-count="1" accept=".sdf" :file-list="[]">
          <a-button>{{ t('predict.submit.chooseInputFile') }}</a-button>
        </a-upload>
        <p v-if="ligandSdfName" class="predict-submit__selected">{{ ligandSdfName }}</p>
      </div>
      <div v-if="affinityInputFields.includes('ligand_smiles')" class="predict-submit__block">
        <p class="predict-submit__hint">{{ t('predict.submit.ligandSmiles') }}</p>
        <a-upload :before-upload="handleLigandSmilesUpload" :max-count="1" accept=".csv" :file-list="[]">
          <a-button>{{ t('predict.submit.chooseInputFile') }}</a-button>
        </a-upload>
        <p v-if="ligandSmilesName" class="predict-submit__selected">{{ ligandSmilesName }}</p>
      </div>
      <p class="predict-submit__hint">{{ t('predict.submit.affinityHint') }}</p>
    </a-card>

    <div class="predict-submit__footer">
      <a-alert v-if="formError" type="error" show-icon :message="formError" data-testid="predict-submit-error" />
      <a-button
        type="primary"
        size="large"
        :loading="submitting"
        :disabled="!canSubmit"
        data-testid="predict-submit-button"
        @click="handleSubmit"
      >
        {{ submitting ? t('predict.submit.submitting') : t('predict.submit.submit') }}
      </a-button>
    </div>
  </main>
</template>

<style scoped lang="less">
.predict-submit {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
}

.predict-submit__notice {
  margin-bottom: 0;
}

.predict-submit__block {
  margin-top: 16px;
}

.predict-submit__hint {
  margin: 8px 0 0;
  color: var(--ant-color-text-secondary, var(--theme-text-secondary));
}

.predict-submit__selected {
  margin: 8px 0 0;
  font-weight: 600;
}

.predict-submit__footer {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: flex-start;
}
</style>
