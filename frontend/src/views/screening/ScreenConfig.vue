<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import { uploadFile } from '@/api/files'
import { submitToolTask } from '@/api/screening'
import ModelSelect from '@/components/design/ModelSelect.vue'
import { useModelOptions } from '@/composables/useModelOptions'
import {
  SCREENING_PARAM_DEFAULTS,
  SCREENING_PARAM_RANGES,
  VINA_TOOL_SLUG
} from '@/types/screening'
import type { ScreeningParams } from '@/types/screening'

const props = withDefaults(defineProps<{ projectIdOverride?: string }>(), {
  projectIdOverride: ''
})

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const {
  options: modelOptions,
  selectedSlug,
  loading: modelLoading,
  load: loadModels
} = useModelOptions('docking', { defaultSlug: VINA_TOOL_SLUG })
void loadModels()

const projectId = computed(() => {
  if (props.projectIdOverride) return props.projectIdOverride
  const raw = route.query.project_id
  if (typeof raw === 'string' && raw) return raw
  const paramId = route.params?.projectId
  return typeof paramId === 'string' ? paramId : ''
})

const receptorFile = ref<File | null>(null)
const receptorName = ref('')
const ligandFiles = ref<File[]>([])
const ligandFormat = ref<'' | 'sdf' | 'csv'>('')
const ligandCount = ref(0)
const ligandError = ref('')
const pocketFile = ref<File | null>(null)
const pocketName = ref('')

const params = reactive<ScreeningParams>({ ...SCREENING_PARAM_DEFAULTS })
const submitting = ref(false)
const formError = ref('')

const canSubmit = computed(
  () =>
    !submitting.value &&
    Boolean(receptorFile.value) &&
    ligandFiles.value.length > 0 &&
    !ligandError.value &&
    ligandCount.value > 0
)

function fileStem(name: string): string {
  return name.replace(/\.[^.]+$/, '')
}

function handleReceptorUpload(file: File): boolean {
  receptorFile.value = file
  receptorName.value = file.name
  return false
}

function handlePocketUpload(file: File): boolean {
  pocketFile.value = file
  pocketName.value = file.name
  return false
}

function detectFormat(name: string): 'sdf' | 'csv' | '' {
  const lower = name.toLowerCase()
  if (lower.endsWith('.csv')) return 'csv'
  if (lower.endsWith('.sdf') || lower.endsWith('.mol')) return 'sdf'
  return ''
}

let ligandCountSeq = 0

async function handleLigandUpload(file: File): Promise<boolean> {
  const format = detectFormat(file.name)
  if (!format) {
    ligandError.value = t('screening.config.onlySdfOrCsv')
    return false
  }
  if (ligandFormat.value && ligandFormat.value !== format) {
    ligandError.value = t('screening.config.mixedLigandFormats')
    return false
  }
  ligandFormat.value = format
  ligandFiles.value = [...ligandFiles.value, file]
  ligandError.value = ''
  const seq = ++ligandCountSeq
  try {
    const count = await countLigands([...ligandFiles.value], format)
    if (seq === ligandCountSeq) ligandCount.value = count
  } catch {
    if (seq === ligandCountSeq) {
      ligandCount.value = 0
      ligandError.value = t('screening.config.ligandsUnreadable')
    }
  }
  return false
}

function clearLigands(): void {
  ligandCountSeq += 1
  ligandFiles.value = []
  ligandFormat.value = ''
  ligandCount.value = 0
  ligandError.value = ''
}

async function countLigands(files: File[], format: 'sdf' | 'csv'): Promise<number> {
  if (format === 'csv') {
    let total = 0
    for (const file of files) {
      total += parseCsv(await file.text()).rows.length
    }
    return total
  }
  let total = 0
  for (const file of files) {
    total += splitSdfRecords(await file.text()).length
  }
  return total
}

function splitSdfRecords(text: string): string[] {
  return text
    .split(/\$\$\$\$\s*/)
    .map(record => record.trim())
    .filter(Boolean)
}

async function buildSdfPayload(): Promise<File> {
  const blocks: string[] = []
  for (const file of ligandFiles.value) {
    const stem = fileStem(file.name)
    const records = splitSdfRecords(await file.text())
    records.forEach((record, index) => {
      const lines = record.split(/\r?\n/)
      lines[0] = records.length === 1 ? stem : `${stem}_${index + 1}`
      blocks.push(`${lines.join('\n')}\n$$$$`)
    })
  }
  return new File([blocks.join('\n')], 'ligands.sdf', { type: 'chemical/x-mdl-sdfile' })
}

