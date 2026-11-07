import { reactive, ref, type Ref } from 'vue'
import { predictStructure } from '@/api/targets'
import { STRUCTURE_PREDICT_TOOL_SLUG } from '@/types/design'
import {
  buildDefaultValues,
  normalizeParameters,
  validateParameters,
  type ParameterValues
} from '@/domain/tools/parameterSchema'
import type { ToolSchema } from '@/types/models'
import type { StructurePredictInput } from '@/types/targets'

export interface StructurePredictValues {
  modelSlug: string
  params: ParameterValues
}

const DEFAULT_VALUES: StructurePredictValues = {
  modelSlug: STRUCTURE_PREDICT_TOOL_SLUG,
  params: {}
}

const STRUCTURE_HIDDEN_PARAMS = ['sequence', 'seq_length']

export function buildStructurePredictPayload(
  values: StructurePredictValues,
  schema?: ToolSchema | null
): StructurePredictInput {
  return {
    model_ref: { name: values.modelSlug.trim() || DEFAULT_VALUES.modelSlug },
    params: normalizeParameters(schema ?? null, values.params)
  }
}

/**
 * 结构预测的表单 + 提交（供既有 Predict 页与「上游接力条」同源复用）。
 * 参数由选中模型的 parameters schema 动态决定，只隐藏后端自动注入的 sequence。
 */
export function useStructurePrediction(options: { defaults?: Partial<StructurePredictValues> } = {}) {
  const form = reactive<StructurePredictValues>({ ...DEFAULT_VALUES, ...options.defaults })
  const submitting: Ref<boolean> = ref(false)
  const error: Ref<string> = ref('')

  function setSchema(schema?: ToolSchema | null): void {
    form.params = buildDefaultValues(schema ?? null, { omit: STRUCTURE_HIDDEN_PARAMS })
  }

  async function submit(proteinId: string, schema?: ToolSchema | null): Promise<string | null> {
    error.value = ''
    const validationSchema = schema
      ? {
          ...schema,
          required: (schema.required ?? []).filter((key) => !STRUCTURE_HIDDEN_PARAMS.includes(key))
        }
      : null
    const errors = validateParameters(validationSchema, form.params)
    if (errors.length > 0) {
      error.value = `invalid-${errors[0]}`
      return null
    }
    submitting.value = true
    try {
      const response = await predictStructure(proteinId, buildStructurePredictPayload(form, schema))
      return response.data.task_id
    } catch {
      error.value = 'submit-failed'
      return null
    } finally {
      submitting.value = false
    }
  }

  return { form, submitting, error, setSchema, submit }
}
