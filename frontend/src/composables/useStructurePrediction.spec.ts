import { describe, it, expect, vi, beforeEach } from 'vitest'
vi.mock('@/api/targets', () => ({ predictStructure: vi.fn() }))
import { predictStructure } from '@/api/targets'
import { useStructurePrediction } from './useStructurePrediction'
import type { ToolSchema } from '@/types/models'

const schema: ToolSchema = {
  type: 'object',
  properties: {
    sequence: { type: 'string', title: 'Sequence' },
    sampling_steps: { type: 'integer', minimum: 10, maximum: 1000, default: 200 },
    recycling_steps: { type: 'integer', minimum: 1, maximum: 10, default: 3 },
    diffusion_samples: { type: 'integer', minimum: 1, maximum: 10, default: 1 },
    seed: { type: 'integer', minimum: 0, default: 0 }
  },
  required: ['sequence']
}

describe('useStructurePrediction', () => {
  beforeEach(() => vi.mocked(predictStructure).mockReset())

  it('rejects invalid numbers', async () => {
    const p = useStructurePrediction()
    p.setSchema(schema)
    p.form.params.sampling_steps = 0
    expect(await p.submit('protein-1', schema)).toBeNull()
    expect(predictStructure).not.toHaveBeenCalled()
  })

  it('submits schema defaults and returns task id', async () => {
    vi.mocked(predictStructure).mockResolvedValue({ data: { task_id: 'task-1' } } as never)
    const p = useStructurePrediction()
    p.setSchema(schema)
    expect(await p.submit('protein-1', schema)).toBe('task-1')
    expect(predictStructure).toHaveBeenCalledWith('protein-1', {
      model_ref: { name: 'boltz2-structure-prediction' },
      params: { sampling_steps: 200, recycling_steps: 3, diffusion_samples: 1, seed: 0 }
    })
  })
})
