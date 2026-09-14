import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ArtifactPickerPath from './ArtifactPickerPath.vue'
import type { ArtifactPickerPathSegment } from '@/domain/tools'

const segments: ArtifactPickerPathSegment[] = [
  { step: 'group', label: 'Group', value: 'Project A', clickable: true, complete: true },
  { step: 'tool', label: 'Tool', value: 'Pocket Tool', clickable: true, complete: true },
  { step: 'task', label: 'Task', value: 'Select task', clickable: false, complete: false },
  { step: 'artifact', label: 'Output', value: 'Select output', clickable: false, complete: false },
]

describe('ArtifactPickerPath', () => {
  it('renders path segment states and emits selected steps', async () => {
    const wrapper = mount(ArtifactPickerPath, {
      props: { segments, activeStep: 'tool' },
    })

    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(4)
    expect(buttons[0]!.classes()).toContain('is-complete')
    expect(buttons[1]!.classes()).toContain('is-active')
    expect(buttons[2]!.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Project A')
    expect(wrapper.text()).toContain('Select output')

    await buttons[0]!.trigger('click')

    expect(wrapper.emitted('select')).toEqual([['group']])
  })
})
