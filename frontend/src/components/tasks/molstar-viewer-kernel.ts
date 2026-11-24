import type { Viewer as MolstarViewer } from 'molstar/lib/apps/viewer/app'
import { Color } from 'molstar/lib/mol-util/color'
import type { MolstarBackground, MolstarViewerMode } from '@/domain/tasks'
import { trackDownload } from '@/utils/download-history'

export type { MolstarBackground, MolstarViewerMode } from '@/domain/tasks'

export const MOLSTAR_BACKGROUND_HEX: Readonly<Record<MolstarBackground, number>> = {
  dark: 0x0b1a2e,
  white: 0xffffff,
}

export interface MolstarViewerKernelOptions {
  allowNativeFullscreen?: boolean
  showControls?: boolean
  backgroundColor?: number
}

/**
 * Shared Mol* lifecycle/configuration boundary for all structure viewers.
 * Rendering presets stay in the host component so molecule/protein/pocket
 * views can retain their domain-specific defaults.
 */
export async function createMolstarViewer(
  host: HTMLElement,
  options: MolstarViewerKernelOptions = {},
): Promise<MolstarViewer> {
  const { Viewer } = await import('molstar/lib/apps/viewer/app')
  const viewer = await Viewer.create(host, {
    layoutIsExpanded: false,
    layoutShowControls: options.showControls ?? false,
    collapseLeftPanel: true,
    collapseRightPanel: true,
    viewportShowControls: false,
    viewportShowExpand: false,
    viewportShowToggleFullscreen: options.allowNativeFullscreen ?? false,
    viewportShowSettings: false,
    viewportShowSelectionMode: false,
    viewportShowAnimation: false,
    viewportShowTrajectoryControls: false,
    viewportShowScreenshotControls: false,
  })

  if (options.backgroundColor !== undefined) {
    try {
      viewer.plugin.canvas3d?.setProps({
        renderer: { backgroundColor: Color(options.backgroundColor) },
      })
    } catch {
      // Background configuration is best-effort and must not block structure loading.
    }
  }

  return viewer
}

export interface RevocableResourceRegistry {
  add(revoke: () => void): void
  clear(): void
}

/** Keeps browser object URLs scoped to one viewer render lifecycle. */
export function createRevocableResourceRegistry(): RevocableResourceRegistry {
  let revokers: Array<() => void> = []
  return {
    add(revoke) { revokers.push(revoke) },
    clear() { revokers.forEach(revoke => revoke()); revokers = [] },
  }
}

export function setMolstarBackgroundColor(
  viewer: MolstarViewer | null,
  background: MolstarBackground,
): void {
  if (!viewer) {
    return
  }
  try {
    viewer.plugin.canvas3d?.setProps({
      renderer: { backgroundColor: Color(MOLSTAR_BACKGROUND_HEX[background]) },
    })
  } catch {
    // Background configuration is best-effort and must not block structure loading.
  }
}

export async function downloadMolstarScreenshot(
  viewer: MolstarViewer | null,
  filename = 'structure-snapshot.png',
): Promise<boolean> {
  if (!viewer) {
    return false
  }
  try {
    const helper = viewer.plugin.helpers.viewportScreenshot
    if (!helper) {
      return false
    }
    await trackDownload(filename, async () => {
      await helper.download(filename)
    })
    return true
  } catch {
    return false
  }
}

export function disposeMolstarViewer(viewer: MolstarViewer | null): void {
  viewer?.dispose()
}
