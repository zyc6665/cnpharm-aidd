import { describe, expect, it } from 'vitest'
import type { ArtifactFile } from '../src/types/models'
import { sortArtifactsByCreatedAtDesc } from '../src/utils/artifact-sorting'

const artifacts = [
  { id: 'older', created_at: '2026-07-01T08:00:00Z' },
  { id: 'newer', created_at: '2026-07-01T10:00:00Z' },
  { id: 'middle', created_at: '2026-07-01T09:00:00Z' }
] as ArtifactFile[]

describe('sortArtifactsByCreatedAtDesc', () => {
  it('按创建时间倒序返回新数组，不修改输入数组', () => {
    const sorted = sortArtifactsByCreatedAtDesc(artifacts)

    expect(sorted.map(artifact => artifact.id)).toEqual(['newer', 'middle', 'older'])
    expect(artifacts.map(artifact => artifact.id)).toEqual(['older', 'newer', 'middle'])
  })
})
