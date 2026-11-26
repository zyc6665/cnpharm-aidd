import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MoleculeDesignContextPanel from './MoleculeDesignContextPanel.vue'

describe('MoleculeDesignContextPanel', () => {
  const defaultProps = {
    modelName: 'Pocket2Mol',
    modeLabel: '基于口袋的分子生成',
    pocketLabel: 'Pocket 1',
    pocketCenter: { x: 10.5, y: 20.3, z: 15.7 },
    pocketBoxSize: { x: 20, y: 25, z: 18 },
    previewScene: null,
    sampleCount: 100,
    fragmentSummary: null,
    steps: [
      { id: 'step1', title: '选择靶点与口袋', done: true },
      { id: 'step2', title: '配置生成参数', done: true },
      { id: 'step3', title: '提交任务', done: false }
    ],
    missingItems: [],
    canSubmit: true
  }

  it('renders step readiness header', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: defaultProps
    })

    const steps = wrapper.find('[data-testid="context-steps"]')
    expect(steps.exists()).toBe(true)
    expect(steps.findAll('.step-item')).toHaveLength(3)
  })

  it('displays step done state correctly', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: defaultProps
    })

    const stepItems = wrapper.findAll('.step-item')
    expect(stepItems[0].classes()).toContain('is-done')
    expect(stepItems[1].classes()).toContain('is-done')
    expect(stepItems[2].classes()).not.toContain('is-done')
  })

  it('shows empty preview state when previewScene is null', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: defaultProps
    })

    expect(wrapper.find('.preview-empty').exists()).toBe(true)
    expect(wrapper.find('.preview-viewer').exists()).toBe(false)
  })

  it('renders MoleculeViewer when previewScene is provided', () => {
    const mockScene = {
      entries: [
        {
          key: 'test',
          url: '/test.pdb',
          label: 'Test Structure',
          source: 'input' as const,
          role: 'receptor' as const,
          format: 'pdb' as const,
          extension: '.pdb'
        }
      ],
      inputEntries: [],
      outputEntries: [],
      supportedOutputFiles: [],
      unsupportedOutputFiles: [],
      hasRenderableOutput: true,
      selectedOutputKey: 'test'
    }

    const wrapper = mount(MoleculeDesignContextPanel, {
      props: {
        ...defaultProps,
        previewScene: mockScene
      }
    })

    expect(wrapper.find('.preview-viewer').exists()).toBe(true)
    expect(wrapper.find('.preview-empty').exists()).toBe(false)
  })

  it('displays readiness checklist when cannot submit', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: {
        ...defaultProps,
        canSubmit: false,
        missingItems: [
          { id: 'pocket', label: '请选择口袋', targetTestId: 'pocket-selector' },
          { id: 'params', label: '请配置生成参数', targetTestId: 'params-form' }
        ]
      }
    })

    const readiness = wrapper.find('[data-testid="context-readiness"]')
    expect(readiness.exists()).toBe(true)
    expect(readiness.findAll('.missing-item')).toHaveLength(2)
  })

  it('displays ready badge when canSubmit is true', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: defaultProps
    })

    const readiness = wrapper.find('[data-testid="context-readiness"]')
    expect(readiness.exists()).toBe(true)
    expect(readiness.find('.ready-badge').exists()).toBe(true)
  })

  it('emits jump-to when missing item is clicked', async () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: {
        ...defaultProps,
        canSubmit: false,
        missingItems: [
          { id: 'pocket', label: '请选择口袋', targetTestId: 'pocket-selector' }
        ]
      }
    })

    await wrapper.find('.missing-item').trigger('click')
    expect(wrapper.emitted('jump-to')).toHaveLength(1)
    expect(wrapper.emitted('jump-to')?.[0]).toEqual(['pocket-selector'])
  })

  it('does not emit jump-to when missing item has no targetTestId', async () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: {
        ...defaultProps,
        canSubmit: false,
        missingItems: [
          { id: 'pocket', label: '请选择口袋' }
        ]
      }
    })

    await wrapper.find('.missing-item').trigger('click')
    expect(wrapper.emitted('jump-to')).toBeUndefined()
  })

  it('displays task summary with model name', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: defaultProps
    })

    const summary = wrapper.find('.summary-grid')
    expect(summary.text()).toContain('Pocket2Mol')
  })

  it('displays pocket center coordinates', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: defaultProps
    })

    const summary = wrapper.find('.summary-grid')
    expect(summary.text()).toContain('10.5')
    expect(summary.text()).toContain('20.3')
    expect(summary.text()).toContain('15.7')
  })

  it('displays pocket box size', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: defaultProps
    })

    const summary = wrapper.find('.summary-grid')
    expect(summary.text()).toContain('20')
    expect(summary.text()).toContain('25')
    expect(summary.text()).toContain('18')
  })

  it('displays sample count', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: defaultProps
    })

    const summary = wrapper.find('.summary-grid')
    expect(summary.text()).toContain('100')
  })

  it('displays fragment summary when provided', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: {
        ...defaultProps,
        fragmentSummary: '保留片段: 原子 0-5'
      }
    })

    const summary = wrapper.find('.summary-grid')
    expect(summary.text()).toContain('保留片段: 原子 0-5')
  })

  it('handles null pocket center gracefully', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: {
        ...defaultProps,
        pocketCenter: null
      }
    })

    expect(wrapper.find('.summary-grid').exists()).toBe(true)
  })

  it('handles null pocket box size gracefully', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: {
        ...defaultProps,
        pocketBoxSize: null
      }
    })

    expect(wrapper.find('.summary-grid').exists()).toBe(true)
  })

  it('formats pocket coordinates with 1 decimal place', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: {
        ...defaultProps,
        pocketCenter: { x: 10.567, y: 20.234, z: 15.789 }
      }
    })

    const summary = wrapper.find('.summary-grid')
    expect(summary.text()).toContain('10.6')
    expect(summary.text()).toContain('20.2')
    expect(summary.text()).toContain('15.8')
  })

  it('displays mode label', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: defaultProps
    })

    const summary = wrapper.find('.summary-grid')
    expect(summary.text()).toContain('基于口袋的分子生成')
  })

  it('displays pocket label', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: defaultProps
    })

    const summary = wrapper.find('.summary-grid')
    expect(summary.text()).toContain('Pocket 1')
  })

  it('renders correctly with minimal props', () => {
    const wrapper = mount(MoleculeDesignContextPanel, {
      props: {
        modelName: 'Test Model',
        modeLabel: 'Test Mode',
        pocketLabel: 'Test Pocket',
        pocketCenter: null,
        pocketBoxSize: null,
        previewScene: null,
        steps: [],
        missingItems: [],
        canSubmit: false
      }
    })

    expect(wrapper.exists()).toBe(true)
  })
})
