<template>
  <div class="model-select" data-testid="model-select">
    <a-select
      v-if="options.length"
      :value="modelValue"
      :loading="loading"
      :disabled="disabled"
      :placeholder="t('design.modelSelect.placeholder')"
      class="model-select__control"
      data-testid="model-select-control"
      @change="handleChange"
    >
      <a-select-option
        v-for="option in options"
        :key="option.slug"
        :value="option.slug"
        :label="option.name"
      >
        {{ optionLabel(option) }}
      </a-select-option>
    </a-select>
    <a-input
      v-else
      :value="modelValue"
      :disabled="loading || disabled"
      :placeholder="t('design.modelSelect.placeholder')"
      class="model-select__control"
      data-testid="model-select-fallback"
      @update:value="handleChange"
    />
    <p v-if="options.length > 1" class="model-select__hint">{{ t('design.modelSelect.hint') }}</p>

    <div v-if="selectedMeta" class="model-select__meta" data-testid="model-select-meta">
      <div class="model-select__meta-row">
        <span class="model-select__meta-label">{{ t('design.modelSelect.meta.selected') }}</span>
        <strong>{{ selectedOption?.name }}</strong>
      </div>
      <p v-if="selectedOption?.description" class="model-select__meta-desc">
        {{ selectedOption.description }}
      </p>
      <div class="model-select__meta-row">
        <span class="model-select__meta-label">{{ t('design.modelSelect.meta.duration') }}</span>
        <span>{{ selectedMeta.duration }}</span>
      </div>
      <div class="model-select__meta-row">
        <span class="model-select__meta-label">{{ t('design.modelSelect.meta.scenario') }}</span>
        <span>{{ selectedMeta.scenario }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ModelOption } from '@/composables/useModelOptions'

const props = defineProps<{
  modelValue: string
  options: ModelOption[]
  loading?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{ (event: 'update:modelValue', value: string): void }>()
const { t } = useI18n()

interface ModelMetaHint {
  duration: string
  scenario: string
}

interface ModelMetaDefinition {
  prefix: string
  durationKey: string
  scenarioKey: string
}

/** 已知模型的耗时/适用场景提示；未命中的 slug 落入通用文案。 */
const MODEL_META_DEFINITIONS: ModelMetaDefinition[] = [
  {
    prefix: 'pocket2mol',
    durationKey: 'design.modelSelect.meta.pocket2mol.duration',
    scenarioKey: 'design.modelSelect.meta.pocket2mol.scenario',
  },
  {
    prefix: 'diffdock',
    durationKey: 'design.modelSelect.meta.diffdock.duration',
    scenarioKey: 'design.modelSelect.meta.diffdock.scenario',
  },
  {
    prefix: 'boltz2',
    durationKey: 'design.modelSelect.meta.boltz2.duration',
    scenarioKey: 'design.modelSelect.meta.boltz2.scenario',
  },
]

const selectedOption = computed(
  () => props.options.find(option => option.slug === props.modelValue) ?? null
)

function metaFor(option: ModelOption): ModelMetaHint {
  const definition = MODEL_META_DEFINITIONS.find(({ prefix }) => option.slug.startsWith(prefix))
  return {
    duration: t(definition?.durationKey ?? 'design.modelSelect.meta.generic.duration'),
    scenario: t(definition?.scenarioKey ?? 'design.modelSelect.meta.generic.scenario'),
  }
}

const selectedMeta = computed<ModelMetaHint | null>(() =>
  selectedOption.value ? metaFor(selectedOption.value) : null
)

function optionLabel(option: ModelOption): string {
  const version = option.version ? ` · v${option.version}` : ''
  const suffix = option.mock ? ` (${t('design.modelSelect.mock')})` : ''
  const duration = ` · ${metaFor(option).duration}`
  return `${option.name}${version}${suffix}${duration}`
}

function handleChange(value: unknown): void {
  if (typeof value === 'string') emit('update:modelValue', value)
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.model-select {
  .model-select__control {
    width: 100%;
  }

  .model-select__hint {
    margin: @spacing-xs 0 0;
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .model-select__meta {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-top: @spacing-sm;
    padding: @spacing-sm @spacing-md;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    background: @surface-sunken;
  }

  .model-select__meta-row {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-sm;
    font-size: @font-size-sm;
    color: @text-secondary;
  }

  .model-select__meta-label {
    min-width: 72px;
    color: @text-tertiary;
  }

  .model-select__meta-desc {
    margin: 0;
    color: @text-secondary;
    font-size: @font-size-sm;
    line-height: 1.5;
  }
}
</style>
