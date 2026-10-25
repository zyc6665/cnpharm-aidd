import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  buildProjectTaskPath,
  buildProjectWorkflowPath,
  buildProjectWorkspaceNavItems,
  isProjectWorkspaceNavItemActive
} from './navigation'

test('项目工作台导航项覆盖所有项目内入口', () => {
  const items = buildProjectWorkspaceNavItems('project-1')

  assert.deepEqual(
    items.map(item => item.label),
    ['项目总览', '靶点与结构', 'Workflow', '任务中心', '数据资产', '结果中心', 'Artifact 谱系', '项目设置']
  )
  assert.deepEqual(
    items.map(item => item.to),
    [
      '/projects/project-1',
      '/projects/project-1/targets',
      '/projects/project-1/workflow',
      '/tasks?project_id=project-1',
      '/projects/project-1/assets',
      '/projects/project-1/results',
      '/projects/project-1/lineage',
      '/projects/project-1/settings'
    ]
  )
})

test('项目任务路径编码 project_id，项目工作流路径保持项目路由', () => {
  assert.equal(buildProjectTaskPath('project 1'), '/tasks?project_id=project%201')
  assert.equal(buildProjectWorkflowPath('project-1'), '/projects/project-1/workflow')
})

test('项目工作台导航 active 规则支持普通项目路径和任务中心 query', () => {
  const [overview, targets, workflow, tasks] = buildProjectWorkspaceNavItems('project-1')

  assert.equal(
    isProjectWorkspaceNavItemActive(overview!, {
      currentPath: '/projects/project-1/settings',
      currentProjectId: 'project-1'
    }),
    true
  )
  assert.equal(
    isProjectWorkspaceNavItemActive(targets!, {
      currentPath: '/projects/project-1/targets/target-1',
      currentProjectId: 'project-1'
    }),
    true
  )
  assert.equal(
    isProjectWorkspaceNavItemActive(workflow!, {
      currentPath: '/projects/project-1/workflow/runs',
      currentProjectId: 'project-1'
    }),
    true
  )
  assert.equal(
    isProjectWorkspaceNavItemActive(tasks!, {
      currentPath: '/tasks',
      currentProjectId: 'project-1',
      queryProjectId: 'project-1'
    }),
    true
  )
  assert.equal(
    isProjectWorkspaceNavItemActive(tasks!, {
      currentPath: '/tasks',
      currentProjectId: 'project-1',
      queryProjectId: 'project-2'
    }),
    false
  )
})
