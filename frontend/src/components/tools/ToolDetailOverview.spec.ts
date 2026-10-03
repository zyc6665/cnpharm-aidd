import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ToolDetailOverview from './ToolDetailOverview.vue'
import type { Tool } from '@/types/models'
import i18n from '@/locales'

function makeTool(overrides: Partial<Tool> = {}): Tool {
  return {
    id: 'tool-1',
    slug: 'lvpocket-pocket-prediction',
    name: 'LVpocket Pocket Prediction',
    description: 'Predict protein pockets',
    category: 'AIDD',
    tags: [{ id: 'tag-1', name: 'Pocket', color: 'gold', sort_order: 0 }],
    status: 'published',
    usage_count: 0,
    view_count: 0,
    favorite_count: 0,
    statistics: { usage_count: 12, view_count: 34, favorite_count: 5 },
    gpu_required: false,
    current_version: {
      id: 'version-1',
      tool_id: 'tool-1',
      version: '2.0.0',
      config: {},
      is_active: true,
      deprecated: false,
      changelog: 'Adds standard artifact outputs.',
    },
    created_at: '2026-09-14T00:00:00Z',
    ...overrides,
  }
}

describe('ToolDetailOverview', () => {
  const stubs = {
    ATag: { props: ['color'], template: '<span class="tag"><slot /></span>' },
    ToolOutlined: { template: '<i />' },
    PlayCircleOutlined: { template: '<i />' },
    EyeOutlined: { template: '<i />' },
    HeartOutlined: { template: '<i />' },
    TagOutlined: { template: '<i />' },
  }

  it('renders tool identity, metrics, version, and changelog', () => {
    const wrapper = mount(ToolDetailOverview, {
      props: { tool: makeTool() },
      global: { plugins: [i18n], stubs },
    })

    expect(wrapper.text()).toContain('Predict protein pockets')
    expect(wrapper.text()).toContain('AIDD')
    expect(wrapper.text()).toContain('Pocket')
    expect(wrapper.text()).toContain('12')
    expect(wrapper.text()).toContain('34')
    expect(wrapper.text()).toContain('5')
    expect(wrapper.text()).toContain('v2.0.0')
    expect(wrapper.text()).toContain('Adds standard artifact outputs.')
  })

  it('omits changelog when the current version has none', () => {
    const wrapper = mount(ToolDetailOverview, {
      props: {
        tool: makeTool({
          current_version: {
            id: 'version-1',
            tool_id: 'tool-1',
            version: '2.0.0',
            config: {},
            is_active: true,
            deprecated: false,
          },
        }),
      },
      global: { plugins: [i18n], stubs },
    })

    expect(wrapper.find('.tool-changelog').exists()).toBe(false)
  })

  it('不在详情中显示部署方式', () => {
    const wrapper = mount(ToolDetailOverview, {
      props: {
        tool: makeTool({
          deployment: { kind: 'platform_builtin', executor_type: 'builtin' },
        }),
      },
      global: { plugins: [i18n], stubs },
    })

    expect(wrapper.text()).not.toContain('平台内置部署')
    expect(wrapper.text()).not.toContain('外部服务部署')
    expect(wrapper.text()).not.toContain('builtin')
  })
})
