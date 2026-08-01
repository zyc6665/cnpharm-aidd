import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import i18n from '@/locales'
import NodeEdgePanel from './NodeEdgePanel.vue'

describe('NodeEdgePanel', () => {
  it('shows standard artifact input and output slots before legacy semantic rows', () => {
    const wrapper = mount(NodeEdgePanel, {
      props: {
        node: {
          id: 'pocket_prediction',
          type: 'tool',
          titleKey: 'LVpocket',
          position: { x: 0, y: 0 },
          inputArtifactSlots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
          outputArtifactSlots: [
            { name: 'pocket', type: 'binding_pocket@1', cardinality: 'one', required: true }
          ]
        },
        template: { id: 'flow', kind: 'free', nameKey: 'Flow', nodes: [], edges: [] }
      },
      global: {
        plugins: [i18n],
        stubs: {
          AButton: true,
          AEmpty: true,
          ASelect: true,
          ATag: { template: '<span><slot /></span>' }
        }
      }
    })

    expect(wrapper.text()).toContain('protein: protein_structure@1')
    expect(wrapper.text()).toContain('pocket: binding_pocket@1')
  })
})
