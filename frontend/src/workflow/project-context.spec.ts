import { describe, expect, it } from 'vitest'
import {
  buildWorkflowDefinitionListParams,
  buildWorkflowRunListParams,
  resolveWorkflowRouteProjectId
} from './project-context'

describe('workflow project context', () => {
  it('prefers route params projectId over query project_id', () => {
    expect(
      resolveWorkflowRouteProjectId({
        paramsProjectId: ' project-1 ',
        queryProjectId: 'project-2'
      })
    ).toBe('project-1')
  })

  it('falls back to query project_id and ignores blank or non-string values', () => {
    expect(
      resolveWorkflowRouteProjectId({
        paramsProjectId: '',
        queryProjectId: ' project-2 '
      })
    ).toBe('project-2')
    expect(
      resolveWorkflowRouteProjectId({
        paramsProjectId: ['project-1'],
        queryProjectId: ['project-2']
      })
    ).toBeUndefined()
  })

  it('builds project-scoped workflow definition list params', () => {
    expect(buildWorkflowDefinitionListParams('project-1')).toEqual({
      page: 1,
      page_size: 100,
      project_id: 'project-1'
    })
    expect(buildWorkflowDefinitionListParams(undefined)).toEqual({ page: 1, page_size: 100 })
  })

  it('builds workflow run list params with optional project and definition scope', () => {
    expect(
      buildWorkflowRunListParams({
        projectId: 'project-1',
        workflowDefinitionId: 'workflow-1',
        page: 2,
        pageSize: 10
      })
    ).toEqual({
      page: 2,
      page_size: 10,
      project_id: 'project-1',
      workflow_definition_id: 'workflow-1'
    })
    expect(buildWorkflowRunListParams({ page: 1, pageSize: 20 })).toEqual({
      page: 1,
      page_size: 20
    })
  })
})
