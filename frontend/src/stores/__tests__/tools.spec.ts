import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useToolsStore } from '@/stores/tools'
import { getCategories, getTags } from '@/api/tools'

vi.mock('@/api/tools', () => ({
  getToolList: vi.fn(),
  getToolDetail: vi.fn(),
  getCategories: vi.fn(),
  getTags: vi.fn(),
  getWorkbenchGroups: vi.fn(),
  getWorkflowToolOptions: vi.fn(),
  favoriteTool: vi.fn(),
  unfavoriteTool: vi.fn()
}))

describe('useToolsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(getCategories).mockReset()
    vi.mocked(getTags).mockReset()
  })

  it('fetchCategories 失败时应清空旧分类状态', async () => {
    const store = useToolsStore()
    vi.mocked(getCategories)
      .mockResolvedValueOnce({
        code: 200,
        message: 'ok',
        data: [{ id: 'cat-1', name: 'Docking', slug: 'docking', sort_order: 1 }]
      })
      .mockRejectedValueOnce(new Error('network failed'))

    await expect(store.fetchCategories()).resolves.toHaveLength(1)
    expect(store.categories).toHaveLength(1)

    await expect(store.fetchCategories()).resolves.toEqual([])
    expect(store.categories).toEqual([])
  })

  it('fetchTags 失败时应清空旧标签状态', async () => {
    const store = useToolsStore()
    vi.mocked(getTags)
      .mockResolvedValueOnce({
        code: 200,
        message: 'ok',
        data: [{ id: 'tag-1', name: 'GPU', color: '#0070c0', sort_order: 1 }]
      })
      .mockRejectedValueOnce(new Error('network failed'))

    await expect(store.fetchTags()).resolves.toHaveLength(1)
    expect(store.tags).toHaveLength(1)

    await expect(store.fetchTags()).resolves.toEqual([])
    expect(store.tags).toEqual([])
  })
})
