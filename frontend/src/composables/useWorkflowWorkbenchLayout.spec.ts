import { describe, expect, it } from 'vitest'
import { useWorkflowWorkbenchLayout } from './useWorkflowWorkbenchLayout'

describe('useWorkflowWorkbenchLayout', () => {
  it('clamps sidebar widths and toggles collapsed state', () => {
    const layout = useWorkflowWorkbenchLayout({
      left: { defaultWidth: 320, minWidth: 280, maxWidth: 480 },
      right: { defaultWidth: 380, minWidth: 320, maxWidth: 560 },
    })

    layout.setLeftWidth(900)
    layout.setRightWidth(120)

    expect(layout.leftWidth.value).toBe(480)
    expect(layout.rightWidth.value).toBe(320)

    layout.toggleLeftCollapsed()
    layout.toggleRightCollapsed()

    expect(layout.leftCollapsed.value).toBe(true)
    expect(layout.rightCollapsed.value).toBe(true)
  })
})
