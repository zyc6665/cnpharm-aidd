import { test } from 'vitest'
import assert from 'node:assert/strict'
import type { WorkspaceArtifact, WorkspaceAttentionTask, WorkspaceLegacyFile } from '@/api/workspace'
import type { ResearchProject } from '@/types/projects'
import {
  buildRecentWorkspaceArtifactRows,
  formatWorkspaceFileSize,
  formatWorkspaceTime,
  getRecentWorkspaceProjects,
  getWorkspaceAttentionTasks,
  getWorkspaceTaskLabelKey,
  hasWorkspaceSchemaMigrationHealthIssue
} from './overview'

const projects = Array.from({ length: 10 }, (_, index) => ({
  id: `project-${index}`,
  name: `Project ${index}`
})) as ResearchProject[]

const tasks: WorkspaceAttentionTask[] = [
  createTask({ id: 'success', status: 'success', name: 'done' }),
  createTask({ id: 'pending', status: 'pending', name: 'wait' }),
  createTask({ id: 'running', status: 'running', name: 'run' }),
  createTask({ id: 'failure', status: 'failure', name: 'fail', error_message: 'failed' })
]

function createTask(input: {
  id: string
  status: WorkspaceAttentionTask['status']
  name: string
  error_message?: string
}): WorkspaceAttentionTask {
  return {
    id: input.id,
    status: input.status,
    name: input.name,
    progress: 0,
    error_message: input.error_message,
    tool_id: 'tool-1',
    created_at: '2026-08-05T00:00:00Z',
    updated_at: '2026-08-05T00:00:00Z'
  }
}

const fakeTranslate = (key: string): string =>
  ({
    'artifacts.type.bindingPocket': '结合口袋',
    'artifacts.type.moleculeTable': '分子表',
    'artifacts.type.unknown': '其他产物'
  })[key] ?? key

const artifact: WorkspaceArtifact = {
  id: 'artifact-1',
  project_id: 'project-1',
  name: 'Pocket',
  artifact_type: 'pocket',
  semantic_type: 'pocket_prediction',
  standard_type: 'pocket.pdb',
  standard_version: 2,
  latest_version: {
    id: 'version-1',
    version: 1,
    filename: 'pocket.pdb',
    size_bytes: 2048,
    sha256: 'sha256',
    status: 'available',
    created_at: '2026-08-05T00:00:00Z'
  },
  created_at: '2026-08-05T00:00:00Z',
  updated_at: '2026-08-05T00:00:00Z'
}

const legacyFile: WorkspaceLegacyFile = {
  id: 'file-1',
  filename: 'legacy.pdb',
  content_type: 'chemical/x-pdb',
  size_bytes: 4096,
  updated_at: '2026-08-05T00:00:00Z'
}

test('工作台最近项目和待关注任务保持页面展示上限', () => {
  assert.deepEqual(getRecentWorkspaceProjects(projects).map(project => project.id), [
    'project-0',
    'project-1',
    'project-2',
    'project-3',
    'project-4',
    'project-5',
    'project-6',
    'project-7'
  ])
  assert.deepEqual(getWorkspaceAttentionTasks(tasks).map(task => task.id), ['pending', 'failure'])
})

test('工作台 Artifact 展示优先使用标准 Artifact，缺失时回退 legacy file', () => {
  const standardRows = buildRecentWorkspaceArtifactRows({
    artifacts: [artifact],
    legacyFiles: [legacyFile],
    unknownArtifactTypeLabel: '未知类型',
    buildArtifactDownloadUrl: (artifactId, versionId) => `/artifacts/${artifactId}/${versionId}`,
    translate: fakeTranslate
  })

  assert.deepEqual(standardRows, [
    {
      id: 'artifact-1',
      title: 'Pocket',
      typeLabel: '其他产物',
      fileName: 'pocket.pdb',
      sizeBytes: 2048,
      updatedAt: '2026-08-05T00:00:00Z',
      downloadUrl: '/artifacts/artifact-1/version-1'
    }
  ])

  const legacyRows = buildRecentWorkspaceArtifactRows({
    artifacts: [],
    legacyFiles: [legacyFile],
    unknownArtifactTypeLabel: '未知类型',
    buildArtifactDownloadUrl: (artifactId, versionId) => `/artifacts/${artifactId}/${versionId}`,
    translate: fakeTranslate
  })

  assert.deepEqual(legacyRows, [
    {
      id: 'file-1',
      title: 'legacy.pdb',
      typeLabel: 'chemical/x-pdb',
      fileName: 'legacy.pdb',
      sizeBytes: 4096,
      updatedAt: '2026-08-05T00:00:00Z',
      downloadUrl: '/api/v1/files/file-1/download'
    }
  ])
})

test('工作台任务文案 key 与时间大小格式保持旧页面约定', () => {
  assert.equal(getWorkspaceTaskLabelKey('pending'), 'workspace.pendingApproval')
  assert.equal(getWorkspaceTaskLabelKey('failure'), 'workspace.taskNeedsAttention')
  assert.equal(formatWorkspaceTime('2026-08-05T01:02:03Z'), '08-05 01:02')
  assert.equal(formatWorkspaceFileSize(0), '0 B')
  assert.equal(formatWorkspaceFileSize(1536), '1.5 KB')
  assert.equal(formatWorkspaceFileSize(1048576), '1 MB')
})

test('工作台 schema 迁移错误只由 database_schema 非健康状态触发', () => {
  assert.equal(
    hasWorkspaceSchemaMigrationHealthIssue([
      { name: 'database_schema', status: 'healthy', message: 'ok' },
      { name: 'cache', status: 'unhealthy', message: 'down' }
    ]),
    false
  )
  assert.equal(
    hasWorkspaceSchemaMigrationHealthIssue([
      { name: 'database_schema', status: 'unhealthy', message: 'missing migration' }
    ]),
    true
  )
})
