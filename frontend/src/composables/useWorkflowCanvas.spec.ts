import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'
import i18n from '@/locales'
import { useArtifactsStore, useToolsStore, useWorkflowStore } from '@/stores'
import { useWorkflowCanvas } from './useWorkflowCanvas'

function mountCanvasHarness() {
  const exposed = {} as ReturnType<typeof useWorkflowCanvas> & {
    workflowStore: ReturnType<typeof useWorkflowStore>
    toolsStore: ReturnType<typeof useToolsStore>
  }
  const Harness = defineComponent({
    setup() {
      const workflowStore = useWorkflowStore()
      const toolsStore = useToolsStore()
      const artifactsStore = useArtifactsStore()
      Object.assign(exposed, useWorkflowCanvas({ workflowStore, toolsStore, artifactsStore }), {
        workflowStore,
        toolsStore
      })
      return () => null
    }
  })

  mount(Harness, { global: { plugins: [createPinia(), i18n] } })
  return exposed
}

describe('useWorkflowCanvas', () => {
  it('添加工具节点时应从工具契约带入语义输入输出并归一化别名', () => {
    const canvas = mountCanvasHarness()
    canvas.toolsStore.workbenchGroups = [
      {
        id: 'aidd',
        name: 'AIDD',
        slug: 'aidd',
        sort_order: 1,
        tools: [
          {
            id: 'tool-1',
            name: 'Pocket Explorer',
            slug: 'pocket-explorer',
            status: 'published',
            is_recommended: true,
            sort_order: 1,
            contract: {
              contract_version: '1.0',
              slug: 'pocket-explorer',
              name: 'Pocket Explorer',
              status: 'published',
              executor: { type: 'ssh' },
              schema: {
                input: { type: 'object', properties: {} },
                output: { type: 'object', properties: {} }
              },
              capability: {
                enabled: true,
                inputs: [{ semantic_type: 'protein_structure', field: 'protein' }],
                outputs: [{ semantic_type: 'pocket_structure', source: 'output_files' }],
                defaults: {}
              },
              artifacts: {
                inputs: [{ name: 'protein', type: 'protein_structure@1', required: true }],
                outputs: [
                  {
                    name: 'pocket',
                    type: 'binding_pocket@1',
                    cardinality: 'one',
                    required: true
                  }
                ]
              },
              validation: { status: 'valid', errors: [] }
            }
          }
        ]
      }
    ] as never

    canvas.handleAddToolNode('pocket-explorer')

    const nodes = canvas.workflowStore.canvasNodes
    expect(nodes).toHaveLength(1)
    expect(nodes[0]?.requiredInputTypes).toEqual(['protein_structure@1'])
    expect(nodes[0]?.producedOutputTypes).toEqual(['binding_pocket@1'])
    expect(nodes[0]?.inputArtifactSlots).toEqual([
      { name: 'protein', type: 'protein_structure@1', required: true }
    ])
    expect(nodes[0]?.outputArtifactSlots).toEqual([
      { name: 'pocket', type: 'binding_pocket@1', cardinality: 'one', required: true }
    ])

    expect(canvas.buildCurrentWorkflowDefinition().nodes[0]).toMatchObject({
      artifact_input_slots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
      artifact_inputs: {
        protein: 'workflow_input:protein_structure@1'
      },
      artifact_outputs: [
        { name: 'pocket', type: 'binding_pocket@1', cardinality: 'one', required: true }
      ]
    })
  })

  it('新增标准产物类型的模型不需要前端硬编码也能生成工作流节点契约', () => {
    const canvas = mountCanvasHarness()
    canvas.toolsStore.workbenchGroups = [
      {
        id: 'cryoem',
        name: 'CryoEM',
        slug: 'cryoem',
        sort_order: 1,
        tools: [
          {
            id: 'tool-cryo-fit',
            name: 'CryoEM Fit',
            slug: 'cryoem-fit',
            status: 'published',
            is_recommended: true,
            sort_order: 1,
            contract: {
              contract_version: '1.0',
              slug: 'cryoem-fit',
              name: 'CryoEM Fit',
              status: 'published',
              executor: { type: 'remote_api' },
              schema: { input: { type: 'object', properties: {} }, output: { type: 'object', properties: {} } },
              capability: { enabled: true, inputs: [], outputs: [], defaults: {} },
              artifacts: {
                inputs: [{ name: 'map', type: 'cryoem_map@1', required: true }],
                outputs: [
                  { name: 'fit_report', type: 'model_fit_report@1', cardinality: 'one', required: true }
                ]
              },
              validation: { status: 'valid', errors: [] }
            }
          }
        ]
      }
    ] as never

    canvas.handleAddToolNode('cryoem-fit')

    const node = canvas.workflowStore.canvasNodes[0]
    expect(node?.requiredInputTypes).toEqual(['cryoem_map@1'])
    expect(node?.producedOutputTypes).toEqual(['model_fit_report@1'])
    expect(canvas.buildCurrentWorkflowDefinition().nodes[0]).toMatchObject({
      artifact_input_slots: [{ name: 'map', type: 'cryoem_map@1', required: true }],
      artifact_inputs: { map: 'workflow_input:cryoem_map@1' },
      artifact_outputs: [
        { name: 'fit_report', type: 'model_fit_report@1', cardinality: 'one', required: true }
      ]
    })
  })

  it('应将条件、批量和循环节点序列化为后端控制流定义', () => {
    const canvas = mountCanvasHarness()
    canvas.workflowStore.$patch({
      hasCanvasOverride: true,
      canvasNodes: [
        {
          id: 'condition-score-gate',
          type: 'condition',
          titleKey: 'Score gate',
          position: { x: 240, y: 120 },
          expression: { op: '<=', left: 'node:docking:score', right: -8 },
        },
        {
          id: 'map-admet',
          type: 'map',
          titleKey: 'Batch ADMET',
          position: { x: 480, y: 120 },
          over: 'workflow_input:smiles_csv',
          max_parallelism: 4,
        },
        {
          id: 'loop-optimize',
          type: 'loop',
          titleKey: 'Lead optimize loop',
          position: { x: 720, y: 120 },
          max_iterations: 6,
          convergence_condition: { op: '<=', left: 'node:docking:score', right: -9 },
          body: [
            {
              id: 'loop-body-generate',
              type: 'tool',
              titleKey: 'Generate',
              position: { x: 0, y: 0 },
              toolSlugs: ['gcdm-pocket-generation'],
              recommendedToolSlug: 'gcdm-pocket-generation',
            },
          ],
        },
      ],
      canvasEdges: [],
    })

    expect(canvas.buildCurrentWorkflowDefinition().nodes).toEqual([
      expect.objectContaining({
        id: 'condition-score-gate',
        kind: 'condition',
        type: 'condition',
        expression: { op: '<=', left: 'node:docking:score', right: -8 },
      }),
      expect.objectContaining({
        id: 'map-admet',
        kind: 'map',
        type: 'map',
        over: 'workflow_input:smiles_csv',
        max_parallelism: 4,
      }),
      expect.objectContaining({
        id: 'loop-optimize',
        kind: 'loop',
        type: 'loop',
        max_iterations: 6,
        convergence_condition: { op: '<=', left: 'node:docking:score', right: -9 },
        body: [expect.objectContaining({ id: 'loop-body-generate', kind: 'tool' })],
      }),
    ])
  })

  it('应一键插入准备节点并把原始连线重连到准备节点', () => {
    const canvas = mountCanvasHarness()
    canvas.toolsStore.workbenchGroups = [
      {
        id: 'aidd',
        name: 'AIDD',
        slug: 'aidd',
        sort_order: 1,
        tools: [
          {
            id: 'tool-prepare',
            name: 'Protein Preparation',
            slug: 'builtin-protein-preparation',
            status: 'published',
            is_recommended: true,
            sort_order: 1,
            contract: {
              contract_version: '1.0',
              slug: 'builtin-protein-preparation',
              name: 'Protein Preparation',
              status: 'published',
              executor: { type: 'builtin' },
              schema: { input: { type: 'object', properties: {} }, output: { type: 'object', properties: {} } },
              capability: { enabled: true, inputs: [], outputs: [], defaults: {} },
              artifacts: {
                inputs: [{ name: 'protein', type: 'protein_structure@1', required: true }],
                outputs: [{ name: 'prepared_protein', type: 'protein_structure@1', cardinality: 'one', required: true }],
              },
              validation: { status: 'valid', errors: [] },
            },
          },
        ],
      },
    ] as never
    canvas.workflowStore.$patch({
      hasCanvasOverride: true,
      canvasNodes: [
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
              suggestedPreparationTool: 'builtin-protein-preparation',
            },
          ],
        },
      ],
      canvasEdges: [
        { id: 'edge-fetch-dock', source: 'fetch-pdb', target: 'dock', artifactType: 'protein_structure@1' },
      ],
    })

    expect(canvas.workflowRepairableCount.value).toBe(1)

    canvas.handleApplyWorkflowAutoRepair()

    const repairNode = canvas.workflowStore.canvasNodes.find(
      node => node.recommendedToolSlug === 'builtin-protein-preparation'
    )
    expect(repairNode).toBeDefined()
    expect(canvas.workflowStore.canvasEdges).not.toContainEqual(expect.objectContaining({ id: 'edge-fetch-dock' }))
    expect(canvas.workflowStore.canvasEdges).toContainEqual(expect.objectContaining({
      source: 'fetch-pdb',
      target: repairNode?.id,
      artifactType: 'protein_structure@1',
    }))
    expect(canvas.workflowStore.canvasEdges).toContainEqual(expect.objectContaining({
      source: repairNode?.id,
      target: 'dock',
      artifactType: 'protein_structure@1',
    }))
    expect(canvas.buildCurrentWorkflowDefinition().nodes.find(node => node.id === 'dock')).toMatchObject({
      artifact_inputs: {
        receptor: `node:${repairNode?.id}:prepared_protein`,
      },
    })
  })
})
