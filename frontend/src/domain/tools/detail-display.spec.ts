import { describe, expect, it } from 'vitest'
import type { TypedArtifact } from '@/types/artifacts'
import {
  formatStandardArtifactLabel,
  formatToolDate,
  formatToolMetricCount,
  getToolStatusColor,
} from './detail-display'

function makeArtifact(overrides: Partial<TypedArtifact> = {}): TypedArtifact {
  return {
    id: 'artifact-1',
    project_id: 'project-1',
    artifact_type: 'protein_structure@1',
    semantic_type: 'protein_structure@1',
    name: 'Target Protein',
    latest_version: {
      id: 'version-1',
      version: 3,
      filename: 'target.pdb',
      content_type: 'chemical/x-pdb',
      size_bytes: 123,
      sha256: 'abc',
      status: 'available',
      created_at: '2026-08-02T00:00:00Z',
    },
    created_at: '2026-08-02T00:00:00Z',
    updated_at: '2026-08-02T00:00:00Z',
    ...overrides,
  }
}

describe('tool detail display rules', () => {
  it('formats metric counts with compact suffixes', () => {
    expect(formatToolMetricCount(undefined)).toBe('0')
    expect(formatToolMetricCount(null)).toBe('0')
    expect(formatToolMetricCount(999)).toBe('999')
    expect(formatToolMetricCount(1200)).toBe('1.2k')
    expect(formatToolMetricCount(15500)).toBe('1.6w')
  })

  it('maps tool status values to Ant Design tag colors', () => {
    expect(getToolStatusColor('draft')).toBe('default')
    expect(getToolStatusColor('published')).toBe('success')
    expect(getToolStatusColor('disabled')).toBe('warning')
    expect(getToolStatusColor('deprecated')).toBe('error')
    expect(getToolStatusColor('unknown')).toBe('default')
  })

  it('formats dates through the native locale formatter', () => {
    expect(formatToolDate('2026-08-02T00:00:00Z')).toBe(
      new Date('2026-08-02T00:00:00Z').toLocaleDateString()
    )
  })

  it('builds readable standard artifact option labels', () => {
    expect(formatStandardArtifactLabel(makeArtifact())).toBe(
      'Target Protein · v3'
    )

    expect(formatStandardArtifactLabel(makeArtifact({ name: '' }))).toBe(
      'target.pdb · v3'
    )
  })
})
