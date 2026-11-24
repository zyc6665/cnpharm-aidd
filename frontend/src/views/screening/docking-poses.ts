import type { PoseMetadata, PosesMetadata } from '@/types/screening'

export interface DockingPoseCatalogEntry {
  pose: PoseMetadata
  recordIndex: number
  sourceOrder: number
}

export function resolveDockingPose(catalog: readonly DockingPoseCatalogEntry[], id: string): DockingPoseCatalogEntry | null {
  const exact = catalog.filter(entry => entry.pose.pose_id === id)
  if (exact.length === 1) return exact[0]!
  if (exact.length > 1) return null
  const rankMatch = /^pose-([1-9]\d*)$/.exec(id)
  if (!rankMatch) return null
  const ranked = catalog.filter(entry => entry.pose.rank === Number(rankMatch[1]))
  return ranked.length === 1 ? ranked[0]! : null
}

export function sortDockingPoseCatalog(poses: PosesMetadata['poses']): DockingPoseCatalogEntry[] {
  return poses.map((pose, sourceOrder) => ({ pose, recordIndex: sourceOrder, sourceOrder }))
    .sort((a, b) => a.pose.rank - b.pose.rank || a.sourceOrder - b.sourceOrder)
}

export function findUniquePoseByTitle(titles: readonly string[], moleculeId: string): number | null {
  const matches = titles.map((title, index) => title.trim() === moleculeId.trim() ? index : -1).filter(index => index >= 0)
  return matches.length === 1 ? matches[0]! : null
}

export interface ParsedResidueFocus {
  chain?: string
  authSeqId: number
  insertionCode?: string
}

export interface DockingTaskCacheEntry {
  taskId: string
  catalog: DockingPoseCatalogEntry[]
  sdfText: string
  receptorText: string | null
  receptorFormat: { format: 'pdb' | 'mmcif' | 'pdbqt'; extension: string } | null
  receptorUnavailable: boolean
}

let cachedTaskEntry: DockingTaskCacheEntry | null = null

/** Retrieve cached docking catalog and structure payloads for the active task across pose switches. */
export function getCachedDockingTask(taskId: string): DockingTaskCacheEntry | null {
  return cachedTaskEntry && cachedTaskEntry.taskId === taskId ? cachedTaskEntry : null
}

/** Store the active docking task bundle so pose stepping via route changes avoids redundant API refetches. */
export function setCachedDockingTask(entry: DockingTaskCacheEntry): void {
  cachedTaskEntry = entry
}

export function parseResidueFocus(residue: string, chain?: string): ParsedResidueFocus | null {
  const cleaned = residue.trim()
  const match = /^(?:([A-Za-z0-9]+):)?[A-Za-z]{0,4}(\d+)([A-Za-z])?$/.exec(cleaned)
  if (!match) return null
  const authSeqId = Number(match[2])
  if (!Number.isInteger(authSeqId)) return null
  const explicitChain = chain?.trim() || match[1]?.trim() || undefined
  const insertionCode = match[3]?.trim() || undefined
  return {
    authSeqId,
    ...(explicitChain ? { chain: explicitChain } : {}),
    ...(insertionCode ? { insertionCode } : {}),
  }
}
