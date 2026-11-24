<template>
  <a-form-item
    :label="parameterLabel()"
    :required="required"
    :extra="parameterHint()"
  >
    <a-switch
      v-if="fieldType() === 'boolean'"
      :checked="Boolean(value)"
      :disabled="disabled || isReadOnly()"
      :data-testid="`model-parameter-${fieldKey}`"
      @update:checked="(next: boolean) => emit('update', next)"
    />
    <a-select
      v-else-if="property.enum?.length"
      :value="value as string | undefined"
      :options="enumOptions()"
      :disabled="disabled || isReadOnly()"
      :data-testid="`model-parameter-${fieldKey}`"
      @update:value="(next: string) => emit('update', next)"
    />
    <a-input-number
      v-else-if="fieldType() === 'number'"
      :value="numberValue()"
      :min="property.minimum"
      :max="property.maximum"
      :step="stepFor()"
      :precision="precisionFor()"
      :disabled="disabled || isReadOnly()"
      :data-testid="`model-parameter-${fieldKey}`"
      class="model-parameter-field__number"
      @update:value="(next: number | null) => emit('update', next)"
    />
    <a-textarea
      v-else-if="useTextarea()"
      :value="value as string | undefined"
      :rows="4"
      :maxlength="property.maxLength"
      show-count
      :disabled="disabled || isReadOnly()"
      :data-testid="`model-parameter-${fieldKey}`"
      @update:value="(next: string) => emit('update', next)"
    />
    <a-input
      v-else
      :value="value as string | undefined"
      :maxlength="property.maxLength"
      :placeholder="parameterHint()"
      :disabled="disabled || isReadOnly()"
      :data-testid="`model-parameter-${fieldKey}`"
      @update:value="(next: string) => emit('update', next)"
    />
  </a-form-item>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { ParameterValue } from '@/domain/tools/parameterSchema'
import type { SchemaProperty } from '@/types/models'

const props = withDefaults(
  defineProps<{
    fieldKey: string
    property: SchemaProperty
    value?: ParameterValue
    required?: boolean
    disabled?: boolean
    readonly?: boolean
  }>(),
  { value: undefined, required: false, disabled: false, readonly: false }
)

const emit = defineEmits<{ (event: 'update', value: ParameterValue): void }>()
const { t, te } = useI18n()

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

function parameterLabel(): string {
  const localeKey = `modelParams.labels.${props.fieldKey}`
  if (te(localeKey)) return t(localeKey)
  return props.property.title || props.fieldKey
}

function parameterHint(): string {
  const localeKey = `modelParams.hints.${props.fieldKey}`
  if (te(localeKey)) return t(localeKey)
  return props.property.hint || props.property.description || ''
}

function fieldType(): 'string' | 'number' | 'integer' | 'boolean' {
  const type = Array.isArray(props.property.type) ? props.property.type[0] : props.property.type
  if (type === 'integer') return 'integer'
  if (type === 'number') return 'number'
  if (type === 'boolean') return 'boolean'
  return 'string'
}

function numberValue(): number | null {
  const raw = props.value
  if (raw === undefined || raw === null || raw === '') return null
  const numeric = Number(raw)
  return Number.isFinite(numeric) ? numeric : null
}

function enumOptions() {
  const optionKeys = KNOWN_OPTION_KEYS[props.fieldKey] ?? {}
  return (props.property.enum ?? []).map(option => {
    const raw = String(option)
    const localeKey = optionKeys[raw] ? `modelParams.options.${optionKeys[raw]}` : ''
    return { value: option, label: localeKey && te(localeKey) ? t(localeKey) : raw }
  })
}

function useTextarea(): boolean {
  return (
    props.property.format === 'textarea' ||
    props.property.format === 'fasta' ||
    (props.property.maxLength ?? 0) >= 500
  )
}

function stepFor(): number {
  if (fieldType() === 'integer') return 1
  if (props.fieldKey === 'dt') return 0.001
  if (props.fieldKey === 'box_distance') return 0.1
  return 0.01
}

function precisionFor(): number {
  return fieldType() === 'integer' ? 0 : 3
}

function isReadOnly(): boolean {
  return props.readonly || Boolean(props.property.disabled || props.property.readOnly)
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.model-parameter-field__number {
  width: 100%;
}
</style>
