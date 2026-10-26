import { describe, expect, it } from 'vitest'
import {
  DECISION_PAGE_SIZE_OPTIONS,
  DECISION_POINT_OPTIONS,
  buildDecisionCreatePayload,
  clampDecisionPage,
  clampDecisionPageSize,
  formatSnapshotScore,
  groupDecisionsByPoint,
  isSnapshotScoreMissing,
  resolveDecisionErrorMessage,
  resolveDecisionSubjectLabel,
  summarizeDecisionCounts
} from './format'
import type { DecisionItem, DecisionRecord } from '@/types/decisions'

function item(overrides: Partial<DecisionItem> = {}): DecisionItem {
  return {
    candidate_id: 'candidate-1',
    verdict: 'SELECTED',
    snapshot_score: 0.85,
    snapshot_rank: 1,
    snapshot_attrs: {},
    ...overrides
  }
}

function record(overrides: Partial<DecisionRecord> = {}): DecisionRecord {
  return {
    id: 'decision-1',
    project_id: 'project-1',
    decision_point: 'DP3',
    subject_type: 'CANDIDATE_SET',
    subject_id: 'set-1',
    reason: '活性与选择性均达标',
    basis_task_ids: ['task-1'],
    basis_metrics: { pic50: 7.2 },
    decided_by: 'lead@example.com',
    decided_by_id: 'user-1',
    decided_at: '2026-10-01T00:00:00Z',
    created_at: '2026-10-01T00:00:00Z',
    selected_ids: ['candidate-1'],
    excluded_ids: [],
    items: [item()],
    ...overrides
  }
}

describe('groupDecisionsByPoint', () => {
  it('按决策点分组，组内与组间都保持时间倒序', () => {
    const newest = record({ id: 'd-3', decision_point: 'DP3', decided_at: '2026-10-05T00:00:00Z' })
    const other = record({ id: 'd-2', decision_point: 'DP1', decided_at: '2026-10-04T00:00:00Z' })
    const older = record({ id: 'd-1', decision_point: 'DP3', decided_at: '2026-10-02T00:00:00Z' })

    const groups = groupDecisionsByPoint([newest, other, older])

    expect(groups.map(group => group.point)).toEqual(['DP3', 'DP1'])
    expect(groups[0]?.records.map(row => row.id)).toEqual(['d-3', 'd-1'])
    expect(groups[1]?.records.map(row => row.id)).toEqual(['d-2'])
    expect(groups[0]?.labelKey).toBe('decisions.points.DP3')
  })

  it('输入未按时间排序时，组内仍然按决策时间倒序', () => {
    const older = record({ id: 'd-1', decided_at: '2026-10-01T00:00:00Z' })
    const newer = record({ id: 'd-2', decided_at: '2026-10-03T00:00:00Z' })

    const groups = groupDecisionsByPoint([older, newer])

    expect(groups).toHaveLength(1)
    expect(groups[0]?.records.map(row => row.id)).toEqual(['d-2', 'd-1'])
  })

  it('空数组返回空分组', () => {
    expect(groupDecisionsByPoint([])).toEqual([])
  })
})

describe('formatSnapshotScore / isSnapshotScoreMissing', () => {
  it('分数缺失时返回「未记录」文案 key', () => {
    const missing = item({ snapshot_score: null, snapshot_attrs: { score_source: 'missing' } })

    expect(isSnapshotScoreMissing(missing)).toBe(true)
    expect(formatSnapshotScore(missing)).toBe('decisions.snapshot.notRecorded')
  })

  it('score = 0 不能被当成缺失', () => {
    const zero = item({ snapshot_score: 0, snapshot_attrs: {} })

    expect(isSnapshotScoreMissing(zero)).toBe(false)
    expect(formatSnapshotScore(zero)).toBe('0')
  })

  it('正常分数按最多四位小数展示且不留尾零', () => {
    expect(formatSnapshotScore(item({ snapshot_score: 0.85 }))).toBe('0.85')
    expect(formatSnapshotScore(item({ snapshot_score: 1.234567 }))).toBe('1.2346')
  })
})

describe('summarizeDecisionCounts / resolveDecisionSubjectLabel', () => {
  it('统计入选与淘汰数量', () => {
    const summary = summarizeDecisionCounts([
      record({
        id: 'd-1',
        selected_ids: ['a', 'b'],
        excluded_ids: ['c'],
        items: [
          item({ candidate_id: 'a', verdict: 'SELECTED' }),
          item({ candidate_id: 'b', verdict: 'SELECTED' }),
          item({ candidate_id: 'c', verdict: 'EXCLUDED' })
        ]
      }),
      record({
        id: 'd-2',
        selected_ids: [],
        excluded_ids: ['d'],
        items: [item({ candidate_id: 'd', verdict: 'EXCLUDED' })]
      })
    ])

    expect(summary).toEqual({ selected: 2, excluded: 2, total: 2 })
  })

  it('对象标签给出 i18n key 与对象 ID', () => {
    expect(resolveDecisionSubjectLabel(record({ subject_type: 'POCKET', subject_id: 'pocket-9' }))).toEqual({
      typeKey: 'decisions.subjectTypes.POCKET',
      subjectId: 'pocket-9'
    })
  })
})

