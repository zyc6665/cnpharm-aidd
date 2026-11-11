import { buildArtifactDisplay } from '@/domain/artifacts/presentation'
import { formatMonthDayMinutes } from '@/utils/datetime'
import type { WorkspaceArtifact, WorkspaceAttentionTask, WorkspaceLegacyFile } from '@/api/workspace'
import type { SystemHealth } from '@/types/models'
import type { ResearchProject } from '@/types/projects'

export interface RecentWorkspaceArtifactRow {
  id: string
  /** 用户读得懂的标题：可能是后端可读名，也可能是「类型名 · vN」。 */
  title: string
  /** 类型中文名（`分子表`、`结合口袋`…），不再是 `molecule_table@1`。 */
  typeLabel: string
  /** 真实文件名，作为次要信息保留；没有则为 null。 */
  fileName: string | null
  sizeBytes: number
  /** ISO 时间串，由页面按用户时区渲染。 */
  updatedAt: string
  downloadUrl: string
}

export interface BuildRecentWorkspaceArtifactRowsOptions {
  artifacts: WorkspaceArtifact[]
  legacyFiles: WorkspaceLegacyFile[]
  unknownArtifactTypeLabel: string
  buildArtifactDownloadUrl: (artifactId: string, versionId: string) => string
  /** i18n 翻译函数；类型名文案由 `artifacts.type.*` 提供。 */
  translate: (key: string) => string
}

export function getRecentWorkspaceProjects(
  projects: ResearchProject[],
  limit = 8
): ResearchProject[] {
  return projects.slice(0, limit)
}

/**
 * 把项目分成「在用」与「已归档」两组。
 *
 * 归档的语义是「从默认列表移走，但记录都还在」，所以它既不能被当成删除（数据还在），
 * 也不能混在常用列表里（会稀释「我正在做的项目」）。分组这一步放在这里，
 * 页面只负责渲染两个 section。
 */
export function partitionWorkspaceProjects(projects: ResearchProject[]): {
  active: ResearchProject[]
  archived: ResearchProject[]
} {
  const active: ResearchProject[] = []
  const archived: ResearchProject[] = []
  for (const project of projects) {
    if (project.status === 'archived') {
      archived.push(project)
    } else {
      active.push(project)
    }
  }
  return { active, archived }
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
  buildArtifactDownloadUrl,
  translate
}: BuildRecentWorkspaceArtifactRowsOptions): RecentWorkspaceArtifactRow[] {
  const standardArtifacts = artifacts.map(artifact => {
    const display = buildArtifactDisplay(
      {
        name: artifact.name,
        artifactType: artifact.artifact_type,
        semanticType: artifact.semantic_type,
        standardType: artifact.standard_type,
        version: artifact.latest_version.version,
        filename: artifact.latest_version.filename
      },
      translate
    )
    return {
      id: artifact.id,
      title: display.title,
      typeLabel: translate(display.typeKey),
      fileName: display.fileName,
      sizeBytes: artifact.latest_version.size_bytes,
      updatedAt: artifact.updated_at,
      downloadUrl: buildArtifactDownloadUrl(artifact.id, artifact.latest_version.id)
    }
  })

  if (standardArtifacts.length) {
    return standardArtifacts.slice(0, 6)
  }

  return legacyFiles.slice(0, 6).map(file => ({
    id: file.id,
    title: file.filename,
    typeLabel: file.content_type || unknownArtifactTypeLabel,
    fileName: file.filename,
    sizeBytes: file.size_bytes,
    updatedAt: file.updated_at,
    downloadUrl: `/api/v1/files/${file.id}/download`
  }))
}

export function getWorkspaceTaskLabelKey(status: WorkspaceAttentionTask['status']): string {
  return status === 'pending' ? 'workspace.pendingApproval' : 'workspace.taskNeedsAttention'
}

export function formatWorkspaceTime(value: string): string {
  return formatMonthDayMinutes(value)
}

export { formatBytes as formatWorkspaceFileSize } from '@/domain/common/format'

export function hasWorkspaceSchemaMigrationHealthIssue(
  services: SystemHealth['services'] | undefined
): boolean {
  return (services ?? []).some(
    service => service.name === 'database_schema' && service.status !== 'healthy'
  )
}

