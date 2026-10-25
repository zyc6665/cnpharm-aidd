/**
 * 算力卡位展示逻辑（P-36）。
 *
 * 纯函数：不依赖组件、不发请求，便于单测。
 */
import type { GpuSlot, GpuSlotNode, GpuSlotState } from '@/types/gpu'

/** 卡位状态的展示色（对应 a-badge / a-tag 的 status 语义）。 */
export const SLOT_STATE_TONES: Record<GpuSlotState, 'success' | 'processing' | 'warning' | 'error' | 'default'> = {
  FREE: 'success',
  RESERVED: 'warning',
  BUSY: 'processing',
  FAULT: 'error',
  BORROWED: 'default'
}

/** 全部卡位状态，顺序即展示顺序。 */
export const SLOT_STATES: readonly GpuSlotState[] = ['FREE', 'RESERVED', 'BUSY', 'FAULT', 'BORROWED']

function emptyStateCounts(): Record<GpuSlotState, number> {
  return { FREE: 0, RESERVED: 0, BUSY: 0, FAULT: 0, BORROWED: 0 }
}

/** 按状态统计卡位数量；空入参返回五个 0。 */
export function countSlotsByState(slots?: readonly GpuSlot[] | null): Record<GpuSlotState, number> {
  const counts = emptyStateCounts()
  if (!slots || slots.length === 0) {
    return counts
  }

  for (const slot of slots) {
    counts[slot.state] += 1
  }
  return counts
}

/**
 * 卡位标识：优先取后端已声明的 slot_identifier，其次组合 `node_id/slot_id`，
 * 再次退化到单独一侧，最后兜底 '-'。
 */
export function formatSlotIdentifier(slot: Pick<GpuSlot, 'slot_identifier' | 'slot_id' | 'node_id'>): string {
  const identifier = (slot.slot_identifier || '').trim()
  if (identifier) {
    return identifier
  }

  const nodeId = (slot.node_id || '').trim()
  const slotId = (slot.slot_id || '').trim()
  if (nodeId && slotId) {
    return `${nodeId}/${slotId}`
  }
  return slotId || nodeId || '-'
}

/** 卡位容量汇总：总卡位数、可调度卡位数、按厂商分布。 */
export function summarizeSlotCapacity(nodes?: readonly GpuSlotNode[] | null): {
  totalSlots: number
  schedulableSlots: number
  byVendor: Record<string, number>
} {
  const byVendor: Record<string, number> = {}
  let totalSlots = 0
  let schedulableSlots = 0

  for (const node of nodes ?? []) {
    for (const slot of node.slots) {
      totalSlots += 1
      if (slot.schedulable) {
        schedulableSlots += 1
      }
      const vendor = (slot.accelerator_vendor || 'unknown').trim() || 'unknown'
      byVendor[vendor] = (byVendor[vendor] ?? 0) + 1
    }
  }

  return { totalSlots, schedulableSlots, byVendor }
}
