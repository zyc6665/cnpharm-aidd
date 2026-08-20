import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WorkflowNodeRunPanel from './WorkflowNodeRunPanel.vue'
import { getToolDetail } from '@/api/tools'
import i18n from '@/locales'

vi.mock('@/api/tools', () => ({
  getToolDetail: vi.fn()
}))

const stubs = {
  AAlert: { template: '<div class="alert"><slot /></div>' },
  ASpin: { template: '<div class="spin"><slot /></div>' },
  AEmpty: { props: ['description'], template: '<div class="empty">{{ description }}</div>' },
  AForm: { template: '<form><slot /></form>' },
  AButton: { template: '<button><slot /></button>' },
  ToolParameterForm: { template: '<div class="tool-parameter-form" />' }
}

describe('WorkflowNodeRunPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(getToolDetail).mockReset()
  })

  it('工具列表异步补齐 id 后应加载真实工具并显示节点参数表单', async () => {
    vi.mocked(getToolDetail).mockResolvedValue({
      code: 200,
      message: 'ok',
      data: {
        id: 'tool-fetch-pdb',
        slug: 'builtin-fetch-pdb',
        name: 'Fetch PDB Structure',
        description: 'Download a protein structure from RCSB PDB',
        status: 'published',
        is_public: true,
        tags: [],
        usage_count: 0,
        view_count: 0,
        favorite_count: 0,
        gpu_required: false,
        created_at: '2026-08-20T00:00:00Z',
        current_version: {
          id: 'version-fetch-pdb',
          tool_id: 'tool-fetch-pdb',
          version: '1.0.0',
          config: {
            input_schema: {
              type: 'object',
              properties: { pdb_id: { type: 'string', title: 'PDB ID' } },
              required: ['pdb_id']
            }
          },
          is_active: true,
          deprecated: false,
          created_at: '2026-08-20T00:00:00Z'
        }
      }
    } as never)

    const wrapper = mount(WorkflowNodeRunPanel, {
      props: {
        nodeId: 'fetch-pdb-node',
        selectedToolSlug: 'builtin-fetch-pdb',
        availableTools: [],
        recommendedArtifacts: []
      },
      global: { plugins: [i18n], stubs }
    })

    await flushPromises()
    expect(wrapper.text()).toContain('Select a real tool before configuring this node')
    expect(getToolDetail).not.toHaveBeenCalled()

    await wrapper.setProps({
      availableTools: [
        {
          id: 'tool-fetch-pdb',
          slug: 'builtin-fetch-pdb',
          name: 'Fetch PDB Structure',
          description: 'Download a protein structure from RCSB PDB'
        }
      ]
    })
    await flushPromises()

    expect(getToolDetail).toHaveBeenCalledWith('tool-fetch-pdb')
    expect(wrapper.find('.tool-parameter-form').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Select a real tool before configuring this node')
  })
})
