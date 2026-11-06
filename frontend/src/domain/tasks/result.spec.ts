import { describe, expect, it } from 'vitest'
import { STRUCTURE_PREDICT_TOOL_SLUG, POCKET_PREDICT_TOOL_SLUG } from '@/types/design'
import {
  getPocketCount,
  getPocketResultRows,
  getTaskResultArtifacts,
  getTaskResultMetrics,
  resolveTaskResultKind,
} from './result'
import type { Task } from '@/types/models'

function makeTask(result: Record<string, unknown> | null): Task {
  return {
    id: 't1',
    tool_id: 'tool-1',
    status: 'success',
    progress: 100,
    created_at: '2026-11-06T00:00:00Z',
    outputs: result ? { result, file_ids: [], output_type: 'json' } : undefined,
  }
}

describe('resolveTaskResultKind', () => {
  it('maps design categories to result views', () => {
    expect(resolveTaskResultKind(STRUCTURE_PREDICT_TOOL_SLUG)).toBe('structure')
    expect(resolveTaskResultKind(POCKET_PREDICT_TOOL_SLUG)).toBe('pocket')
    expect(resolveTaskResultKind('pocket2mol-pocket-ligand-generation')).toBe('generation')
    expect(resolveTaskResultKind('therapainter-peptide-prediction')).toBe('generation')
    expect(resolveTaskResultKind('molp-pc-property-prediction')).toBe('predict')
    expect(resolveTaskResultKind('builtin-vina-docking')).toBe('screening')
    expect(resolveTaskResultKind('gromacs-md')).toBe('md')
    expect(resolveTaskResultKind('gmx-mmpbsa')).toBe('freeEnergy')
  })

  it('falls back to generic for unknown tools', () => {
    expect(resolveTaskResultKind('unknown-tool')).toBe('generic')
    expect(resolveTaskResultKind(undefined)).toBe('generic')
  })
})

describe('task result payload helpers', () => {
  it('reads metrics and artifacts from the nested result envelope', () => {
    const task = makeTask({
      success: true,
      result: {
        artifacts: { pocket: { type: 'binding_pocket@1', files: { atom_pocket_pdb: { path: 'pocket0.pdb' } } } },
        metrics: {
          pocket_count: 2,
          pockets: [
            { id: 'P1', pdb: 'artifacts/lv_results/protein/pocket0.pdb' },
            { id: 'P2', pdb: 'pocket1.pdb' },
          ],
        },
      },
    })

    expect(getTaskResultMetrics(task).pocket_count).toBe(2)
    expect(Object.keys(getTaskResultArtifacts(task))).toEqual(['pocket'])
    expect(getPocketCount(task)).toBe(2)
    expect(getPocketResultRows(task).map(row => row.id)).toEqual(['P1', 'P2'])
    expect(getPocketResultRows(task)[0]?.atomPdb).toBe('pocket0.pdb')
  })

  it('returns empty values when there is no output', () => {
    expect(getTaskResultMetrics(makeTask(null))).toEqual({})
    expect(getTaskResultArtifacts(makeTask(null))).toEqual({})
    expect(getPocketCount(makeTask(null))).toBe(0)
  })
})
