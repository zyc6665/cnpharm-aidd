import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import i18n from '@/locales'
import WorkflowToolPalette from './WorkflowToolPalette.vue'

interface PaletteToolFixture {
  slug: string
  name: string
  description?: string
  category_id?: string
  category?: string
  tags?: Array<{ id: string; name: string; color?: string }>
  capability?: string
  stage?: string
  resourceProfile?: Record<string, unknown>
  deployment?: { kind: string; executor_type?: string | null }
}

function mountPalette(tools: PaletteToolFixture[] = [
  { slug: 'pocket-explorer', name: 'Pocket Explorer', description: 'Find pockets' },
]) {
  return mount(WorkflowToolPalette, {
    props: {
      searchKeyword: '',
      stageOptions: [],
      inputOptions: [],
      outputOptions: [],
      tools,
    },
    global: {
      plugins: [i18n],
      stubs: {
        AInputSearch: { template: '<input />' },
        ASelect: { template: '<div />' },
        AEmpty: true,
      },
    },
  })
}

describe('WorkflowToolPalette', () => {
  it('工具项拖拽开始时写入工具 slug', async () => {
    const wrapper = mountPalette()
    const setData = vi.fn()
    const dataTransfer = { setData, effectAllowed: '' }

    await wrapper.find('.sidebar-tool-item').trigger('dragstart', { dataTransfer })

    expect(wrapper.find('.sidebar-tool-item').attributes('draggable')).toBe('true')
    expect(setData).toHaveBeenCalledWith('application/x-workflow-tool', 'pocket-explorer')
    expect(setData).toHaveBeenCalledWith('text/plain', 'pocket-explorer')
    expect(dataTransfer.effectAllowed).toBe('copy')
  })

  it('按能力分组展示工具和资源画像', () => {
    const wrapper = mountPalette([
      {
        slug: 'vina-docking',
        name: 'AutoDock Vina',
        description: 'Docking',
        capability: 'molecular_docking',
        stage: 'docking_scoring',
        resourceProfile: {
          tier: 'medium',
          cpu: 8,
          memory_gb: 16,
          gpu_required: false,
          expected_minutes: 30,
          timeout_minutes: 180,
        },
      },
      {
        slug: 'rdkit-properties',
        name: 'RDKit Properties',
        capability: 'property_prediction',
        stage: 'property_prediction',
        resourceProfile: { tier: 'light', cpu: 2, memory_gb: 4 },
      },
    ])

    expect(wrapper.find('.sidebar-tool-summary').text()).toContain('2 个工具可用')
    expect(wrapper.findAll('.sidebar-tool-group-title').map(item => item.text())).toEqual([
      '分子性质',
      '分子对接',
    ])
    expect(wrapper.findAll('.sidebar-tool-group-count').map(item => item.text())).toEqual([
      '1',
      '1',
    ])
    expect(wrapper.find('.sidebar-tool-grid').exists()).toBe(true)
    expect(wrapper.text()).toContain('medium')
    expect(wrapper.text()).toContain('CPU 8')
    expect(wrapper.text()).toContain('MEM 16GB')
  })

  it('统一工具目录不按部署方式展示工具', () => {
    const wrapper = mountPalette([
      {
        slug: 'builtin-protein-preparation',
        name: 'Protein Preparation',
        category: '蛋白与配体预处理',
        deployment: { kind: 'platform_builtin', executor_type: 'builtin' },
      },
      {
        slug: 'remote-admet',
        name: 'Remote ADMET',
        category: '性质预测',
        deployment: { kind: 'external_service', executor_type: 'remote_api' },
      },
    ])

    expect(wrapper.text()).not.toContain('平台内置部署')
    expect(wrapper.text()).not.toContain('外部服务部署')
    expect(wrapper.findAll('.sidebar-tool-group').length).toBe(2)
  })

  it('默认使用动态快捷筛选并折叠高级筛选', async () => {
    const wrapper = mountPalette([
      { slug: 'builtin-fetch-pdb', name: 'Fetch PDB', category_id: 'cat-data', category: '数据获取' },
      { slug: 'vina-docking', name: 'AutoDock Vina', category_id: 'cat-docking', category: '对接模拟' },
    ])

    expect(wrapper.find('.sidebar-tool-quick-filters').exists()).toBe(true)
    expect(wrapper.find('.sidebar-tool-quick-filter.is-active').text()).toContain('全部')
    expect(wrapper.find('.sidebar-tool-quick-filters').text()).toContain('数据获取')
    expect(wrapper.find('.sidebar-tool-quick-filters').text()).toContain('对接模拟')
    expect(wrapper.find('.sidebar-tool-filter-card').exists()).toBe(false)

    await wrapper.find('.sidebar-tool-advanced-toggle').trigger('click')

    expect(wrapper.find('.sidebar-tool-filter-card').exists()).toBe(true)
  })

  it('动态快捷筛选按管理员分类过滤工具', async () => {
    const wrapper = mountPalette([
      { slug: 'builtin-fetch-pdb', name: 'Fetch PDB', category_id: 'cat-data', category: '数据获取' },
      { slug: 'rdkit-properties', name: 'RDKit Properties', category_id: 'cat-property', category: '性质预测' },
      { slug: 'vina-docking', name: 'AutoDock Vina', category_id: 'cat-docking', category: '对接模拟' },
    ])

    const dockingFilter = wrapper
      .findAll('.sidebar-tool-quick-filter')
      .find(button => button.text().includes('对接模拟'))

    expect(dockingFilter).toBeTruthy()
    await dockingFilter!.trigger('click')

    expect(wrapper.find('.sidebar-tool-summary').text()).toContain('1 个工具可用')
    expect(wrapper.text()).toContain('AutoDock Vina')
    expect(wrapper.text()).not.toContain('Fetch PDB')
    expect(wrapper.text()).not.toContain('RDKit Properties')
  })

  it('动态快捷筛选按管理员标签过滤工具', async () => {
    const wrapper = mountPalette([
      {
        slug: 'vina-docking',
        name: 'AutoDock Vina',
        category_id: 'cat-docking',
        category: '对接模拟',
        tags: [{ id: 'tag-gpu', name: 'GPU', color: '#22c55e' }],
      },
      {
        slug: 'rdkit-properties',
        name: 'RDKit Properties',
        category_id: 'cat-property',
        category: '性质预测',
        tags: [{ id: 'tag-built-in', name: '平台内置', color: '#1890ff' }],
      },
    ])

    const gpuFilter = wrapper
      .findAll('.sidebar-tool-quick-filter')
      .find(button => button.text().includes('GPU'))

    expect(gpuFilter).toBeTruthy()
    await gpuFilter!.trigger('click')

    expect(wrapper.find('.sidebar-tool-summary').text()).toContain('1 个工具可用')
    expect(wrapper.text()).toContain('AutoDock Vina')
    expect(wrapper.text()).not.toContain('RDKit Properties')
  })
})
