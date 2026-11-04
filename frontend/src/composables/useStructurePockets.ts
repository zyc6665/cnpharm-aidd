import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { listPockets, selectPocket } from '@/api/targets'
import { findSelectedPocket, sortPocketsByScore } from '@/domain/targets'
import type { PocketSummary } from '@/types/targets'

/**
 * 某结构下的口袋列表 + 选定（供既有 Pockets 页与「上游接力条」同源复用）。
 * 选定是「同结构内互斥」语义，故选定后整表重拉，避免本地 patch 漏掉后端连带规则。
 */
export function useStructurePockets(structureId: Ref<string>) {
  const pockets: Ref<PocketSummary[]> = ref([])
  const loading: Ref<boolean> = ref(false)
  const error: Ref<string> = ref('')
  const selectingId: Ref<string> = ref('')

  const sorted: ComputedRef<PocketSummary[]> = computed(() => sortPocketsByScore(pockets.value))
  const selected: ComputedRef<PocketSummary | null> = computed(() => findSelectedPocket(pockets.value))

  async function load(): Promise<void> {
    if (!structureId.value) {
      return
    }
    loading.value = true
    error.value = ''
    try {
      const response = await listPockets(structureId.value)
      pockets.value = response.data.items
    } catch {
      error.value = 'load-failed'
      pockets.value = []
    } finally {
      loading.value = false
    }
  }

  async function select(pocketId: string): Promise<void> {
    selectingId.value = pocketId
    error.value = ''
    try {
      await selectPocket(pocketId, true)
      await load()
    } catch {
      error.value = 'select-failed'
    } finally {
      selectingId.value = ''
    }
  }

  return { pockets, sorted, selected, loading, error, selectingId, load, select }
}
