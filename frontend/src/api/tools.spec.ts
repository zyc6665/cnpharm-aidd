import { describe, expect, it, vi } from 'vitest'
import { get } from './request'
import { getWorkflowToolOptions } from './tools'
import type { ToolContract } from '@/types/models'

vi.mock('./request', () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  del: vi.fn()
}))

function makeFetchPdbContract(): ToolContract {
  return {
    contract_version: '1.0',
    id: 'tool-fetch-pdb',
    slug: 'builtin-fetch-pdb',
    name: 'Fetch PDB Structure',
    description: 'Download a protein structure from RCSB PDB',
    status: 'published',
    is_public: true,
    version: { id: 'version-fetch-pdb', version: '1.0.0', is_active: true, deprecated: false },
    executor: { type: 'builtin', timeout_sec: 120 },
    resource_profile: { tier: 'light', cpu: 1, memory_mb: 512, gpu: false },
    schema: {
      input: {
        type: 'object',
        properties: { pdb_id: { type: 'string' } },
        required: ['pdb_id']
      },
      output: { type: 'object', properties: {} }
    },
    capability: {
      enabled: true,
      capability: 'external_database_fetch',
      stage: 'data_acquisition',
      inputs: [],
      outputs: [
        {
          semantic_type: 'protein_structure@1',
          source: 'artifact',
          path: 'protein',
          required: true
        }
      ],
      defaults: {},
      virtual: false
    },
    artifacts: {
      inputs: [],
      outputs: [
        { name: 'protein', type: 'protein_structure@1', cardinality: 'one', required: true },
        { name: 'report', type: 'run_report@1', cardinality: 'one', required: false }
      ]
    },
    validation: { status: 'valid', errors: [] }
  }
}

describe('getWorkflowToolOptions', () => {
  it('保留公开工具列表中的工作流契约供单节点运行预检使用', async () => {
    const contract = makeFetchPdbContract()
    vi.mocked(get).mockResolvedValueOnce({
      code: 200,
      message: 'ok',
      data: {
        items: [
          {
            id: 'tool-fetch-pdb',
            slug: 'builtin-fetch-pdb',
            name: 'Fetch PDB Structure',
            description: 'Download a protein structure from RCSB PDB',
            icon: 'DatabaseOutlined',
            icon_url: undefined,
            category_id: 'cat-data',
            category: '数据获取',
            tags: [{ id: 'tag-built-in', name: '平台内置', color: '#1890ff', sort_order: 0 }],
            status: 'published',
            is_public: true,
            contract
          }
        ],
        total: 1,
        page: 1,
        page_size: 100
      }
    } as never)

    const response = await getWorkflowToolOptions()

    expect(response.data[0]).toMatchObject({
      slug: 'builtin-fetch-pdb',
      category_id: 'cat-data',
      category: '数据获取',
      tags: [{ id: 'tag-built-in', name: '平台内置' }],
      contract
    })
  })
})
