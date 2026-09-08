import { describe, expect, it } from 'vitest'
import type { Task } from '@/types/models'
import {
  getTaskScientificAttachmentEntries,
  getTaskOutputDataEntries,
  getTaskOutputFiles,
  hasTaskOutputSummaryContent,
} from './output-summary'

function task(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    tool_id: 'tool-1',
    status: 'success',
    progress: 100,
    created_at: '2026-08-05T06:00:00Z',
    ...overrides,
  }
}

describe('task output summary rules', () => {
  it('returns entries only for object output data', () => {
    expect(getTaskOutputDataEntries({ score: 0.9, label: 'hit' })).toEqual([
      ['score', 0.9],
      ['label', 'hit'],
    ])
    expect(getTaskOutputDataEntries(null)).toEqual([])
    expect(getTaskOutputDataEntries(['not', 'summary'])).toEqual([])
  })

  it('normalizes missing output files to an empty list', () => {
    expect(getTaskOutputFiles(task())).toEqual([])
    expect(
      getTaskOutputFiles(
        task({ output_files: [{ id: 'file-1', filename: 'result.csv', size: 1024 }] })
      ).map(file => file.filename)
    ).toEqual(['result.csv'])
  })

  it('reports summary content when data entries or files exist', () => {
    expect(hasTaskOutputSummaryContent(null, [])).toBe(false)
    expect(hasTaskOutputSummaryContent({ score: 0.9 }, [])).toBe(true)
    expect(hasTaskOutputSummaryContent(null, [{ filename: 'result.csv' }])).toBe(true)
  })

  it('extracts scientific attachment refs from MolP-PC standard results', () => {
    const entries = getTaskScientificAttachmentEntries({
      result: { success: true },
      standard_result: {
        result_version: 'aidd.sciminer/result.v2',
        artifacts: {
          report: {
            type: 'run_report@1',
            metadata: {
              model_card_ref: 'example/MolP-PC/tool-package-v2/docs/model-card.md',
              verification_record_ref:
                'example/MolP-PC/tool-package-v2/docs/verification-record.md',
              evidence_level: 'engineering_smoke_only',
            },
          },
        },
      },
    })

    expect(entries).toEqual([
      {
        key: 'model_card_ref',
        labelKey: 'tasks.scientificModelCard',
        value: 'example/MolP-PC/tool-package-v2/docs/model-card.md',
      },
      {
        key: 'verification_record_ref',
        labelKey: 'tasks.scientificVerificationRecord',
        value: 'example/MolP-PC/tool-package-v2/docs/verification-record.md',
      },
      {
        key: 'evidence_level',
        labelKey: 'tasks.scientificEvidenceLevel',
        value: 'engineering_smoke_only',
      },
    ])
  })
})
