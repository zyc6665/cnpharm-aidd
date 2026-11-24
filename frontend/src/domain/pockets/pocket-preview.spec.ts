import { describe, expect, it } from 'vitest'
import { buildPocketBoxVoxelGrid } from './pocket-preview'

describe('口袋包围盒体素预览', () => {
  it('用中心与包围盒生成闭合的体素盒子', () => {
    const grid = buildPocketBoxVoxelGrid(
      { x: 10, y: 20, z: 30 },
      { x: 20, y: 20, z: 20 }
    )
    expect(grid?.boxes.length).toBeGreaterThan(0)
    expect(grid?.color).toBe(0x22d3ee)
    for (const box of grid?.boxes ?? []) {
      expect(box.center[0]).toBeGreaterThanOrEqual(0)
      expect(box.center[0]).toBeLessThanOrEqual(20)
      expect(box.center[1]).toBeGreaterThanOrEqual(10)
      expect(box.center[1]).toBeLessThanOrEqual(30)
      expect(box.center[2]).toBeGreaterThanOrEqual(20)
      expect(box.center[2]).toBeLessThanOrEqual(40)
    }
  })

  it('缺少中心或包围盒时返回 null，供页面走空态', () => {
    expect(buildPocketBoxVoxelGrid(null, { x: 20, y: 20, z: 20 })).toBeNull()
    expect(buildPocketBoxVoxelGrid({ x: 0, y: 0, z: 0 }, null)).toBeNull()
    expect(buildPocketBoxVoxelGrid({ x: 0, y: 0, z: 0 }, { x: 0, y: 20, z: 20 })).toBeNull()
  })
})
