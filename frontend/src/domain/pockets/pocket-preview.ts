import type { AxisVector } from '@/types/targets'
import type { PocketVoxelGrid } from '@/domain/tasks/pocket-voxel'

const MAX_EDGE_STEPS = 6
const MAX_AXIS_LENGTH = 120

function finitePositive(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null
}

function finite(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/**
 * 用口袋包围盒画一个体素线框，供提交页的「口袋三维预览」使用。
 *
 * 这里不解析真实口袋点云（那要走口袋文件下载），只用 `center` + `box_size`
 * 把盒子的 12 条棱按 2~4 Å 间距采样成小方块：视觉上能看出口袋位置、范围和
 * 相对受体的大小，成本却只有几十个 box，不会让预览卡住。
 */
export function buildPocketBoxVoxelGrid(
  center: AxisVector | null | undefined,
  boxSize: AxisVector | null | undefined
): PocketVoxelGrid | null {
  const cx = finite(center?.x)
  const cy = finite(center?.y)
  const cz = finite(center?.z)
  const sx = finitePositive(boxSize?.x)
  const sy = finitePositive(boxSize?.y)
  const sz = finitePositive(boxSize?.z)

  if (cx === null || cy === null || cz === null || sx === null || sy === null || sz === null) {
    return null
  }

  const hx = Math.min(sx, MAX_AXIS_LENGTH) / 2
  const hy = Math.min(sy, MAX_AXIS_LENGTH) / 2
  const hz = Math.min(sz, MAX_AXIS_LENGTH) / 2

  const seen = new Set<string>()
  const boxes: Array<{ center: [number, number, number]; halfSize: number }> = []
  const halfSize = 0.55

  const addPoint = (x: number, y: number, z: number): void => {
    const key = `${x.toFixed(2)}|${y.toFixed(2)}|${z.toFixed(2)}`
    if (seen.has(key)) return
    seen.add(key)
    boxes.push({ center: [x, y, z], halfSize })
  }

  const sampleAxis = (length: number): number[] => {
    const steps = Math.min(MAX_EDGE_STEPS, Math.max(1, Math.round(length / 4)))
    return Array.from({ length: steps + 1 }, (_, index) => (index / steps) * 2 - 1)
  }

  const xs = sampleAxis(hx * 2)
  const ys = sampleAxis(hy * 2)
  const zs = sampleAxis(hz * 2)

  for (const x of xs) {
    for (const y of ys) {
      addPoint(cx + x * hx, cy + y * hy, cz - hz)
      addPoint(cx + x * hx, cy + y * hy, cz + hz)
    }
  }
  for (const x of xs) {
    for (const z of zs) {
      addPoint(cx + x * hx, cy - hy, cz + z * hz)
      addPoint(cx + x * hx, cy + hy, cz + z * hz)
    }
  }
  for (const y of ys) {
    for (const z of zs) {
      addPoint(cx - hx, cy + y * hy, cz + z * hz)
      addPoint(cx + hx, cy + y * hy, cz + z * hz)
    }
  }

  return { boxes, color: 0x22d3ee, radius: 0.04 }
}
