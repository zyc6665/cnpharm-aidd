import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import i18n from '@/locales'
import WorkflowRunInputPanel from './WorkflowRunInputPanel.vue'

function mountPanel() {
  return mount(WorkflowRunInputPanel, {
    props: {
      requirements: ['protein_structure@1'],
      artifactRequirements: [
        {
          key: 'protein_structure@1',
          semanticType: 'protein_structure@1',
          slotName: 'protein',
          label: 'protein: protein_structure@1'
        }
      ],
      selections: {},
      optionsBySemanticType: {
        'protein_structure@1': [{ value: 'artifact-1', label: 'protein.pdb · Upload' }]
      }
    },
    global: {
      plugins: [i18n],
      stubs: {
        AButton: {
          emits: ['click'],
          template: '<button @click="$emit(\'click\')"><slot /></button>'
        },
        ASelect: {
          props: ['options'],
          emits: ['change'],
          template: `
            <div>
              <button
                v-for="option in options"
                :key="option.value"
                class="select-option"
                type="button"
                @click="$emit('change', option.value)"
              >
                {{ option.label }}
              </button>
            </div>
          `
        }
      }
    }
  })
}

describe('WorkflowRunInputPanel', () => {
  it('shows standard artifact slot names while selecting by compatible type', async () => {
    const wrapper = mountPanel()

    expect(wrapper.text()).toContain('protein: protein_structure@1')
    expect(wrapper.text()).toContain('protein.pdb · Upload')

    await wrapper.find('.select-option').trigger('click')

    expect(wrapper.emitted('select')?.[0]).toEqual(['protein_structure@1', 'artifact-1'])
  })
})
