<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import MockDataBanner from '@/components/common/MockDataBanner.vue'
import { useToolMockBanner } from '@/composables/useToolMockBanner'
import FunnelChart from './FunnelChart.vue'
import { estimateFunnel } from './funnel'
import type { FunnelStageKey } from './funnel'
import { uploadFile } from '@/api/files'
import { submitToolTask } from '@/api/screening'
import {
  SCREENING_PARAM_DEFAULTS,
  SCREENING_PARAM_RANGES,
  VINA_TOOL_SLUG
} from '@/types/screening'
import type { ScreeningParams } from '@/types/screening'

const route = useRoute()
const { isMock } = useToolMockBanner(VINA_TOOL_SLUG)
const router = useRouter()
const { t } = useI18n()

const projectId = computed(() => {
  const raw = route.query.project_id
  return typeof raw === 'string' ? raw : ''
})

const receptorFile = ref<File | null>(null)
const receptorName = ref('')
const ligandsFile = ref<File | null>(null)
const ligandsName = ref('')
const pocketFile = ref<File | null>(null)
const pocketName = ref('')

const ligandCount = ref(1000)
const params = reactive<ScreeningParams>({ ...SCREENING_PARAM_DEFAULTS })
const submitting = ref(false)
const formError = ref('')

const stageLabels = computed<Record<FunnelStageKey, string>>(() => ({
  input: t('screening.config.stageInput'),
  pharmacophore: t('screening.config.stagePharmacophore'),
  docking: t('screening.config.stageDocking'),
  rescore: t('screening.config.stageRescore')
}))

const funnelStages = computed(() =>
  estimateFunnel({
    ligandCount: ligandCount.value,
    pharmacophoreMinFeatures: params.pharmacophore_min_features,
    dockingScoreCutoff: params.docking_score_cutoff,
    exhaustiveness: params.exhaustiveness,
    topN: params.top_n
  })
)

const stageRows = computed(() =>
  funnelStages.value.map((stage, index) => {
    const previous =
      index === 0 ? stage.remaining : (funnelStages.value[index - 1]?.remaining ?? stage.remaining)
    return {
      key: stage.key,
      label: stageLabels.value[stage.key],
      remaining: stage.remaining,
      eliminated: index === 0 ? 0 : previous - stage.remaining
    }
  })
)

const canSubmit = computed(
  () =>
    !submitting.value &&
    Boolean(receptorFile.value) &&
    Boolean(ligandsFile.value) &&
    Number.isFinite(ligandCount.value) &&
    ligandCount.value > 0
)

function handleReceptorUpload(file: File): boolean {
  receptorFile.value = file
  receptorName.value = file.name
  return false
}

async function handleLigandsUpload(file: File): Promise<boolean> {
  ligandsFile.value = file
  ligandsName.value = file.name
  try {
    const text = await file.text()
    const lines = text.split(/\r?\n/).filter(line => line.trim().length > 0)
    ligandCount.value = Math.max(0, lines.length - 1)
  } catch {
    // 读取失败时保留当前输入，允许用户手动填写。
  }
  return false
}

function handlePocketUpload(file: File): boolean {
  pocketFile.value = file
  pocketName.value = file.name
  return false
}