describe('分页参数守卫', () => {
  it('page 至少为 1，page_size 落在 1..100', () => {
    expect(clampDecisionPage(0)).toBe(1)
    expect(clampDecisionPage(-5)).toBe(1)
    expect(clampDecisionPage(Number.NaN)).toBe(1)
    expect(clampDecisionPage(3)).toBe(3)
    expect(clampDecisionPageSize(0)).toBe(1)
    expect(clampDecisionPageSize(500)).toBe(100)
    expect(clampDecisionPageSize(20)).toBe(20)
  })

  it('page_size 选项全部不超过 100', () => {
    expect(DECISION_PAGE_SIZE_OPTIONS.every(size => size >= 1 && size <= 100)).toBe(true)
  })
})

describe('buildDecisionCreatePayload', () => {
  const baseDraft = {
    decisionPoint: 'DP3' as const,
    subjectType: 'CANDIDATE_SET' as const,
    subjectId: 'set-1',
    reason: '活性与选择性均达标',
    selectedIdsText: 'candidate-1, candidate-2',
    excludedIdsText: 'candidate-3',
    basisTaskIdsText: 'task-1,task-2'
  }

  it('逗号分隔输入被拆成数组，并按结论自动生成未录分的快照', () => {
    const result = buildDecisionCreatePayload(baseDraft)

    expect(result.ok).toBe(true)
    if (!result.ok) {
      return
    }
    expect(result.payload.selected_ids).toEqual(['candidate-1', 'candidate-2'])
    expect(result.payload.excluded_ids).toEqual(['candidate-3'])
    expect(result.payload.basis_task_ids).toEqual(['task-1', 'task-2'])
    expect(result.payload.snapshot).toEqual([
      { candidate_id: 'candidate-1', score: null },
      { candidate_id: 'candidate-2', score: null },
      { candidate_id: 'candidate-3', score: null }
    ])
  })

  it('理由为空白时拒绝提交', () => {
    expect(buildDecisionCreatePayload({ ...baseDraft, reason: '   ' })).toEqual({
      ok: false,
      errorKey: 'decisions.drawer.reasonRequired'
    })
  })

  it('入选与淘汰同时为空时拒绝提交', () => {
    expect(
      buildDecisionCreatePayload({ ...baseDraft, selectedIdsText: '', excludedIdsText: '' })
    ).toEqual({ ok: false, errorKey: 'decisions.drawer.verdictRequired' })
  })

  it('同一个候选物同时入选与淘汰时拒绝提交', () => {
    expect(
      buildDecisionCreatePayload({ ...baseDraft, excludedIdsText: 'candidate-1' })
    ).toEqual({ ok: false, errorKey: 'decisions.drawer.verdictDuplicated' })
  })

  it('对象 ID 为空时拒绝提交', () => {
    expect(buildDecisionCreatePayload({ ...baseDraft, subjectId: '  ' })).toEqual({
      ok: false,
      errorKey: 'decisions.drawer.subjectRequired'
    })
  })
})

describe('DECISION_POINT_OPTIONS', () => {
  it('覆盖 DP1~DP5 且 label 走 i18n key', () => {
    expect(DECISION_POINT_OPTIONS.map(option => option.value)).toEqual([
      'DP1',
      'DP2',
      'DP3',
      'DP4',
      'DP5'
    ])
    expect(DECISION_POINT_OPTIONS.map(option => option.labelKey)).toEqual([
      'decisions.points.DP1',
      'decisions.points.DP2',
      'decisions.points.DP3',
      'decisions.points.DP4',
      'decisions.points.DP5'
    ])
  })
})

describe('resolveDecisionErrorMessage', () => {
  it('优先取后端 ApiResponse.message', () => {
    const cause = { response: { data: { message: '决策记录已存在，不能重复提交' } } }

    expect(resolveDecisionErrorMessage(cause, 'fallback')).toBe('决策记录已存在，不能重复提交')
  })

  it('没有响应体时退回 Error.message，最后才用 fallback', () => {
    expect(resolveDecisionErrorMessage(new Error('Network Error'), 'fallback')).toBe('Network Error')
    expect(resolveDecisionErrorMessage(undefined, 'fallback')).toBe('fallback')
  })
})
