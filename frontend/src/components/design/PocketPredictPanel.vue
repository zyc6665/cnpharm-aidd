<template>
  <div class="pocket-predict-panel" data-testid="pocket-predict-panel">
    <div class="panel-head">
      <span class="panel-hint">{{ t('targets.pockets.subtitle') }}</span>
      <a-button
        size="small"
        :loading="predicting || waiting"
        data-testid="pocket-predict-button"
        @click="handlePredict"
      >
        {{ t('targets.structure.predictPockets') }}
      </a-button>
    </div>

    <div class="panel-model">
      <ModelSelect v-model="selectedSlug" :options="modelOptions" :loading="modelLoading" />
    </div>

    <ModelParameterForm
      v-if="selectedOption?.parameterSchema"
      v-model="pocketParams"
      :schema="selectedOption.parameterSchema"
      :disabled="predicting || waiting"
    />

    <a-spin :spinning="loading">
      <p v-if="!sorted.length && !loading" class="panel-empty">{{ t('targets.pockets.emptyHint') }}</p>
      <a-table
        v-else
        size="small"
        :columns="columns"
        :data-source="sorted"
        :pagination="false"
        row-key="id"
        data-testid="pocket-predict-table"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'rank'">#{{ record.rank ?? '-' }}</template>
          <template v-else-if="column.key === 'score'">{{ formatPocketScore(record.score) }}</template>
          <template v-else-if="column.key === 'volume'">{{ formatPocketVolume(record.volume) }}</template>
          <template v-else-if="column.key === 'actions'">
            <a-button
              size="small"
              type="primary"
              :loading="selectingId === record.id"
              data-testid="pocket-select-button"
              @click="handleSelect(record)"
            >
              {{ t('targets.pockets.select') }}
            </a-button>
          </template>
        </template>
      </a-table>
    </a-spin>

    <a-alert v-if="errorText" type="error" show-icon :message="errorText" class="panel-error" />  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, toRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatPocketScore, formatPocketVolume } from '@/domain/targets'
import { usePocketPrediction } from '@/composables/usePocketPrediction'
import { useStructurePockets } from '@/composables/useStructurePockets'
import { waitForTaskCompletion } from '@/composables/useTaskCompletion'
import { useModelOptions } from '@/composables/useModelOptions'
import ModelSelect from '@/components/design/ModelSelect.vue'
import ModelParameterForm from '@/components/design/ModelParameterForm.vue'
import { buildDefaultValues, normalizeParameters, validateParameters, type ParameterValues } from '@/domain/tools/parameterSchema'
import { POCKET_PREDICT_TOOL_SLUG } from '@/types/design'
import type { PocketSummary } from '@/types/targets'

const props = defineProps<{ structureId: string }>()
const emit = defineEmits<{
  (event: 'selected', pocket: PocketSummary): void
  (event: 'predicted', taskId: string): void
}>()

const { t } = useI18n()
const structureIdRef = toRef(props, 'structureId')
const { sorted, loading, error, selectingId, selected, load, select } = useStructurePockets(structureIdRef)
const { predicting, error: predictError, predict } = usePocketPrediction()
const waiting = ref(false)
const runError = ref('')
const pocketParams = ref<ParameterValues>({})

// 口袋预测模型：同类可自由选择，默认 lvpocket；参数 schema 随模型切换。
const {
  options: modelOptions,
  selectedSlug,
  selectedOption,
  loading: modelLoading,
  load: loadModels
} = useModelOptions('pocket_prediction', { defaultSlug: POCKET_PREDICT_TOOL_SLUG })

watch(
  selectedOption,
  option => {
    pocketParams.value = buildDefaultValues(option?.parameterSchema ?? null)
  },
  { immediate: true }
)

onMounted(() => {
  void loadModels()
})

const columns = computed(() => [
  { title: t('targets.pockets.rank'), key: 'rank', width: 70 },
  { title: t('targets.pockets.score'), key: 'score', width: 100 },
  { title: t('targets.pockets.volume'), key: 'volume', width: 110 },
  { title: t('targets.actions'), key: 'actions', width: 100 },
])

const errorText = computed(() => {
  const code = runError.value || predictError.value || error.value
  if (!code) return ''
  if (code === 'select-failed') return t('targets.pockets.selectFailed')
  if (code === 'predict-failed') return t('targets.structure.pocketsFailed')
  if (code === 'predict-timeout') return t('targets.structure.pocketsTimeout')
  return t('targets.loadFailed')
})

watch(structureIdRef, () => void load(), { immediate: true })

async function handlePredict(): Promise<void> {
  if (!props.structureId) return
  runError.value = ''
  const schema = selectedOption.value?.parameterSchema ?? null
  if (validateParameters(schema, pocketParams.value).length > 0) {
    runError.value = 'predict-failed'
    return
  }
  const taskId = await predict(
    props.structureId,
    selectedSlug.value,
    normalizeParameters(schema, pocketParams.value)
  )
  if (!taskId) return
  emit('predicted', taskId)
  waiting.value = true
  try {
    const result = await waitForTaskCompletion(taskId)
    if (result.ok) {
      await load()
    } else {
      runError.value = result.status === 'timeout' ? 'predict-timeout' : 'predict-failed'
    }
  } finally {
    waiting.value = false
  }
}

async function handleSelect(pocket: PocketSummary): Promise<void> {
  await select(pocket.id)
  const current = selected.value
  if (current) emit('selected', current)
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.pocket-predict-panel {
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    margin-bottom: @spacing-sm;
  }

  .panel-hint {
    color: @text-secondary;
    font-size: @font-size-sm;
  }

  .panel-empty {
    margin: @spacing-sm 0;
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .panel-config {
    display: flex;
    gap: @spacing-md;
    margin: @spacing-sm 0;
  }

  .panel-config-item {
    flex: 1;
    margin-bottom: 0;
  }

  .panel-error {
    margin-top: @spacing-sm;
  }
}
</style>
