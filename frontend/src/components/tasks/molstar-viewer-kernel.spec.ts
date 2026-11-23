import { describe, expect, it, vi } from 'vitest'
import { createRevocableResourceRegistry } from './molstar-viewer-kernel'

describe('createRevocableResourceRegistry', () => {
  it('revokes registered resources when cleared', () => {
    const revoke = vi.fn()
    const registry = createRevocableResourceRegistry()

    registry.add(revoke)
    registry.clear()

    expect(revoke).toHaveBeenCalledTimes(1)
  })

  it('does not revoke the same resources again after clearing', () => {
    const revoke = vi.fn()
    const registry = createRevocableResourceRegistry()

    registry.add(revoke)
    registry.clear()
    registry.clear()

    expect(revoke).toHaveBeenCalledTimes(1)
  })
})
