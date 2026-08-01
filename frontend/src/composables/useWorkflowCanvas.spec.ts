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
        toolsStore,
      })
      return () => null
    },
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
              executor: { type: 'ssh' },
              capability: {
                enabled: true,
                inputs: [{ semantic_type: 'protein_structure', field: 'protein' }],
                outputs: [{ semantic_type: 'pocket_structure', source: 'output_files' }],
                defaults: {},
              },
              validation: { status: 'valid', errors: [] },
            },
          },
        ],
      },
    ] as never

    canvas.handleAddToolNode('pocket-explorer')

    const nodes = canvas.workflowStore.canvasNodes
    expect(nodes).toHaveLength(1)
    expect(nodes[0]?.requiredInputTypes).toEqual(['protein_structure@1'])
    expect(nodes[0]?.producedOutputTypes).toEqual(['binding_pocket@1'])
  })
})