function parseCsv(text: string): { headers: string[]; rows: string[][] } {
  const source = text.replace(/^\uFEFF/, '')
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let inQuotes = false
  for (let i = 0; i < source.length; i += 1) {
    const char = source[i]
    if (inQuotes) {
      if (char === '"' && source[i + 1] === '"') {
        field += '"'
        i += 1
      } else if (char === '"') {
        inQuotes = false
      } else {
        field += char
      }
      continue
    }
    if (char === '"') {
      inQuotes = true
    } else if (char === ',') {
      row.push(field)
      field = ''
    } else if (char === '\n') {
      row.push(field)
      if (row.some(cell => cell.trim())) rows.push(row)
      row = []
      field = ''
    } else if (char !== '\r') {
      field += char
    }
  }
  row.push(field)
  if (row.some(cell => cell.trim())) rows.push(row)
  const headers = (rows.shift() ?? []).map(header => header.trim())
  return { headers, rows }
}

async function buildCsvPayload(): Promise<File> {
  const output = ['molecule_id,SMILES']
  for (const file of ligandFiles.value) {
    const { headers, rows } = parseCsv(await file.text())
    const smilesIndex = headers.findIndex(header => header.toLowerCase().includes('smiles'))
    if (smilesIndex < 0) {
      throw new Error(t('screening.config.csvMissingSmiles'))
    }
    const idIndex = headers.findIndex(header =>
      ['molecule_id', 'ligand_id', 'name', 'id'].includes(header.toLowerCase())
    )
    const stem = fileStem(file.name)
    rows.forEach((cells, index) => {
      const smiles = (cells[smilesIndex] ?? '').trim()
      if (!smiles) return
      const rawId = idIndex >= 0 ? (cells[idIndex] ?? '').trim() : ''
      const moleculeId = rawId || (rows.length === 1 ? stem : `${stem}_${index + 1}`)
      output.push(`${moleculeId},${smiles}`)
    })
  }
  return new File([output.join('\n')], 'ligands.csv', { type: 'text/csv' })
}

async function handleSubmit(): Promise<void> {
  formError.value = ''
  if (!receptorFile.value) {
    formError.value = t('screening.config.needReceptor')
    return
  }
  if (!ligandFiles.value.length) {
    formError.value = t('screening.config.needLigands')
    return
  }
  if (ligandError.value || ligandCount.value <= 0) {
    formError.value = ligandError.value || t('screening.config.needLigands')
    return
  }

  submitting.value = true
  try {
    const receptor = await uploadFile(receptorFile.value)
    const standardInputUploads: Record<string, string> = {
      protein_pdb: receptor.data.id
    }
    if (ligandFormat.value === 'csv') {
      const payload = await buildCsvPayload()
      const uploaded = await uploadFile(payload)
      standardInputUploads.ligand_smiles = uploaded.data.id
    } else {
      const payload = await buildSdfPayload()
      const uploaded = await uploadFile(payload)
      standardInputUploads.ligand_sdf = uploaded.data.id
    }
    if (pocketFile.value) {
      const pocket = await uploadFile(pocketFile.value)
      standardInputUploads.binding_pocket = pocket.data.id
    }
    const task = await submitToolTask({
      toolSlug: selectedSlug.value,
      projectId: projectId.value || undefined,
      name: `虚拟筛选 ${new Date().toISOString().slice(0, 10)}`,
      params: { ...params },
      standardInputUploads
    })
    message.success(t('screening.config.success'))
    await router.push(`/tasks/${task.id}/screening`)
  } catch (error) {
    formError.value = error instanceof Error ? error.message : t('screening.config.submitFailed')
  } finally {
    submitting.value = false
  }
}

const paramFields = computed(() => [
  {
    key: 'pharmacophore_min_features' as const,
    label: t('screening.config.pharmacophoreMinFeatures'),
    step: 1
  },
  {
    key: 'docking_score_cutoff' as const,
    label: t('screening.config.dockingScoreCutoff'),
    step: 0.5
  },
  { key: 'top_n' as const, label: t('screening.config.topN'), step: 1 },
  { key: 'exhaustiveness' as const, label: t('screening.config.exhaustiveness'), step: 1 },
  { key: 'n_poses' as const, label: t('screening.config.nPoses'), step: 1 },
  { key: 'box_size' as const, label: t('screening.config.boxSize'), step: 1 },
  { key: 'seed' as const, label: t('screening.config.seed'), step: 1 }
])
</script>

