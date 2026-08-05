import { describe, expect, it } from 'vitest'
import type { Task } from '@/types/models'
import {
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
})
