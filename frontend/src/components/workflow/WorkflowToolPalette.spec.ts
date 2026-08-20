import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import i18n from '@/locales'
import WorkflowToolPalette from './WorkflowToolPalette.vue'

interface PaletteToolFixture {
  slug: string
  name: string
  description?: string
  capability?: string
  stage?: string
  executorType?: string
  resourceProfile?: Record<string, unknown>
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
      executorOptions: [],
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

  it('按能力分组展示工具并显示执行器和资源画像', () => {
    const wrapper = mountPalette([
      {
        slug: 'vina-docking',
        name: 'AutoDock Vina',
        description: 'Docking',
        capability: 'molecular_docking',
        stage: 'docking_scoring',
        executorType: 'docker_image',
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
        executorType: 'python_script',
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
    expect(wrapper.text()).toContain('docker_image')
    expect(wrapper.text()).toContain('medium')
    expect(wrapper.text()).toContain('CPU 8')
    expect(wrapper.text()).toContain('MEM 16GB')
  })

  it('默认使用任务快捷筛选并折叠高级筛选', async () => {
    const wrapper = mountPalette([
      { slug: 'builtin-fetch-pdb', name: 'Fetch PDB', capability: 'external_database_fetch' },
      { slug: 'vina-docking', name: 'AutoDock Vina', capability: 'molecular_docking' },
    ])

    expect(wrapper.find('.sidebar-tool-quick-filters').exists()).toBe(true)
    expect(wrapper.find('.sidebar-tool-quick-filter.is-active').text()).toContain('全部')
    expect(wrapper.find('.sidebar-tool-filter-card').exists()).toBe(false)

    await wrapper.find('.sidebar-tool-advanced-toggle').trigger('click')

    expect(wrapper.find('.sidebar-tool-filter-card').exists()).toBe(true)
  })

  it('任务快捷筛选按用户场景过滤工具', async () => {
    const wrapper = mountPalette([
      { slug: 'builtin-fetch-pdb', name: 'Fetch PDB', capability: 'external_database_fetch' },
      { slug: 'rdkit-properties', name: 'RDKit Properties', capability: 'property_prediction' },
      { slug: 'vina-docking', name: 'AutoDock Vina', capability: 'molecular_docking' },
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
})
