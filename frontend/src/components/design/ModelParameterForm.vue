<template>
  <div v-if="visibleEntries.length" class="model-parameter-form" data-testid="model-parameter-form">
    <a-form layout="vertical">
      <a-row :gutter="[12, 0]">
        <a-col
          v-for="[key, property] in visibleEntries"
          :key="key"
          :xs="24"
          :sm="fieldSpan(key, property)"
        >
          <a-form-item
            :label="parameterLabel(key, property)"
            :required="isRequired(schema, key)"
            :extra="parameterHint(key, property)"
          >
            <a-switch
              v-if="fieldType(property) === 'boolean'"
              :checked="Boolean(modelValue[key])"
              :disabled="isDisabled(key, property)"
              :data-testid="`model-parameter-${key}`"
              @update:checked="(value: boolean) => updateValue(key, value)"
            />
            <a-select
              v-else-if="property.enum?.length"
              :value="modelValue[key] as string | undefined"
              :options="enumOptions(key, property)"
              :disabled="isDisabled(key, property)"
              :data-testid="`model-parameter-${key}`"
              @update:value="(value: string) => updateValue(key, value)"
            />
            <a-input-number
              v-else-if="fieldType(property) === 'number'"
              :value="numberValue(key)"
              :min="property.minimum"
              :max="property.maximum"
              :step="stepFor(key, property)"
              :precision="precisionFor(property)"
              :disabled="isDisabled(key, property)"
              :data-testid="`model-parameter-${key}`"
              class="model-parameter-form__number"
              @update:value="(value: number | null) => updateValue(key, value)"
            />
            <a-textarea
              v-else-if="useTextarea(property)"
              :value="modelValue[key] as string | undefined"
              :rows="4"
              :maxlength="property.maxLength"
              show-count
              :disabled="isDisabled(key, property)"
              :data-testid="`model-parameter-${key}`"
              @update:value="(value: string) => updateValue(key, value)"
            />
            <a-input
              v-else
              :value="modelValue[key] as string | undefined"
              :maxlength="property.maxLength"
              :placeholder="parameterHint(key, property)"
              :disabled="isDisabled(key, property)"
              :data-testid="`model-parameter-${key}`"
              @update:value="(value: string) => updateValue(key, value)"
            />
          </a-form-item>
        </a-col>
      </a-row>
    </a-form>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  isRequired,
  schemaProperties,
  type ParameterValue
} from '@/domain/tools/parameterSchema'
import type { SchemaProperty, ToolSchema } from '@/types/models'

export interface ParameterFieldOverride {
  hidden?: boolean
  readonly?: boolean
  textarea?: boolean
  span?: number
}

const props = withDefaults(
  defineProps<{
    modelValue: Record<string, ParameterValue>
    schema?: ToolSchema | null
    disabled?: boolean
    overrides?: Record<string, ParameterFieldOverride>
  }>(),
  { schema: null, disabled: false, overrides: () => ({}) }
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: Record<string, ParameterValue>): void
}>()

const { t, te } = useI18n()

const visibleEntries = computed(() =>
  schemaProperties(props.schema).filter(([key]) => !props.overrides[key]?.hidden && !props.schema?.properties[key]?.hidden)
)

const KNOWN_OPTION_KEYS: Record<string, Record<string, string>> = {
  device: { auto: 'deviceAuto', cpu: 'deviceCpu', gpu: 'deviceGpu' },
  water_model: { tip3p: 'waterTip3p', spc: 'waterSpc', tip4p: 'waterTip4p' },
  prediction_mode: { joint: 'modeJoint', activity: 'modeActivity', toxicity: 'modeToxicity' },
  model_choice: {
    auto: 'modelChoiceAuto',
    all_scpdb: 'modelChoiceAllScpdb',
    alpha: 'modelChoiceAlpha',
    beta: 'modelChoiceBeta',
    alpha_beta: 'modelChoiceAlphaBeta',
    alpha_and_beta: 'modelChoiceAlphaAndBeta'
  }
}

function parameterLabel(key: string, property: SchemaProperty): string {
  const localeKey = `modelParams.labels.${key}`
  if (te(localeKey)) return t(localeKey)
  return property.title || key
}

function parameterHint(key: string, property: SchemaProperty): string {
  const localeKey = `modelParams.hints.${key}`
  if (te(localeKey)) return t(localeKey)
  return property.hint || property.description || ''
}

function fieldType(property: SchemaProperty): 'string' | 'number' | 'integer' | 'boolean' {
  const type = Array.isArray(property.type) ? property.type[0] : property.type
  if (type === 'integer') return 'integer'
  if (type === 'number') return 'number'
  if (type === 'boolean') return 'boolean'
  return 'string'
}

function numberValue(key: string): number | null {
  const value = props.modelValue[key]
  if (value === undefined || value === null || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function enumOptions(key: string, property: SchemaProperty) {
  const optionKeys = KNOWN_OPTION_KEYS[key] ?? {}
  return (property.enum ?? []).map(value => {
    const raw = String(value)
    const localeKey = optionKeys[raw] ? `modelParams.options.${optionKeys[raw]}` : ''
    return { value, label: localeKey && te(localeKey) ? t(localeKey) : raw }
  })
}

function useTextarea(property: SchemaProperty): boolean {
  return (
    property.format === 'textarea' ||
    property.format === 'fasta' ||
    (property.maxLength ?? 0) >= 500
  )
}

function stepFor(key: string, property: SchemaProperty): number {
  if (fieldType(property) === 'integer') return 1
  if (key === 'dt') return 0.001
  if (key === 'box_distance') return 0.1
  return 0.01
}

function precisionFor(property: SchemaProperty): number {
  return fieldType(property) === 'integer' ? 0 : 3
}

function isDisabled(key: string, property: SchemaProperty): boolean {
  return props.disabled || Boolean(property.disabled || property.readOnly || props.overrides[key]?.readonly)
}

function fieldSpan(key: string, property: SchemaProperty): number {
  const overrideSpan = props.overrides[key]?.span
  if (overrideSpan) return overrideSpan
  if (useTextarea(property) || key === 'sequence') return 24
  if (fieldType(property) === 'boolean' || property.enum?.length) return 8
  return 8
}

function updateValue(key: string, value: ParameterValue): void {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.model-parameter-form {
  &__number {
    width: 100%;
  }

  :deep(.ant-form-item) {
    margin-bottom: @spacing-md;
  }

  :deep(.ant-form-item-extra) {
    color: @text-tertiary;
    font-size: @font-size-sm;
  }
}
</style>