<template>
  <main class="screen-config" data-testid="screen-config-page">
    <AppPageHeader :title="t('screening.config.title')" :subtitle="t('screening.config.subtitle')" />

    <a-card :title="t('design.modelSelect.label')">
      <ModelSelect v-model="selectedSlug" :options="modelOptions" :loading="modelLoading" />
    </a-card>

    <a-card :title="t('screening.config.inputs')">
      <a-form layout="vertical">
        <a-form-item :label="t('screening.config.receptor')" required>
          <a-upload :before-upload="handleReceptorUpload" :max-count="1" accept=".pdb,.cif,.ent" :file-list="[]">
            <a-button>{{ t('screening.config.chooseFile') }}</a-button>
          </a-upload>
          <span v-if="receptorName" class="screen-config__file">{{ receptorName }}</span>
        </a-form-item>

        <a-form-item :label="t('screening.config.ligandLibrary')" required>
          <a-upload
            :before-upload="handleLigandUpload"
            multiple
            accept=".sdf,.mol,.csv"
            :file-list="[]"
            data-testid="screen-config-ligands-upload"
          >
            <a-button>{{ t('screening.config.chooseFiles') }}</a-button>
          </a-upload>
          <a-button v-if="ligandFiles.length" type="link" size="small" @click="clearLigands">
            {{ t('screening.config.clearLigands') }}
          </a-button>
          <p class="screen-config__hint">{{ t('screening.config.ligandLibraryHint') }}</p>
          <div v-if="ligandFiles.length" class="screen-config__files" data-testid="screen-config-ligand-files">
            <a-tag v-for="file in ligandFiles" :key="file.name">{{ file.name }}</a-tag>
            <span class="screen-config__hint">{{ t('screening.config.ligandCountValue', { count: ligandCount }) }}</span>
          </div>
          <a-alert v-if="ligandError" type="warning" show-icon :message="ligandError" />
        </a-form-item>

        <a-form-item :label="t('screening.config.pocket')">
          <a-upload :before-upload="handlePocketUpload" :max-count="1" accept=".pdb" :file-list="[]">
            <a-button>{{ t('screening.config.chooseFile') }}</a-button>
          </a-upload>
          <span v-if="pocketName" class="screen-config__file">{{ pocketName }}</span>
          <p class="screen-config__hint">{{ t('screening.config.pocketHint') }}</p>
        </a-form-item>
      </a-form>
    </a-card>

    <a-row :gutter="16">
      <a-col :xs="24" :lg="12">
        <a-card :title="t('screening.config.params')">
          <a-form layout="vertical">
            <a-row :gutter="12">
              <a-col v-for="field in paramFields" :key="field.key" :xs="24" :sm="12">
                <a-form-item :label="field.label">
                  <a-input-number
                    v-model:value="params[field.key]"
                    :min="SCREENING_PARAM_RANGES[field.key].min"
                    :max="SCREENING_PARAM_RANGES[field.key].max"
                    :step="field.step"
                    style="width: 100%"
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </a-form>
        </a-card>
      </a-col>

      <a-col :xs="24" :lg="12">
        <a-card :title="t('screening.config.rulesTitle')" data-testid="screen-config-rules">
          <p class="screen-config__hint">{{ t('screening.config.rulesHint') }}</p>
          <ol class="screen-config__rules">
            <li>
              <strong>{{ t('screening.config.ruleInput') }}</strong>
              <span>{{ t('screening.config.ruleInputHint', { count: ligandCount }) }}</span>
            </li>
            <li>
              <strong>{{ t('screening.config.rulePharmacophore') }}</strong>
              <span>{{ t('screening.config.rulePharmacophoreHint', { count: params.pharmacophore_min_features }) }}</span>
            </li>
            <li>
              <strong>{{ t('screening.config.ruleDocking') }}</strong>
              <span>{{ t('screening.config.ruleDockingHint', { count: params.exhaustiveness, poses: params.n_poses }) }}</span>
            </li>
            <li>
              <strong>{{ t('screening.config.ruleCutoff') }}</strong>
              <span>{{ t('screening.config.ruleCutoffHint', { score: params.docking_score_cutoff }) }}</span>
            </li>
            <li>
              <strong>{{ t('screening.config.ruleKept') }}</strong>
              <span>{{ t('screening.config.ruleKeptHint', { count: params.top_n }) }}</span>
            </li>
          </ol>
          <p class="screen-config__hint">{{ t('screening.config.resultFunnelHint') }}</p>
        </a-card>
      </a-col>
    </a-row>

    <div class="screen-config__footer">
      <a-alert v-if="formError" type="error" show-icon :message="formError" data-testid="screen-config-error" />
      <a-button
        type="primary"
        size="large"
        :loading="submitting"
        :disabled="!canSubmit"
        data-testid="screen-config-submit"
        @click="handleSubmit"
      >
        {{ submitting ? t('screening.config.submitting') : t('screening.config.submit') }}
      </a-button>
    </div>
  </main>
</template>

<style scoped lang="less">
.screen-config {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
}

.screen-config__file {
  margin-left: 12px;
  font-weight: 600;
}

.screen-config__files {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}

.screen-config__hint {
  margin: 8px 0 0;
  color: var(--ant-color-text-secondary, var(--theme-text-secondary));
}

.screen-config__rules {
  margin: 8px 0 0;
  padding-left: 22px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.screen-config__rules li {
  line-height: 1.6;
}

.screen-config__rules strong {
  display: block;
}

.screen-config__rules span {
  color: var(--ant-color-text-secondary, var(--theme-text-secondary));
}

.screen-config__footer {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: flex-start;
}
</style>
