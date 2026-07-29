import { getCurrentScope, onScopeDispose, ref } from 'vue'
import { getToolList } from '@/api/tools'
import type { Tool } from '@/types/models'

interface RemoteToolOptionsConfig {
  debounceMs?: number
  pageSize?: number
}

export function useRemoteToolOptions(config: RemoteToolOptionsConfig = {}) {
  const debounceMs = config.debounceMs ?? 250
  const pageSize = config.pageSize ?? 50
  const toolOptions = ref<Tool[]>([])
  const toolOptionsLoading = ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | undefined
  let requestSequence = 0

  const fetchToolOptions = async (keyword = '') => {
    const requestId = ++requestSequence
    toolOptionsLoading.value = true
    try {
      const response = await getToolList({
        page: 1,
        page_size: pageSize,
        search: keyword.trim() || undefined
      })
      if (requestId === requestSequence) {
        toolOptions.value = response.data.items
      }
    } finally {
      if (requestId === requestSequence) {
        toolOptionsLoading.value = false
      }
    }
  }

  const searchToolOptions = (keyword: string) => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
    }
    debounceTimer = setTimeout(() => {
      void fetchToolOptions(keyword)
    }, debounceMs)
  }

  if (getCurrentScope()) {
    onScopeDispose(() => {
      if (debounceTimer) {
        clearTimeout(debounceTimer)
      }
      requestSequence += 1
    })
  }

  return {
    fetchToolOptions,
    searchToolOptions,
    toolOptions,
    toolOptionsLoading
  }
}
