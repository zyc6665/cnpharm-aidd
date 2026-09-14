import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ToolDetailSidebar from './ToolDetailSidebar.vue'
import type { Tool } from '@/types/models'
import i18n from '@/locales'

function makeTool(overrides: Partial<Tool> = {}): Tool {
  return {
    id: 'tool-1',
    slug: 'remote-tool',
    name: 'Remote Tool',
    description: 'Demo',
    category: 'AIDD',
    tags: [{ id: 'tag-1', name: 'Docking', color: 'blue', sort_order: 0 }],
    status: 'published',
    usage_count: 0,
    view_count: 0,
    favorite_count: 0,
    statistics: { usage_count: 1, view_count: 2, favorite_count: 3 },
    gpu_required: false,
    created_at: '2026-09-14T00:00:00Z',
    updated_at: '2026-09-15T00:00:00Z',
    ...overrides,
  }
}

describe('ToolDetailSidebar', () => {
  const stubs = {
    RouterLink: { props: ['to'], template: '<a><slot /></a>' },
    ATag: { props: ['color'], template: '<span class="tag"><slot /></span>' },
    ASpace: { template: '<span><slot /></span>' },
    TagOutlined: { template: '<i />' },
    InfoCircleOutlined: { template: '<i />' },
  }

  it('renders tags, status, validation, dates, and remote tool diagnostics', () => {
    const wrapper = mount(ToolDetailSidebar, {
      props: {
        tool: makeTool(),
        validationBadges: [{ label: '生产已验证', color: 'green' }],
        isRemoteToolV1: true,
        remoteToolBaseUrl: 'https://runner.example',
        remoteToolManifestHash: 'sha256:abc123',
        remoteToolSmokeStatus: 'success',
        remoteToolSmokeTaskId: 'task-1',
        remoteToolSmokeError: '',
        remoteToolSmokeStatusColor: status => status === 'success' ? 'green' : 'orange',
        remoteToolSmokeStatusText: status => status === 'success' ? '已通过' : '未完成',
      },
      global: { plugins: [i18n], stubs },
    })

    expect(wrapper.text()).toContain('Docking')
    expect(wrapper.text()).toContain('published')
    expect(wrapper.text()).toContain('生产已验证')
    expect(wrapper.text()).toContain('远程 API')
    expect(wrapper.text()).toContain('remote_tool_v1')
    expect(wrapper.text()).toContain('https://runner.example')
    expect(wrapper.text()).toContain('sha256:abc123')
    expect(wrapper.text()).toContain('已通过')
    expect(wrapper.text()).toContain('查看 smoke test 任务')
  })

  it('omits optional tag and remote cards when absent', () => {
    const wrapper = mount(ToolDetailSidebar, {
      props: {
        tool: makeTool({ tags: [] }),
        validationBadges: [],
        isRemoteToolV1: false,
        remoteToolSmokeStatus: 'not_run',
        remoteToolSmokeStatusColor: () => 'orange',
        remoteToolSmokeStatusText: () => '未完成',
      },
      global: { plugins: [i18n], stubs },
    })

    expect(wrapper.find('.tags-info').exists()).toBe(false)
    expect(wrapper.find('.remote-tool-info').exists()).toBe(false)
    expect(wrapper.find('.status-info').exists()).toBe(true)
  })
})
