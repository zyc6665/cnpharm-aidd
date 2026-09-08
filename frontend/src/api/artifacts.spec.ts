import { describe, expect, it, vi } from 'vitest'
import { get } from './request'
import { getProjectArtifacts } from './artifacts'

vi.mock('./request', () => ({
  get: vi.fn(),
  post: vi.fn(),
}))

describe('getProjectArtifacts', () => {
  it('透传 Artifact 交付元数据筛选参数', async () => {
    const response = {
      code: 200,
      message: 'ok',
      data: { items: [] },
    }
    vi.mocked(get).mockResolvedValueOnce(response as never)

    const result = await getProjectArtifacts('project-1', {
      metadata_model_version: 'MolP-PC 0.1.1',
      metadata_evidence_level: 'engineering_smoke_only',
    })

    expect(get).toHaveBeenCalledWith('/projects/project-1/artifacts', {
      metadata_model_version: 'MolP-PC 0.1.1',
      metadata_evidence_level: 'engineering_smoke_only',
    })
    expect(result).toEqual(response)
  })
})
