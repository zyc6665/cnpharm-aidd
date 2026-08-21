import { describe, expect, it } from 'vitest'
import type { WorkflowCanvasPreset } from './canvas-types'
import { buildWorkflowAutoRepairPlan } from './auto-repair'

const proteinPreparationTool = {
  slug: 'builtin-protein-preparation',
  name: 'Protein Preparation',
  inputSemanticTypes: ['protein_structure@1'],
  outputSemanticTypes: ['protein_structure@1'],
  inputArtifactSlots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
  outputArtifactSlots: [
    { name: 'prepared_protein', type: 'protein_structure@1', cardinality: 'one' as const, required: true },
  ],
}

const ligandConformerTool = {
  slug: 'builtin-rdkit-conformer',
  name: 'RDKit Conformer',
  inputSemanticTypes: ['ligand_structure@1'],
  outputSemanticTypes: ['ligand_structure@1'],
  inputArtifactSlots: [{ name: 'ligand', type: 'ligand_structure@1', required: true }],
  outputArtifactSlots: [
    { name: 'ligand_3d', type: 'ligand_structure@1', cardinality: 'one' as const, required: true },
  ],
}

const remoteProteinPreparationTool = {
  slug: 'remote-protein-prep-api',
  name: 'Remote Protein Preparation API',
  inputSemanticTypes: ['protein_structure@1'],
  outputSemanticTypes: ['protein_structure@1'],
  inputArtifactSlots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
  outputArtifactSlots: [
    {
      name: 'receptor',
      type: 'protein_structure@1',
      cardinality: 'one' as const,
      required: true,
      providedRoles: ['prepared_pdb', 'receptor_pdbqt'],
    },
  ],
}

