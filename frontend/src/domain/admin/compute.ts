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
  BORROWED: 'default',
  // 未知状态用中性灰：既不能显示为空闲（绿），也不能显示成故障（红）误导判断。
  UNKNOWN: 'default'
}

/** 全部卡位状态，顺序即展示顺序。 */
export const SLOT_STATES: readonly GpuSlotState[] = [
  'FREE',
  'RESERVED',
  'BUSY',
  'FAULT',
  'BORROWED',
  'UNKNOWN'
]

/** 后端声明过的卡位状态（UNKNOWN 仅是前端兜底，不属于后端契约）。 */
export const DECLARED_SLOT_STATES: readonly GpuSlotState[] = [
  'FREE',
  'RESERVED',
  'BUSY',
  'FAULT',
  'BORROWED'
]

/** 判断状态字符串是否属于后端已声明状态。 */
export function isDeclaredSlotState(value: string): value is GpuSlotState {
  return (DECLARED_SLOT_STATES as readonly string[]).includes(value)
}

/**
 * 后端状态字符串 → 展示状态。
 *
 * 未知值一律落到 `UNKNOWN`，**绝不**降级成 `FREE`：
 * 把不确定显示成「空闲」会让算力页误导调度决策。
 */
export function normalizeSlotState(value: unknown): GpuSlotState {
  const raw = typeof value === 'string' ? value.trim() : ''
  return isDeclaredSlotState(raw) ? raw : 'UNKNOWN'
}

function emptyStateCounts(): Record<GpuSlotState, number> {
  return { FREE: 0, RESERVED: 0, BUSY: 0, FAULT: 0, BORROWED: 0, UNKNOWN: 0 }
}

/** 按状态统计卡位数量；空入参返回六个 0（含 UNKNOWN 兜底桶）。 */
export function countSlotsByState(slots?: readonly GpuSlot[] | null): Record<GpuSlotState, number> {
  const counts = emptyStateCounts()
  if (!slots || slots.length === 0) {
    return counts
  }

  for (const slot of slots) {
    const state = slot.state
    // 运行时兜底：即便调用方绕过类型塞进未知状态，也归到 UNKNOWN 桶，
    // 而不是新增一个键（那会让页面统计出现未声明的状态列）或算出 NaN。
    const bucket: GpuSlotState = state in counts ? state : 'UNKNOWN'
    counts[bucket] += 1
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
