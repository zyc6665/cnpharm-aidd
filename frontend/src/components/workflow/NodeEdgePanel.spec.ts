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

  it('includes contract-declared custom artifact refs in manual edge type options', () => {
    const wrapper = mount(NodeEdgePanel, {
      props: {
        node: {
          id: 'cryoem-fit',
          type: 'tool',
          titleKey: 'CryoEM Fit',
          position: { x: 320, y: 0 },
          requiredInputTypes: ['cryoem_map@1'],
          inputArtifactSlots: [{ name: 'map', type: 'cryoem_map@1', required: true }]
        },
        template: {
          id: 'flow',
          kind: 'free',
          nameKey: 'Flow',
          nodes: [
            {
              id: 'fetch-map',
              type: 'tool',
              titleKey: 'Fetch Map',
              position: { x: 0, y: 0 },
              producedOutputTypes: ['cryoem_map@1'],
              outputArtifactSlots: [
                { name: 'map', type: 'cryoem_map@1', cardinality: 'one', required: true }
              ]
            },
            {
              id: 'cryoem-fit',
              type: 'tool',
              titleKey: 'CryoEM Fit',
              position: { x: 320, y: 0 },
              requiredInputTypes: ['cryoem_map@1']
            }
          ],
          edges: []
        }
      },
      global: {
        plugins: [i18n],
        stubs: {
          AButton: true,
          AEmpty: true,
          ASelect: {
            props: ['options'],
            template: '<select><option v-for="option in options" :key="option.value">{{ option.label }}</option></select>'
          },
          ATag: { template: '<span><slot /></span>' }
        }
      }
    })

    const artifactTypeSelect = wrapper.findAll('select')[1]
    expect(artifactTypeSelect?.text()).toContain('cryoem_map@1')
  })
})
