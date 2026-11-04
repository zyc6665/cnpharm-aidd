import { describe, it, expect, vi, beforeEach } from 'vitest'
vi.mock('@/api/targets', () => ({ listPockets: vi.fn(), selectPocket: vi.fn() }))
import { ref } from 'vue'
import { listPockets, selectPocket } from '@/api/targets'
import { useStructurePockets } from './useStructurePockets'

describe('useStructurePockets', () => {
  beforeEach(() => {
    vi.mocked(listPockets).mockReset()
    vi.mocked(selectPocket).mockReset()
  })

  it('loads, sorts and exposes selected pocket', async () => {
    vi.mocked(listPockets).mockResolvedValue({
      data: {
        items: [
          { id: 'b', rank: 2, score: 0.5, selected: false },
          { id: 'a', rank: 1, score: 0.9, selected: true },
        ],
      },
    } as never)
    const c = useStructurePockets(ref('s1'))
    await c.load()
    expect(c.sorted.value.map(p => p.id)).toEqual(['a', 'b'])
    expect(c.selected.value?.id).toBe('a')
  })
})
