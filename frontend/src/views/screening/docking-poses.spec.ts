import { describe, expect, it } from 'vitest'
import { findUniquePoseByTitle, resolveDockingPose, sortDockingPoseCatalog } from './docking-poses'

describe('docking pose catalog helpers', () => {
  const catalog = sortDockingPoseCatalog([
    { pose_id: 'b', rank: 2, docking_score: -7, rmsd_lb: 0, rmsd_ub: 0 },
    { pose_id: 'a', rank: 1, docking_score: -8, rmsd_lb: 0, rmsd_ub: 0 },
  ])
  it('sorts by rank and resolves exact ids before unambiguous legacy ranks', () => {
    expect(catalog.map(entry => entry.pose.pose_id)).toEqual(['a', 'b'])
    expect(resolveDockingPose(catalog, 'b')?.pose.pose_id).toBe('b')
    expect(resolveDockingPose(catalog, 'pose-1')?.pose.pose_id).toBe('a')
    expect(resolveDockingPose(catalog, 'pose-0')).toBeNull()
  })
  it('only resolves unique SDF titles', () => {
    expect(findUniquePoseByTitle(['one', 'two'], 'two')).toBe(1)
    expect(findUniquePoseByTitle(['two', 'two'], 'two')).toBeNull()
    expect(findUniquePoseByTitle(['one'], 'missing')).toBeNull()
  })
})
