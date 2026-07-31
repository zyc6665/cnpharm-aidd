import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import i18n from '@/locales'
import WorkflowToolPalette from './WorkflowToolPalette.vue'

function mountPalette() {
  return mount(WorkflowToolPalette, {
    props: {
      searchKeyword: '',
      stageOptions: [],
      inputOptions: [],
      outputOptions: [],
      executorOptions: [],
      tools: [{ slug: 'pocket-explorer', name: 'Pocket Explorer', description: 'Find pockets' }],
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
})
