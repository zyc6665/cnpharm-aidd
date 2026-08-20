import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ResizableWorkbenchSidebar from './ResizableWorkbenchSidebar.vue'

describe('ResizableWorkbenchSidebar', () => {
  it('renders slot content and emits width changes from the resize handle', async () => {
    const wrapper = mount(ResizableWorkbenchSidebar, {
      props: {
        side: 'left',
        width: 320,
        collapsed: false,
        minWidth: 280,
        maxWidth: 480,
      },
      slots: { default: '<div data-testid="sidebar-content">Tools</div>' },
    })

    expect(wrapper.find('[data-testid="sidebar-content"]').text()).toBe('Tools')
    expect(wrapper.attributes('style')).toContain('width: 320px')

    wrapper.find('[data-testid="sidebar-resize-handle"]').element.dispatchEvent(
      new PointerEvent('pointerdown', { clientX: 320, button: 0 })
    )
    await wrapper.vm.$nextTick()
    window.dispatchEvent(new PointerEvent('pointermove', { clientX: 380 }))
    window.dispatchEvent(new PointerEvent('pointerup'))

    const widthEvents = wrapper.emitted('update:width') ?? []
    expect(widthEvents[widthEvents.length - 1]).toEqual([380])
  })

  it('uses collapsed width and emits collapsed toggle', async () => {
    const wrapper = mount(ResizableWorkbenchSidebar, {
      props: {
        side: 'right',
        width: 380,
        collapsed: true,
        minWidth: 320,
        maxWidth: 560,
      },
    })

    expect(wrapper.attributes('style')).toContain('width: 56px')
    await wrapper.find('[data-testid="sidebar-collapse-toggle"]').trigger('click')
    expect(wrapper.emitted('update:collapsed')).toEqual([[false]])
  })
})
