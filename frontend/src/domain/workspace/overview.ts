import dayjs from 'dayjs'
import type { WorkspaceArtifact, WorkspaceAttentionTask, WorkspaceLegacyFile } from '@/api/workspace'
import type { SystemHealth } from '@/types/models'
import type { ResearchProject } from '@/types/projects'

export interface RecentWorkspaceArtifactRow {
  id: string
  name: string
  typeLabel: string
  sizeBytes: number
  downloadUrl: string
}

export interface BuildRecentWorkspaceArtifactRowsOptions {
  artifacts: WorkspaceArtifact[]
  legacyFiles: WorkspaceLegacyFile[]
  unknownArtifactTypeLabel: string
  buildArtifactDownloadUrl: (artifactId: string, versionId: string) => string
}

export function getRecentWorkspaceProjects(
  projects: ResearchProject[],
  limit = 8
): ResearchProject[] {
  return projects.slice(0, limit)
}

export function getWorkspaceAttentionTasks(
  tasks: WorkspaceAttentionTask[],
  limit = 6
): WorkspaceAttentionTask[] {
  return tasks.filter(task => task.status === 'pending' || task.status === 'failure').slice(0, limit)
}

export function buildRecentWorkspaceArtifactRows({
  artifacts,
  legacyFiles,
  unknownArtifactTypeLabel,
  buildArtifactDownloadUrl
}: BuildRecentWorkspaceArtifactRowsOptions): RecentWorkspaceArtifactRow[] {
  const standardArtifacts = artifacts.map(artifact => ({
    id: artifact.id,
    name: artifact.name,
    typeLabel: getWorkspaceArtifactTypeLabel(artifact, unknownArtifactTypeLabel),
    sizeBytes: artifact.latest_version.size_bytes,
    downloadUrl: buildArtifactDownloadUrl(artifact.id, artifact.latest_version.id)
  }))

  if (standardArtifacts.length) {
    return standardArtifacts.slice(0, 6)
  }

  return legacyFiles.slice(0, 6).map(file => ({
    id: file.id,
    name: file.filename,
    typeLabel: file.content_type || unknownArtifactTypeLabel,
    sizeBytes: file.size_bytes,
    downloadUrl: `/api/v1/files/${file.id}/download`
  }))
}

export function getWorkspaceTaskLabelKey(status: WorkspaceAttentionTask['status']): string {
  return status === 'pending' ? 'workspace.pendingApproval' : 'workspace.taskNeedsAttention'
}

export function formatWorkspaceTime(value: string): string {
  return dayjs(value).format('MM-DD HH:mm')
}

export function formatWorkspaceFileSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function hasWorkspaceSchemaMigrationHealthIssue(
  services: SystemHealth['services'] | undefined
): boolean {
  return (services ?? []).some(
    service => service.name === 'database_schema' && service.status !== 'healthy'
  )
}

function getWorkspaceArtifactTypeLabel(
  artifact: WorkspaceArtifact,
  unknownArtifactTypeLabel: string
): string {
  if (artifact.standard_type) {
    return `${artifact.standard_type}@${artifact.standard_version ?? 1}`
  }
  return artifact.semantic_type || artifact.artifact_type || unknownArtifactTypeLabel
}
