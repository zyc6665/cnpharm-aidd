import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import i18n from '@/locales'
import NodeResultPanel from './NodeResultPanel.vue'

vi.mock('@/utils/protected-file-access', () => ({
  triggerProtectedFileDownload: vi.fn(),
}))

describe('NodeResultPanel', () => {
  it('以用户可读的结果摘要展示任务，不暴露内部 ID', () => {
    const wrapper = mount(NodeResultPanel, {
      props: {
        node: {
          id: 'node-internal-1',
          type: 'tool',
          titleKey: 'workflow.canvasNode.titleFallback',
          position: { x: 0, y: 0 },
        } as never,
        task: {
          id: 'task-internal-1',
          status: 'success',
          progress: 100,
          output_files: [
            {
              id: 'file-internal-1',
              filename: 'generated_molecules.sdf',
              content_type: 'chemical/x-mdl-sdfile',
              size: 2048,
              url: '/api/v1/files/file-internal-1/download',
            },
          ],
        } as never,
        artifacts: [
          {
            id: 'artifact-internal-1',
            filename: 'generated_molecules.sdf',
            content_type: 'chemical/x-mdl-sdfile',
            size_bytes: 2048,
            source_type: 'task',
            download_url: '/api/v1/files/another-internal-id/download',
            task_id: 'task-internal-1',
            tool_id: 'tool-1',
            tool_name: 'Pocket2Mol',
            tool_slug: 'pocket2mol',
            created_at: '2026-10-02T00:00:00Z',
          },
        ] as never,
        selectedToolSlug: 'pocket2mol',
      },
      global: {
        plugins: [i18n],
        stubs: {
          AButton: { template: '<button><slot /></button>' },
          AProgress: { template: '<div data-testid="progress" />' },
          ATag: { template: '<span><slot /></span>' },
          AEmpty: { template: '<div><slot /></div>' },
        },
      },
    })

    expect(wrapper.text()).toContain('已完成')
    expect(wrapper.text()).toContain('generated_molecules.sdf')
    expect(wrapper.text()).toContain('2 KB')
    expect(wrapper.findAll('.output-file-name')).toHaveLength(1)
    expect(wrapper.text()).not.toContain('task-internal-1')
    expect(wrapper.text()).not.toContain('file-internal-1')
    expect(wrapper.text()).not.toContain('artifact-internal-1')
  })
})
