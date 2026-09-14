import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ArtifactPickerStepOption from './ArtifactPickerStepOption.vue'

describe('ArtifactPickerStepOption', () => {
  const stubs = {
    ATag: { props: ['color'], template: '<span class="tag-stub" :data-color="color"><slot /></span>' },
  }

  it('renders option copy, state, right text, and select event', async () => {
    const wrapper = mount(ArtifactPickerStepOption, {
      props: {
        title: 'Docking Tool',
        meta: 'Generated tool outputs',
        rightText: 3,
        rightColor: 'blue',
        selected: true,
        focused: false,
      },
      global: { stubs },
    })

    expect(wrapper.text()).toContain('Docking Tool')
    expect(wrapper.text()).toContain('Generated tool outputs')
    expect(wrapper.text()).toContain('3')
    expect(wrapper.classes()).toContain('is-selected')
    expect(wrapper.find('.tag-stub').attributes('data-color')).toBe('blue')

    await wrapper.trigger('click')

    expect(wrapper.emitted('select')).toEqual([[]])
  })

  it('omits right text when none is provided', () => {
    const wrapper = mount(ArtifactPickerStepOption, {
      props: {
        title: 'result.sdf',
        meta: 'Docking Tool · 2026-08-05 06:00',
        focused: true,
      },
      global: { stubs },
    })

    expect(wrapper.classes()).toContain('is-focused')
    expect(wrapper.find('.tag-stub').exists()).toBe(false)
  })
})
