import { computed } from 'vue'
import { describe, expect, it } from 'vitest'
import type { Tool, ToolSchema } from '@/types/models'
import { useToolDetailPresentation, type ToolDetailPresentationLabels } from './useToolDetailPresentation'

const labels: ToolDetailPresentationLabels = {
  detailFallback: '工具详情',
  usageCount: '使用次数',
  viewCount: '浏览次数',
  title: '介绍',
  overview: '模型概览',
  parameters: '参数说明',
  outputs: '输出说明',
  outputPatterns: '输出文件',
  name: '名称',
  required: '必填',
  optional: '选填',
  defaultValue: '默认值',
  type: '类型',
  description: '描述',
  range: '范围',
  noDocumentation: '暂无文档',
}

function makeTool(config: Record<string, unknown>): Tool {
  return {
    id: 'tool-remote',
    name: 'Remote Tool',
    slug: 'remote-tool',
    description: 'Remote model endpoint',
    category: 'AIDD',
    tags: [],
    status: 'published',
    usage_count: 0,
    view_count: 0,
    favorite_count: 0,
    gpu_required: false,
    statistics: { usage_count: 12_300, view_count: 456, favorite_count: 7 },
    current_version: {
      id: 'version-remote',
      tool_id: 'tool-remote',
      version: '1.0.0',
      is_active: true,
      deprecated: false,
      config,
    },
    created_at: '2026-09-13T00:00:00Z',
  }
}

const inputSchema: ToolSchema = {
  type: 'object',
  properties: {
    sequence: { type: 'string', title: 'Sequence' },
  },
  required: ['sequence'],
}

describe('useToolDetailPresentation', () => {
  it('provides executor metadata and a concise subtitle', () => {
    const presentation = useToolDetailPresentation({
      tool: computed(() => makeTool({
        type: 'ssh_job',
      })),
      inputSchema: computed(() => inputSchema),
      labels: computed(() => labels),
    })

    expect(presentation.executorType.value).toBe('ssh_job')
    expect(presentation.detailSubtitle.value).toBe('使用次数: 1.2w · 浏览次数: 456')
  })

  it('renders configured markdown before fallback documentation', () => {
    const configured = useToolDetailPresentation({
      tool: computed(() => makeTool({ documentation_markdown: '## Custom Doc' })),
      inputSchema: computed(() => inputSchema),
      labels: computed(() => labels),
    })
    const fallback = useToolDetailPresentation({
      tool: computed(() => makeTool({ output_globs: ['*.pdb'] })),
      inputSchema: computed(() => inputSchema),
      labels: computed(() => labels),
    })

    expect(configured.documentationMarkdown.value).toBe('## Custom Doc')
    expect(configured.documentationHtml.value).toContain('<h2>Custom Doc</h2>')
    expect(fallback.documentationMarkdown.value).toContain('Remote model endpoint')
    expect(fallback.documentationMarkdown.value).toContain('*.pdb')
  })
})
