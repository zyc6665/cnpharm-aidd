import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ToolDetailHeaderActions from './ToolDetailHeaderActions.vue'
import type { Tool } from '@/types/models'
import i18n from '@/locales'

function makeTool(overrides: Partial<Tool> = {}): Tool {
  return {
    id: 'tool-1',
    slug: 'lvpocket-pocket-prediction',
    name: 'LVpocket Pocket Prediction',
    description: 'Predict protein pockets',
    category: 'AIDD',
    tags: [],
    status: 'published',
    usage_count: 0,
    view_count: 0,
    favorite_count: 0,
    gpu_required: false,
    is_favorited: false,
    current_version: {
      id: 'version-1',
      tool_id: 'tool-1',
      version: '2.0.0',
      config: {},
      is_active: true,
      deprecated: false,
    },
    created_at: '2026-09-14T00:00:00Z',
    ...overrides,
  }
}

describe('ToolDetailHeaderActions', () => {
  const stubs = {
    ASpace: { template: '<div class="space-stub"><slot /></div>' },
    AButton: {
      props: ['type', 'loading'],
      emits: ['click'],
      template: '<button type="button" :data-type="type" :data-loading="loading" @click="$emit(\'click\')"><slot /></button>',
    },
    ATag: { props: ['color'], template: '<span class="tag-stub"><slot /></span>' },
    HeartFilled: { template: '<i class="heart-filled" />' },
    HeartOutlined: { template: '<i class="heart-outlined" />' },
    InfoCircleOutlined: { template: '<i />' },
  }

  it('renders documentation, favorite, and version actions', () => {
    const wrapper = mount(ToolDetailHeaderActions, {
      props: { tool: makeTool(), favoriteLoading: true },
      global: { plugins: [i18n], stubs },
    })

    expect(wrapper.text()).toContain('v2.0.0')
    expect(wrapper.find('[data-loading="true"]').exists()).toBe(true)
    expect(wrapper.find('.heart-outlined').exists()).toBe(true)
  })

  it('emits header action events', async () => {
    const wrapper = mount(ToolDetailHeaderActions, {
      props: { tool: makeTool({ is_favorited: true }), favoriteLoading: false },
      global: { plugins: [i18n], stubs },
    })

    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(2)
    await buttons[0]!.trigger('click')
    await buttons[1]!.trigger('click')

    expect(wrapper.find('.heart-filled').exists()).toBe(true)
    expect(wrapper.emitted('view-documentation')).toEqual([[]])
    expect(wrapper.emitted('toggle-favorite')).toEqual([[]])
  })
})
