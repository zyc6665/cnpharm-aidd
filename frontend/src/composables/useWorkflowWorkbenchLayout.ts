import { ref } from 'vue'

interface SidebarConfig {
  defaultWidth: number
  minWidth: number
  maxWidth: number
}

interface WorkbenchLayoutOptions {
  left: SidebarConfig
  right: SidebarConfig
}

function clampWidth(value: number, config: SidebarConfig) {
  return Math.min(config.maxWidth, Math.max(config.minWidth, Math.round(value)))
}

export function useWorkflowWorkbenchLayout(options: WorkbenchLayoutOptions) {
  const leftWidth = ref(options.left.defaultWidth)
  const rightWidth = ref(options.right.defaultWidth)
  const leftCollapsed = ref(false)
  const rightCollapsed = ref(false)

  function setLeftWidth(value: number) {
    leftWidth.value = clampWidth(value, options.left)
  }

  function setRightWidth(value: number) {
    rightWidth.value = clampWidth(value, options.right)
  }

  function toggleLeftCollapsed() {
    leftCollapsed.value = !leftCollapsed.value
  }

  function toggleRightCollapsed() {
    rightCollapsed.value = !rightCollapsed.value
  }

  return {
    leftWidth,
    rightWidth,
    leftCollapsed,
    rightCollapsed,
    setLeftWidth,
    setRightWidth,
    toggleLeftCollapsed,
    toggleRightCollapsed,
  }
}
