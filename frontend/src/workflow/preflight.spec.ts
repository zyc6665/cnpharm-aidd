import { describe, expect, it } from 'vitest'
import type { ToolContract } from '@/types/models'
import type { WorkflowCanvasPreset } from './canvas-types'
import { buildWorkflowPreflight } from './preflight'

function makeToolContract(overrides: Partial<ToolContract> = {}): ToolContract {
  return {
    contract_version: '1.0',
    id: 'tool-1',
    slug: 'vina-docking',
    name: 'AutoDock Vina',
    description: null,
    status: 'published',
    is_public: true,
    version: { id: 'version-1', version: '1.0.0', is_active: true, deprecated: false },
    executor: { type: 'docker_image', timeout_sec: 10800 },
    resource_profile: {
      tier: 'medium',
      cpu: 8,
      memory_gb: 16,
      gpu_required: false,
      expected_minutes: 30,
      timeout_minutes: 180,
    },
    schema: {
      input: { type: 'object', properties: {} },
      output: { type: 'object', properties: {} },
    },
    capability: {
      enabled: true,
      capability: 'molecular_docking',
      stage: 'docking_scoring',
      inputs: [],
      outputs: [],
      defaults: {},
      virtual: false,
    },
    validation: { status: 'valid', errors: [] },
    ...overrides,
  }
}

describe('buildWorkflowPreflight', () => {
  it('汇总可运行节点的工具执行器和资源画像', () => {
    const template: WorkflowCanvasPreset = {
      id: 'free',
      kind: 'free',
      nameKey: 'Free Workflow',
      nodes: [
        {
          id: 'dock-ligands',
          type: 'tool',
          titleKey: 'Dock Ligands',
          position: { x: 120, y: 80 },
          recommendedToolSlug: 'vina-docking',
        },
      ],
      edges: [],
    }

    const preflight = buildWorkflowPreflight({
      template,
      nodeStatuses: { 'dock-ligands': 'idle' },
      readyNodeIds: ['dock-ligands'],
      toolsBySlug: {
        'vina-docking': {
          slug: 'vina-docking',
          name: 'AutoDock Vina',
          contract: makeToolContract(),
        },
      },
    })

    expect(preflight.resourceSummaries).toEqual([
      expect.objectContaining({
        id: 'dock-ligands-vina-docking-resources',
        nodeId: 'dock-ligands',
        nodeTitle: 'Dock Ligands',
        toolSlug: 'vina-docking',
        toolName: 'AutoDock Vina',
        executorType: 'docker_image',
        tier: 'medium',
        cpu: 8,
        memoryGb: 16,
        gpuRequired: false,
        expectedMinutes: 30,
        timeoutMinutes: 180,
        label: 'medium · CPU 8 · MEM 16GB · ETA 30m · Timeout 180m',
      }),
    ])
  })
})
