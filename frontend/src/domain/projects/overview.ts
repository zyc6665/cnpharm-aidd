import dayjs from 'dayjs'
import type { TypedArtifact } from '@/types/artifacts'
import type { ProjectOverviewCounts } from '@/types/projects'

export interface ProjectOverviewStatCard {
  label: string
  value: number
}

export interface ProjectArtifactFilterPreset {
  key: 'recent' | 'protein_structure' | 'molecule_table' | 'molp_pc'
  label: string
  params?: {
    standard_type?: string
    metadata_model_name?: string
  }
}

export const PROJECT_ARTIFACT_FILTER_PRESETS: readonly ProjectArtifactFilterPreset[] = [
  { key: 'recent', label: '最近' },
  { key: 'protein_structure', label: '蛋白结构', params: { standard_type: 'protein_structure' } },
  { key: 'molecule_table', label: '分子表格', params: { standard_type: 'molecule_table' } },
  { key: 'molp_pc', label: 'MolP-PC', params: { metadata_model_name: 'MolP-PC' } }
]

export function resolveProjectArtifactFilterPreset(key: unknown): ProjectArtifactFilterPreset {
  if (typeof key !== 'string') return PROJECT_ARTIFACT_FILTER_PRESETS[0]!
  return PROJECT_ARTIFACT_FILTER_PRESETS.find(preset => preset.key === key)
    ?? PROJECT_ARTIFACT_FILTER_PRESETS[0]!
}

export function getProjectOverviewStatCards(
  counts: ProjectOverviewCounts | undefined
): ProjectOverviewStatCard[] {
  return [
    { label: 'Artifact', value: counts?.artifacts ?? 0 },
    { label: '任务', value: counts?.tasks ?? 0 },
    { label: '工作流', value: counts?.workflows ?? 0 }
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