describe('buildWorkflowAutoRepairPlan', () => {
  it('为需要 receptor_pdbqt 的蛋白输入规划蛋白准备节点并重连原始边', () => {
    const template: WorkflowCanvasPreset = {
      id: 'free',
      kind: 'free',
      nameKey: 'Free',
      nodes: [
        {
          id: 'fetch-pdb',
          type: 'tool',
          titleKey: 'Fetch PDB',
          position: { x: 0, y: 0 },
          producedOutputTypes: ['protein_structure@1'],
          outputArtifactSlots: [
            { name: 'protein', type: 'protein_structure@1', cardinality: 'one', required: true },
          ],
        },
        {
          id: 'dock',
          type: 'tool',
          titleKey: 'Dock',
          position: { x: 420, y: 0 },
          requiredInputTypes: ['protein_structure@1'],
          inputArtifactSlots: [
            {
              name: 'receptor',
              type: 'protein_structure@1',
              required: true,
              readinessPolicy: 'require_receptor',
              suggestedPreparationTool: 'builtin-protein-preparation',
            },
          ],
        },
      ],
      edges: [
        {
          id: 'edge-fetch-dock',
          source: 'fetch-pdb',
          target: 'dock',
          artifactType: 'protein_structure@1',
        },
      ],
    }

    const plan = buildWorkflowAutoRepairPlan({ template, tools: [proteinPreparationTool] })

    expect(plan.actions).toEqual([
      expect.objectContaining({
        sourceEdgeId: 'edge-fetch-dock',
        sourceNodeId: 'fetch-pdb',
        targetNodeId: 'dock',
        inputSlotName: 'receptor',
        toolSlug: 'builtin-protein-preparation',
        artifactType: 'protein_structure@1',
      }),
    ])
  })

  it('已有准备节点连接到目标时不重复规划修复节点', () => {
    const template: WorkflowCanvasPreset = {
      id: 'free',
      kind: 'free',
      nameKey: 'Free',
      nodes: [
        {
          id: 'fetch-pdb',
          type: 'tool',
          titleKey: 'Fetch PDB',
          position: { x: 0, y: 0 },
          producedOutputTypes: ['protein_structure@1'],
        },
        {
          id: 'prepare-protein',
          type: 'tool',
          titleKey: 'Protein Preparation',
          position: { x: 220, y: 0 },
          recommendedToolSlug: 'builtin-protein-preparation',
          producedOutputTypes: ['protein_structure@1'],
        },
        {
          id: 'dock',
          type: 'tool',
          titleKey: 'Dock',
          position: { x: 440, y: 0 },
          requiredInputTypes: ['protein_structure@1'],
          inputArtifactSlots: [
            { name: 'receptor', type: 'protein_structure@1', required: true, readinessPolicy: 'require_receptor' },
          ],
        },
      ],
      edges: [
        { id: 'edge-fetch-prepare', source: 'fetch-pdb', target: 'prepare-protein', artifactType: 'protein_structure@1' },
        { id: 'edge-prepare-dock', source: 'prepare-protein', target: 'dock', artifactType: 'protein_structure@1' },
      ],
    }

    const plan = buildWorkflowAutoRepairPlan({ template, tools: [proteinPreparationTool] })

    expect(plan.actions).toEqual([])
  })

  it('为需要 3D 配体的输入规划 RDKit 构象生成节点', () => {
    const template: WorkflowCanvasPreset = {
      id: 'free',
      kind: 'free',
      nameKey: 'Free',
      nodes: [
        {
          id: 'fetch-ligand',
          type: 'tool',
          titleKey: 'Fetch Ligand',
          position: { x: 0, y: 120 },
          producedOutputTypes: ['ligand_structure@1'],
        },
        {
          id: 'dock',
          type: 'tool',
          titleKey: 'Dock',
          position: { x: 420, y: 120 },
          requiredInputTypes: ['ligand_structure@1'],
          inputArtifactSlots: [
            { name: 'ligand', type: 'ligand_structure@1', required: true, readinessPolicy: 'prefer_3d_ligand' },
          ],
        },
      ],
      edges: [
        { id: 'edge-ligand-dock', source: 'fetch-ligand', target: 'dock', artifactType: 'ligand_structure@1' },
      ],
    }

    const plan = buildWorkflowAutoRepairPlan({ template, tools: [ligandConformerTool] })

    expect(plan.actions).toEqual([
      expect.objectContaining({
        sourceEdgeId: 'edge-ligand-dock',
        sourceNodeId: 'fetch-ligand',
        targetNodeId: 'dock',
        toolSlug: 'builtin-rdkit-conformer',
        artifactType: 'ligand_structure@1',
      }),
    ])
  })

  it('目标节点缺少上游产物连线时不规划空准备节点', () => {
    const template: WorkflowCanvasPreset = {
      id: 'free',
      kind: 'free',
      nameKey: 'Free',
      nodes: [
        {
          id: 'dock',
          type: 'tool',
          titleKey: 'Dock',
          position: { x: 420, y: 0 },
          requiredInputTypes: ['protein_structure@1'],
          inputArtifactSlots: [
            { name: 'receptor', type: 'protein_structure@1', required: true, readinessPolicy: 'require_receptor' },
          ],
        },
      ],
      edges: [],
    }

    const plan = buildWorkflowAutoRepairPlan({ template, tools: [proteinPreparationTool] })

    expect(plan.actions).toEqual([])
  })

  it('优先选择声明可提供 required roles 的非内置准备工具', () => {
    const template: WorkflowCanvasPreset = {
      id: 'free',
      kind: 'free',
      nameKey: 'Free',
      nodes: [
        {
          id: 'fetch-pdb',
          type: 'tool',
          titleKey: 'Fetch PDB',
          position: { x: 0, y: 0 },
          producedOutputTypes: ['protein_structure@1'],
        },
        {
          id: 'dock',
          type: 'tool',
          titleKey: 'Dock',
          position: { x: 420, y: 0 },
          requiredInputTypes: ['protein_structure@1'],
          inputArtifactSlots: [
            {
              name: 'receptor',
              type: 'protein_structure@1',
              required: true,
              readinessPolicy: 'require_receptor',
              requiredRoles: ['receptor_pdbqt'],
            },
          ],
        },
      ],
      edges: [
        { id: 'edge-fetch-dock', source: 'fetch-pdb', target: 'dock', artifactType: 'protein_structure@1' },
      ],
    }

    const plan = buildWorkflowAutoRepairPlan({ template, tools: [remoteProteinPreparationTool] })

    expect(plan.actions).toEqual([
      expect.objectContaining({
        sourceEdgeId: 'edge-fetch-dock',
        sourceNodeId: 'fetch-pdb',
        targetNodeId: 'dock',
        inputSlotName: 'receptor',
        toolSlug: 'remote-protein-prep-api',
        artifactType: 'protein_structure@1',
      }),
    ])
  })
})
