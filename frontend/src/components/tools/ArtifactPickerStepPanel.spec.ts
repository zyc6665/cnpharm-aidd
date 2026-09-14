import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ArtifactPickerStepPanel from './ArtifactPickerStepPanel.vue'

describe('ArtifactPickerStepPanel', () => {
  const stubs = {
    ATag: {
      template: '<span class="tag-stub"><slot /></span>',
    },
    ArtifactPickerStepOption: {
      props: ['title', 'meta', 'rightText', 'rightColor', 'selected', 'focused'],
      emits: ['select'],
      template: `
        <button
          type="button"
          class="option-stub"
          :class="{ selected, focused }"
          :data-right-color="rightColor"
          @click="$emit('select')"
        >
          {{ title }} {{ meta }} {{ rightText }}
        </button>
      `,
    },
  }

  it('renders step copy and emits selected option id', async () => {
    const wrapper = mount(ArtifactPickerStepPanel, {
      props: {
        label: 'Output',
        title: 'Select output',
        count: 2,
        options: [
          {
            id: 'artifact-1',
            title: 'first.pdb',
            meta: 'Docking Tool',
            rightText: undefined,
          },
          {
            id: 'artifact-2',
            title: 'second.pdb',
            meta: 'Scoring Tool',
            rightText: 'Selected',
            rightColor: 'blue',
            selected: true,
          },
        ],
      },
      global: { stubs },
    })

    expect(wrapper.text()).toContain('Output')
    expect(wrapper.text()).toContain('Select output')
    expect(wrapper.find('.tag-stub').text()).toBe('2')
    expect(wrapper.findAll('.option-stub')).toHaveLength(2)
    expect(wrapper.text()).toContain('second.pdb')
    expect(wrapper.find('.selected').exists()).toBe(true)

    await wrapper.findAll('.option-stub')[1]!.trigger('click')

    expect(wrapper.emitted('select')).toEqual([['artifact-2']])
  })
})
