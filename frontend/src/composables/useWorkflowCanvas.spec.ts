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
})
