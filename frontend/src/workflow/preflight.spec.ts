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

  it('将工作流节点的 Artifact Binding 决策转换为预检处理提示', () => {
    const template: WorkflowCanvasPreset = {
      id: 'free',
      kind: 'free',
      nameKey: 'Free Workflow',
      nodes: [
        {
          id: 'predict-pocket',
          type: 'tool',
          titleKey: 'Predict Pocket',
          position: { x: 120, y: 80 },
          recommendedToolSlug: 'lvpocket-pocket-prediction',
        },
      ],
      edges: [],
    }

    const preflight = buildWorkflowPreflight({
      template,
      nodeStatuses: { 'predict-pocket': 'idle' },
      readyNodeIds: [],
      workflowRunNodeStates: {
        'predict-pocket': {
          status: 'blocked',
          blocked_reason: '需要先运行蛋白准备工具生成 prepared_pdb。',
          binding_decisions: {
            protein: {
              status: 'needs_preparation',
              input_name: 'protein',
              standard_type: 'protein_structure@1',
              reason: '当前蛋白缺少 prepared_pdb。',
              suggested_tool_slug: 'builtin-protein-preparation',
            },
          },
        },
      },
    })

    expect(preflight.canRun).toBe(false)
    expect(preflight.primaryMessage).toBe('存在标准产物需要准备或转换')
    expect(preflight.issues).toEqual([
      expect.objectContaining({
        id: 'predict-pocket-needs_preparation-protein',
        type: 'needs_preparation',
        severity: 'warning',
        nodeTitle: 'Predict Pocket',
        title: '需要先准备输入产物',
        detail: '当前蛋白缺少 prepared_pdb。建议运行 builtin-protein-preparation。',
      }),
    ])
  })

  it('等待上游产物时应提示用户先运行上游而不是手动绑定文件', () => {
    const template: WorkflowCanvasPreset = {
      id: 'free',
      kind: 'free',
      nameKey: 'Free Workflow',
      nodes: [
        {
          id: 'fetch-pdb',
          type: 'tool',
          titleKey: 'Fetch PDB',
          position: { x: 0, y: 0 },
          producedOutputTypes: ['protein_structure@1'],
        },
        {
          id: 'predict-pocket',
          type: 'tool',
          titleKey: 'Predict Pocket',
          position: { x: 320, y: 0 },
          requiredInputTypes: ['protein_structure@1'],
        },
      ],
      edges: [
        {
          id: 'edge-fetch-pdb-to-pocket',
          source: 'fetch-pdb',
          target: 'predict-pocket',
          artifactType: 'protein_structure@1',
        },
      ],
    }

    const preflight = buildWorkflowPreflight({
      template,
      nodeStatuses: { 'fetch-pdb': 'idle', 'predict-pocket': 'idle' },
      readyNodeIds: ['fetch-pdb'],
      taskByNode: {},
    })

    expect(preflight.issues).toContainEqual(expect.objectContaining({
      type: 'waiting_upstream',
      title: '等待上游产物',
      detail: '先运行 Fetch PDB，成功后 protein_structure@1 会自动绑定到当前节点。',
    }))
  })
})
