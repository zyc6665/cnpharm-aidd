import { beforeEach, describe, expect, it, vi } from 'vitest'
import { get } from './request'
import { getAllProjectArtifacts, getProjectArtifacts } from './artifacts'

vi.mock('./request', () => ({
  get: vi.fn(),
  post: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
})

describe('getProjectArtifacts', () => {
  it('透传 Artifact 交付元数据筛选参数', async () => {
    const response = {
      code: 200,
      message: 'ok',
      data: { items: [] },
    }
    vi.mocked(get).mockResolvedValueOnce(response as never)

    const result = await getProjectArtifacts('project-1', {
      metadata_model_name: 'MolP-PC',
      metadata_model_version: 'MolP-PC 0.1.1',
      metadata_evidence_level: 'engineering_smoke_only',
      metadata_endpoint_ref: 'local_runtime:molp-pc-property-prediction@0.1.1',
      metadata_applicability_domain_status: 'unknown',
    })

    // 分页接口不塞默认 page_size，参数原样透传。
    expect(get).toHaveBeenCalledWith('/projects/project-1/artifacts', {
      metadata_model_name: 'MolP-PC',
      metadata_model_version: 'MolP-PC 0.1.1',
      metadata_evidence_level: 'engineering_smoke_only',
      metadata_endpoint_ref: 'local_runtime:molp-pc-property-prediction@0.1.1',
      metadata_applicability_domain_status: 'unknown',
    })
    expect(result).toEqual(response)
  })

  it('透传 Artifact 类型和来源筛选参数', async () => {
    const response = {
      code: 200,
      message: 'ok',
      data: { items: [] },
    }
    vi.mocked(get).mockResolvedValueOnce(response as never)

    await getProjectArtifacts('project-1', {
      artifact_type: 'molecule_table',
      standard_type: 'molecule_table',
      source_task_id: 'task-rdkit',
    })

    expect(get).toHaveBeenCalledWith('/projects/project-1/artifacts', {
      artifact_type: 'molecule_table',
      standard_type: 'molecule_table',
      source_task_id: 'task-rdkit',
    })
  })

  it('透传 Artifact role 筛选参数', async () => {
    vi.mocked(get).mockResolvedValueOnce({ code: 200, message: 'ok', data: { items: [] } } as never)

    await getProjectArtifacts('project-1', { file_role: 'structure_3d_sdf' })

    expect(get).toHaveBeenCalledWith('/projects/project-1/artifacts', {
      file_role: 'structure_3d_sdf',
    })
  })

  it('透传分页参数', async () => {
    vi.mocked(get).mockResolvedValueOnce({ code: 200, message: 'ok', data: { items: [] } } as never)

    await getProjectArtifacts('project-1', { page: 2, page_size: 20 })

    expect(get).toHaveBeenCalledWith('/projects/project-1/artifacts', {
      page: 2,
      page_size: 20,
    })
  })
})

describe('getAllProjectArtifacts', () => {
  it('按 page_size=100 循环取全量并合并 items', async () => {
    const firstPageItems = Array.from({ length: 100 }, (_, index) => ({ id: `a-${index}` }))
    const secondPageItems = Array.from({ length: 50 }, (_, index) => ({ id: `b-${index}` }))

    vi.mocked(get)
      .mockResolvedValueOnce({
        code: 200,
        message: 'ok',
        data: { items: firstPageItems, total: 150, page: 1, page_size: 100 },
      } as never)
      .mockResolvedValueOnce({
        code: 200,
        message: 'ok',
        data: { items: secondPageItems, total: 150, page: 2, page_size: 100 },
      } as never)

    const result = await getAllProjectArtifacts('project-1')

    expect(get).toHaveBeenCalledTimes(2)
    expect(get).toHaveBeenNthCalledWith(1, '/projects/project-1/artifacts', {
      page: 1,
      page_size: 100,
    })
    expect(get).toHaveBeenNthCalledWith(2, '/projects/project-1/artifacts', {
      page: 2,
      page_size: 100,
    })
    expect(result.data.items).toHaveLength(150)
    expect(result.data.total).toBe(150)
  })
})
