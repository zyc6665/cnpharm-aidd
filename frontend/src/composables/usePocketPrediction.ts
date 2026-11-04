import { ref, type Ref } from 'vue'
import { predictPockets } from '@/api/targets'

/**
 * 口袋预测提交（供既有 Pockets 页与「上游接力条」同源复用）。
 * 只负责提交并返回 task_id；等待终态与刷新列表由调用方处理。
 */
export function usePocketPrediction() {
  const predicting: Ref<boolean> = ref(false)
  const error: Ref<string> = ref('')

  async function predict(structureId: string): Promise<string | null> {
    error.value = ''
    predicting.value = true
    try {
      const response = await predictPockets(structureId, {})
      return response.data.task_id
    } catch {
      error.value = 'predict-failed'
      return null
    } finally {
      predicting.value = false
    }
  }

  return { predicting, error, predict }
}
