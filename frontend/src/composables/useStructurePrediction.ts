import { reactive, ref, type Ref } from 'vue'
import { predictStructure } from '@/api/targets'
import type { StructurePredictInput } from '@/types/targets'

export interface StructurePredictValues {
  modelName: string
  numRecycles: number
  seed: number
  useMsa: boolean
}

const DEFAULT_VALUES: StructurePredictValues = {
  modelName: 'boltz-2',
  numRecycles: 3,
  seed: 42,
  useMsa: false,
}

export function buildStructurePredictPayload(values: StructurePredictValues): StructurePredictInput {
  return {
    model_ref: { name: values.modelName.trim() || DEFAULT_VALUES.modelName },
    params: {
      useMsa: values.useMsa,
      numRecycles: values.numRecycles,
      seed: values.seed,
    },
  }
}

/**
 * 结构预测的表单 + 提交（供既有 Predict 页与「上游接力条」同源复用）。
 * 只负责把一次提交发出去并返回 task_id；等待终态由调用方用 waitForTaskCompletion。
 */
export function useStructurePrediction(options: { defaults?: Partial<StructurePredictValues> } = {}) {
  const form = reactive<StructurePredictValues>({ ...DEFAULT_VALUES, ...options.defaults })
  const submitting: Ref<boolean> = ref(false)
  const error: Ref<string> = ref('')

  async function submit(proteinId: string): Promise<string | null> {
    error.value = ''
    const numRecycles = Number(form.numRecycles)
    const seed = Number(form.seed)
    if (!Number.isFinite(numRecycles) || numRecycles < 1) {
      error.value = 'invalid-num-recycles'
      return null
    }
    if (!Number.isFinite(seed) || seed < 0) {
      error.value = 'invalid-seed'
      return null
    }
    form.numRecycles = numRecycles
    form.seed = seed
    submitting.value = true
    try {
      const response = await predictStructure(proteinId, buildStructurePredictPayload(form))
      return response.data.task_id
    } catch {
      error.value = 'submit-failed'
      return null
    } finally {
      submitting.value = false
    }
  }

  return { form, submitting, error, submit }
}
