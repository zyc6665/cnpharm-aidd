import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getArtifactFiles } from '@/api/files'
import type { ArtifactFile } from '@/types/models'

export const useArtifactsStore = defineStore('artifacts', () => {
  const items = ref<ArtifactFile[]>([])
  const total = ref(0)
  const loading = ref(false)

  const fetchArtifacts = async (params?: { page?: number; page_size?: number; search?: string }) => {
    loading.value = true
    try {
      const res = await getArtifactFiles(params)
      items.value = res.data.items
      total.value = res.data.total
      return res.data
    } finally {
      loading.value = false
    }
  }

  const resetArtifacts = () => {
    items.value = []
    total.value = 0
  }

  return {
    items,
    total,
    loading,
    fetchArtifacts,
    resetArtifacts
  }
})
