import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ArtifactLineageGraph from './ArtifactLineageGraph.vue'
import type { ArtifactLineageGraph as ArtifactLineageGraphData } from '@/types/artifacts'
import { triggerProtectedFileDownload } from '@/utils/protected-file-access'

vi.mock('@/utils/protected-file-access', () => ({
  triggerProtectedFileDownload: vi.fn()
}))

const graph: ArtifactLineageGraphData = {
  project_id: 'project-1',
  summary: {
    artifacts: 1,
    versions: 1,
    tasks: 1,
    workflow_nodes: 1,
    lineage_edges: 1
  },
  nodes: [
    {
      id: 'artifact:artifact-1',
      kind: 'artifact',
      label: 'binding pocket',
      artifact_id: 'artifact-1',
      artifact_type: 'binding_pocket',
      standard_type: 'binding_pocket',
      standard_version: 1
    },
    {
      id: 'version:version-1',
      kind: 'version',
      label: 'pocket.pdb',
      artifact_id: 'artifact-1',
      version_id: 'version-1',
      version: 1,
      filename: 'pocket.pdb',
      status: 'available'
    },
    {
      id: 'task:task-1234567890',
      kind: 'task',
      label: 'LVpocket',
      task_id: 'task-1234567890',
      tool_slug: 'lvpocket',
      status: 'SUCCESS'
    },
    {
      id: 'workflow-node:run-1:pocket_prediction',
      kind: 'workflow_node',
      label: 'pocket_prediction',
      workflow_run_id: 'run-1',
      workflow_node_id: 'pocket_prediction',
      task_id: 'task-1234567890'
    }
  ],
  edges: [
    {
      id: 'edge-1',
      kind: 'produced_by',
      source: 'task:task-1234567890',
      target: 'version:version-1'
    }
  ]
}

const stubs = {
  AEmpty: true,
  ATag: { template: '<span><slot /></span>' },
  RouterLink: {
    props: ['to'],
    template: '<a :href="typeof to === \'string\' ? to : to.path"><slot /></a>'
  }
}

describe('ArtifactLineageGraph', () => {
  it('提供版本下载、来源任务和 workflow run 追溯入口', async () => {
    const wrapper = mount(ArtifactLineageGraph, {
      props: { graph },
      global: { stubs }
    })

    expect(wrapper.get('[data-testid="artifact-version-download"]').attributes('href')).toBe(
      '/api/v1/artifacts/artifact-1/versions/version-1/download'
    )
    expect(wrapper.get('[data-testid="lineage-task-link"]').attributes('href')).toBe(
      '/tasks/task-1234567890'
    )
    expect(wrapper.get('[data-testid="lineage-workflow-run-link"]').attributes('href')).toBe(
      '/workflow/runs/run-1'
    )

    await wrapper.get('[data-testid="artifact-version-download"]').trigger('click')

    expect(triggerProtectedFileDownload).toHaveBeenCalledWith({
      url: '/api/v1/artifacts/artifact-1/versions/version-1/download',
      filename: 'pocket.pdb'
    })
  })
})
