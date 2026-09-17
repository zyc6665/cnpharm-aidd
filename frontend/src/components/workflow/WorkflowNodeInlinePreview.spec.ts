import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import i18n from '@/locales'
import WorkflowNodeInlinePreview from './WorkflowNodeInlinePreview.vue'

describe('WorkflowNodeInlinePreview', () => {
  it('keeps inline preview copy in locale keys', () => {
    const source = readFileSync(resolve('src/components/workflow/WorkflowNodeInlinePreview.vue'), 'utf8')

    for (const marker of [
      'useI18n',
      'workflow.inlinePreview.empty',
      'workflow.inlinePreview.running',
      'workflow.inlinePreview.failed',
      'workflow.inlinePreview.failureFallback',
      'workflow.inlinePreview.expand',
      'workflow.inlinePreview.previewTitle',
      'workflow.inlinePreview.noPreviewableArtifacts',
    ]) {
      expect(source).toContain(marker)
    }

    for (const literal of [
      '暂无运行结果',
      '运行中',
      '运行失败',
      '请查看任务日志定位失败原因。',
      '放大查看',
      '结果预览',
      '任务已完成，暂无可预览产物',
    ]) {
      expect(source).not.toContain(literal)
    }
  })

  it('shows a lightweight running state while task is running', () => {
    const wrapper = mount(WorkflowNodeInlinePreview, {
      props: {
        selected: true,
        task: { id: 'task-1', status: 'running', progress: 40, output_files: [] } as never,
        artifacts: [],
      },
      global: { plugins: [i18n], stubs: { AProgress: true, AEmpty: true, ResultVisualizationPanel: true } },
    })

    expect(wrapper.text()).toContain('40%')
  })

  it('renders compact visualization for successful nodes even when they are not selected', () => {
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
        plugins: [i18n],
        stubs: {
          AEmpty: true,
          AProgress: true,
          AButton: true,
          AModal: true,
          ResultVisualizationPanel: {
            props: ['variant', 'allowNativeFullscreen'],
            template: '<div data-testid="visualization" :data-variant="variant" :data-native-fullscreen="String(allowNativeFullscreen)" />',
          },
        },
      },
    })

    expect(wrapper.find('[data-testid="visualization"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="visualization"]').attributes('data-variant')).toBe('compact')
    expect(wrapper.find('[data-testid="visualization"]').attributes('data-native-fullscreen')).toBe('false')
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
        plugins: [i18n],
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
    expect(wrapper.find('.inline-preview-expand-button').attributes('data-appearance')).toBe('light')
    expect(wrapper.find('.inline-preview-expand-button').text()).toBe('')

    await wrapper.find('.inline-preview-expand-button').trigger('click')

    expect(wrapper.find('[data-testid="preview-modal"]').exists()).toBe(true)
    const expandedVisualizations = wrapper.findAll('[data-testid="visualization"]')
    expect(expandedVisualizations).toHaveLength(2)
    expect(expandedVisualizations[1]?.attributes('data-variant')).toBe('full')
    expect(expandedVisualizations[1]?.attributes('data-native-fullscreen')).toBe('false')
  })
})
