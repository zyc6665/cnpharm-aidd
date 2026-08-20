import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkflowNodeInlinePreview from './WorkflowNodeInlinePreview.vue'

describe('WorkflowNodeInlinePreview', () => {
  it('shows a lightweight running state while task is running', () => {
    const wrapper = mount(WorkflowNodeInlinePreview, {
      props: {
        selected: true,
        task: { id: 'task-1', status: 'running', progress: 40, output_files: [] } as never,
        artifacts: [],
      },
      global: { stubs: { AProgress: true, AEmpty: true, ResultVisualizationPanel: true } },
    })

    expect(wrapper.text()).toContain('40%')
  })

  it('lazy-renders visualization only for selected successful nodes', () => {
    const wrapper = mount(WorkflowNodeInlinePreview, {
      props: {
        selected: false,
        task: {
          id: 'task-1',
          status: 'success',
          progress: 100,
          output_files: [{ id: 'f1', filename: 'ligand.sdf', url: '/f1' }],
        } as never,
        artifacts: [],
      },
      global: {
        stubs: {
          AEmpty: true,
          ResultVisualizationPanel: { template: '<div data-testid="visualization" />' },
        },
      },
    })

    expect(wrapper.find('[data-testid="visualization"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('ligand.sdf')
  })

  it('uses a compact in-node visualization and opens full preview outside the canvas node', async () => {
    const wrapper = mount(WorkflowNodeInlinePreview, {
      props: {
        selected: true,
        task: {
          id: 'task-1',
          status: 'success',
          progress: 100,
          output_files: [{ id: 'f1', filename: 'ligand.sdf', url: '/f1' }],
        } as never,
        artifacts: [],
      },
      global: {
        stubs: {
          AEmpty: true,
          AProgress: true,
          AButton: { template: '<button @click="$emit(\'click\', $event)"><slot /></button>' },
          AModal: {
            props: ['open'],
            template: '<div v-if="open" data-testid="preview-modal"><slot /></div>',
          },
          ResultVisualizationPanel: {
            props: ['task', 'variant', 'allowNativeFullscreen'],
            template: '<div data-testid="visualization" :data-variant="variant" :data-native-fullscreen="String(allowNativeFullscreen)" />',
          },
        },
      },
    })

    const visualizations = wrapper.findAll('[data-testid="visualization"]')
    expect(visualizations).toHaveLength(1)
    expect(visualizations[0]?.attributes('data-variant')).toBe('compact')
    expect(visualizations[0]?.attributes('data-native-fullscreen')).toBe('false')
    expect(wrapper.find('.inline-preview-expand-button').attributes('aria-label')).toBe('放大查看')
    expect(wrapper.find('.inline-preview-expand-button').attributes('data-placement')).toBe('top-left')
    expect(wrapper.find('.inline-preview-expand-button').text()).toBe('')

    await wrapper.find('.inline-preview-expand-button').trigger('click')

    expect(wrapper.find('[data-testid="preview-modal"]').exists()).toBe(true)
    const expandedVisualizations = wrapper.findAll('[data-testid="visualization"]')
    expect(expandedVisualizations).toHaveLength(2)
    expect(expandedVisualizations[1]?.attributes('data-variant')).toBe('full')
    expect(expandedVisualizations[1]?.attributes('data-native-fullscreen')).toBe('false')
  })
})
