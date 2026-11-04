import { describe, it, expect, vi, beforeEach } from 'vitest'
vi.mock('@/api/targets', () => ({ predictStructure: vi.fn() }))
import { predictStructure } from '@/api/targets'
import { useStructurePrediction } from './useStructurePrediction'

describe('useStructurePrediction', () => {
  beforeEach(() => vi.mocked(predictStructure).mockReset())

  it('rejects invalid numbers', async () => {
    const p = useStructurePrediction()
    p.form.numRecycles = 0
    expect(await p.submit('protein-1')).toBeNull()
    expect(predictStructure).not.toHaveBeenCalled()
  })

  it('submits payload and returns task id', async () => {
    vi.mocked(predictStructure).mockResolvedValue({ data: { task_id: 'task-1' } } as never)
    const p = useStructurePrediction()
    expect(await p.submit('protein-1')).toBe('task-1')
    expect(predictStructure).toHaveBeenCalledWith('protein-1', {
      model_ref: { name: 'boltz-2' },
      params: { useMsa: false, numRecycles: 3, seed: 42 },
    })
  })
})
