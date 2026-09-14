import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ArtifactPickerSelectionSummary from './ArtifactPickerSelectionSummary.vue'
import i18n from '@/locales'

describe('ArtifactPickerSelectionSummary', () => {
  const stubs = {
    AButton: {
      emits: ['click'],
      template: '<button type="button" @click="$emit(\'click\')"><slot /></button>',
    },
  }

  it('renders summary copy and emits clear when selectable', async () => {
    const wrapper = mount(ArtifactPickerSelectionSummary, {
      props: {
        label: 'Selected',
        title: 'result.sdf',
        meta: 'Docking Tool · 2026-08-05 06:00',
        showClear: true,
      },
      global: { plugins: [i18n], stubs },
    })

    expect(wrapper.text()).toContain('Selected')
    expect(wrapper.text()).toContain('result.sdf')
    expect(wrapper.text()).toContain('Docking Tool')

    await wrapper.find('button').trigger('click')

    expect(wrapper.emitted('clear')).toEqual([[]])
  })

  it('omits clear action when nothing is selected', () => {
    const wrapper = mount(ArtifactPickerSelectionSummary, {
      props: {
        label: 'Pending',
        title: 'Select output',
        meta: 'No artifact selected',
        showClear: false,
      },
      global: { plugins: [i18n], stubs },
    })

    expect(wrapper.find('button').exists()).toBe(false)
  })
})
