import { test } from 'vitest'
import assert from 'node:assert/strict'
import type { Task } from '@/types/models'
import { getTaskArtifactLineagePath, getTaskProjectContextLabel } from './navigation'

function task(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    tool_id: 'tool-1',
    status: 'success',
    progress: 100,
    created_at: '2026-08-05T00:00:00Z',
    ...overrides
  }
}

test('项目上下文标签优先使用当前项目名称', () => {
  assert.equal(
    getTaskProjectContextLabel(task({ project_id: 'project-123456789' }), {
      currentProjectId: 'project-123456789',
      currentProjectName: '分子生成项目'
    }),
    '项目：分子生成项目'
  )
})

test('项目上下文标签缺少名称时回退到短项目 ID', () => {
  assert.equal(
    getTaskProjectContextLabel(task({ project_id: 'project-123456789' }), {
      currentProjectId: 'project-123456789'
    }),
    '项目：project-'
  )
  assert.equal(getTaskProjectContextLabel(task(), {}), '项目：-')
})

test('任务 Artifact 谱系路径使用项目路径，无项目时回到工作台', () => {
  assert.equal(
    getTaskArtifactLineagePath(task({ project_id: 'project-1' })),
    '/projects/project-1/lineage'
  )
  assert.equal(getTaskArtifactLineagePath(task()), '/workspace')
})
