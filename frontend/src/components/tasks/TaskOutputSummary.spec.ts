import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import TaskOutputSummary from './TaskOutputSummary.vue'
import type { Task } from '@/types/models'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key })
}))

vi.mock('@/utils/protected-file-access', () => ({
  fetchProtectedFileText: vi.fn(),
  triggerProtectedFileDownload: vi.fn()
}))

const baseTask: Task = {
  id: 'task-1',
  tool_id: 'tool-1',
  status: 'success',
  progress: 100,
  created_at: '2026-09-08T00:00:00Z',
  outputs: {
    result: null,
    file_ids: [],
    output_type: 'json'
  },
  output_files: []
}

const stubs = {
  AButton: { template: '<button><slot /></button>' },
  DownloadOutlined: true,
  FileOutlined: true,
  JsonResultRenderer: { template: '<div data-testid="json-result-renderer" />' }
}

describe('TaskOutputSummary', () => {
  it('shows MolP-PC scientific attachment refs from the full task result', () => {
    const task: Task = {
      ...baseTask,
      output_data: { success: true },
      outputs: {
        result: {
          result: { success: true },
          standard_result: {
            result_version: 'aidd.sciminer/result',
            artifacts: {
              report: {
                type: 'run_report@1',
                metadata: {
                  model_card_ref: 'example/MolP-PC/tool-package-v2/docs/model-card.md',
                  verification_record_ref:
                    'example/MolP-PC/tool-package-v2/docs/verification-record.md',
                  evidence_level: 'engineering_smoke_only'
                }
              }
            }
          }
        },
        file_ids: [],
        output_type: 'json'
      }
    }

    const wrapper = mount(TaskOutputSummary, {
      props: { task },
      global: { stubs }
    })

    const attachments = wrapper.get('[data-testid="task-scientific-attachments"]')
    expect(attachments.text()).toContain('tasks.scientificAttachments')
    expect(attachments.text()).toContain('example/MolP-PC/tool-package-v2/docs/model-card.md')
    expect(attachments.text()).toContain(
      'example/MolP-PC/tool-package-v2/docs/verification-record.md'
    )
    expect(attachments.text()).toContain('engineering_smoke_only')
  })
})
