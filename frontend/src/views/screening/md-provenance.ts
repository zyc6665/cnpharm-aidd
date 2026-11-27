import type { Task } from '@/types/models'

function nonEmptyString(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value.trim() : ''
}
export function resolveMdProvenance(detail: Task | null, fallbackProjectId: string): Record<string, string> {
  const projectId = nonEmptyString(detail?.project_id) || nonEmptyString(fallbackProjectId)
  if (!projectId) return {}
  const query: Record<string, string> = { project_id: projectId }
  const receptorSnap = (detail?.input_snapshots ?? []).find(snap =>
    /protein|receptor/i.test(String(snap.inputRole ?? '')) && ['protein_structure', 'file', 'artifact_version'].includes(snap.entityType ?? '')
  )
  const inputs = (detail?.inputs ?? {}) as Record<string, unknown>
  const targetId = nonEmptyString(receptorSnap?.detail?.target_id) || nonEmptyString(inputs.target_id)
  const proteinId = nonEmptyString(receptorSnap?.detail?.protein_id) || nonEmptyString(inputs.protein_id)
  const snapFileId = nonEmptyString(receptorSnap?.fileId)
  const rawStructureId = nonEmptyString(receptorSnap?.detail?.structure_id) || nonEmptyString(inputs.structure_id) ||
    (receptorSnap?.entityType === 'protein_structure' ? nonEmptyString(receptorSnap.entityId) : '')
  const structureId = rawStructureId && rawStructureId !== snapFileId ? rawStructureId : ''
  if (targetId) query.target_id = targetId
  if (targetId && proteinId) query.protein_id = proteinId
  if (targetId && proteinId && structureId) query.structure_id = structureId
  return query
}