async function handleSubmit(): Promise<void> {
  formError.value = ''
  if (!receptorFile.value) {
    formError.value = t('screening.config.needReceptor')
    return
  }
  if (!ligandsFile.value) {
    formError.value = t('screening.config.needLigands')
    return
  }
  if (!Number.isFinite(ligandCount.value) || ligandCount.value <= 0) {
    formError.value = t('screening.config.ligandCountInvalid')
    return
  }

  submitting.value = true
  try {
    const receptor = await uploadFile(receptorFile.value)
    const ligands = await uploadFile(ligandsFile.value)
    const standardInputUploads: Record<string, string> = {
      receptor: receptor.data.id,
      ligands: ligands.data.id
    }
    if (pocketFile.value) {
      const pocket = await uploadFile(pocketFile.value)
      standardInputUploads.pocket = pocket.data.id
    }
    const task = await submitToolTask({
      toolSlug: VINA_TOOL_SLUG,
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
</script>

<template>
  <main class="screen-config" data-testid="screen-config-page">
    <AppPageHeader :title="t('screening.config.title')" :subtitle="t('screening.config.subtitle')" />

    <!-- 演示（mock）工具包才提示；真实模型包不显示任何告警 -->
    <MockDataBanner
      v-if="isMock"
      :mock="true"
      :disclaimer="t('screening.banner.mockTool')"
    />

    <a-card :title="t('screening.config.inputs')">
      <a-form layout="vertical">
        <a-form-item :label="t('screening.config.receptor')" required>
          <a-upload :before-upload="handleReceptorUpload" :max-count="1" accept=".pdb,.ent,.cif,.pdbqt" :file-list="[]">
            <a-button>{{ t('screening.config.chooseFile') }}</a-button>
          </a-upload>
          <span v-if="receptorName" class="screen-config__file">{{ receptorName }}</span>
        </a-form-item>
        <a-form-item :label="t('screening.config.ligands')" required>
          <a-upload :before-upload="handleLigandsUpload" :max-count="1" accept=".csv" :file-list="[]">
            <a-button>{{ t('screening.config.chooseFile') }}</a-button>
          </a-upload>
          <span v-if="ligandsName" class="screen-config__file">{{ ligandsName }}</span>
        </a-form-item>
        <a-form-item :label="t('screening.config.pocket')">
          <a-upload :before-upload="handlePocketUpload" :max-count="1" accept=".pdb,.mol2,.sdf" :file-list="[]">
            <a-button>{{ t('screening.config.chooseFile') }}</a-button>
          </a-upload>
          <span v-if="pocketName" class="screen-config__file">{{ pocketName }}</span>
        </a-form-item>
        <a-form-item :label="t('screening.config.ligandCount')">
          <a-input-number
            v-model:value="ligandCount"
            :min="1"
            :step="1"
            style="width: 200px"
            data-testid="screen-config-ligand-count"
          />
          <p class="screen-config__hint">{{ t('screening.config.ligandCountHint') }}</p>
        </a-form-item>
      </a-form>
    </a-card>

    <a-row :gutter="16">
      <a-col :xs="24" :lg="10">
        <a-card :title="t('screening.config.params')">
          <a-form layout="vertical">
            <a-form-item :label="t('screening.config.pharmacophoreMinFeatures')">
              <a-input-number
                v-model:value="params.pharmacophore_min_features"
                :min="SCREENING_PARAM_RANGES.pharmacophore_min_features.min"
                :max="SCREENING_PARAM_RANGES.pharmacophore_min_features.max"
                style="width: 100%"
              />
            </a-form-item>
            <a-form-item :label="t('screening.config.dockingScoreCutoff')">
              <a-input-number
                v-model:value="params.docking_score_cutoff"
                :min="SCREENING_PARAM_RANGES.docking_score_cutoff.min"
                :max="SCREENING_PARAM_RANGES.docking_score_cutoff.max"
                :step="0.5"
                style="width: 100%"
              />
            </a-form-item>
            <a-form-item :label="t('screening.config.exhaustiveness')">
              <a-input-number
                v-model:value="params.exhaustiveness"
                :min="SCREENING_PARAM_RANGES.exhaustiveness.min"
                :max="SCREENING_PARAM_RANGES.exhaustiveness.max"
                style="width: 100%"
              />
            </a-form-item>
            <a-form-item :label="t('screening.config.topN')">
              <a-input-number
                v-model:value="params.top_n"
                :min="SCREENING_PARAM_RANGES.top_n.min"
                :max="SCREENING_PARAM_RANGES.top_n.max"
                style="width: 100%"
              />
            </a-form-item>
            <a-form-item :label="t('screening.config.seed')">
              <a-input-number
                v-model:value="params.seed"
                :min="SCREENING_PARAM_RANGES.seed.min"
                :max="SCREENING_PARAM_RANGES.seed.max"
                style="width: 100%"
              />
            </a-form-item>
          </a-form>
        </a-card>
      </a-col>

      <a-col :xs="24" :lg="14">
        <a-card :title="t('screening.config.preview')" data-testid="screen-config-funnel">
          <p class="screen-config__hint">{{ t('screening.config.previewHint') }}</p>
          <FunnelChart :stages="funnelStages" :labels="stageLabels" />
          <a-table
            :columns="[
              { title: '', dataIndex: 'label', key: 'label' },
              { title: t('screening.config.remain'), dataIndex: 'remaining', key: 'remaining', align: 'right' },
              { title: t('screening.config.eliminated'), dataIndex: 'eliminated', key: 'eliminated', align: 'right' }
            ]"
            :data-source="stageRows"
            :pagination="false"
            row-key="key"
            size="small"
          />
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

.screen-config__notice {
  margin-bottom: 0;
}

.screen-config__file {
  margin-left: 12px;
  font-weight: 600;
}

.screen-config__hint {
  margin: 8px 0 0;
  color: var(--ant-color-text-secondary, var(--theme-text-secondary));
}

.screen-config__footer {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: flex-start;
}
</style>
