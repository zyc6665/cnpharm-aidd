import dayjs from 'dayjs'
import type { TypedArtifact } from '@/types/artifacts'
import type { ProjectOverviewCounts } from '@/types/projects'

export interface ProjectOverviewStatCard {
  label: string
  value: number
}

export function getProjectOverviewStatCards(
  counts: ProjectOverviewCounts | undefined
): ProjectOverviewStatCard[] {
  return [
    { label: 'Artifact', value: counts?.artifacts ?? 0 },
    { label: '任务', value: counts?.tasks ?? 0 },
    { label: '工作流', value: counts?.workflows ?? 0 },
    { label: '白板', value: counts?.boards ?? 0 }
  ]
}

export function getProjectArtifactTypeLabel(
  artifact: Pick<
    TypedArtifact,
    'artifact_type' | 'semantic_type' | 'standard_type' | 'standard_version'
  >
): string {
  return artifact.standard_type
    ? `${artifact.standard_type}@${artifact.standard_version ?? 1}`
    : artifact.semantic_type || artifact.artifact_type
}

export function formatProjectResourceTime(value: string): string {
  return dayjs(value).format('YYYY-MM-DD HH:mm')
}

export function formatProjectResourceSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
