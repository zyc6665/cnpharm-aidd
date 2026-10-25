/**
 * 算力卡位与分配相关接口（P-36）。
 *
 * 全部为只读查询：卡位声明随部署版本化（DRP_NODE_SLOTS_YAML /
 * DRP_NODE_SLOTS_FILE），后端不提供写接口，前端亦不提供任何写操作。
 */
import { get } from '@/api/request'
import type { ApiResponse } from '@/types/api'
import { normalizeSlotState } from '@/domain/admin/compute'
import type { GpuAllocation, GpuSlot, GpuSlotNode, GpuSlotOverview } from '@/types/gpu'

/** 只读查询统一配置：不弹全局错误提示，失败重试一次。 */
const READ_OPTIONS = { silent: true, retry: 1 } as const

/**
 * 后端 `NodeSlot.to_dict()` 使用 camelCase 字段，与对外的 `GpuSlot`
 * （计划中约定的 snake_case 契约）不同名，因此在 api 层做一次规范化。
 */
interface RawSlot {
  nodeId?: string
  slotId?: string
  identifier?: string
  deviceIds?: string[]
  acceleratorModel?: string
  vendor?: string
  image?: string
  models?: string[]
  state?: string
  schedulable?: boolean
  stateMessage?: string
  deviceCount?: number
}

interface RawNode {
  nodeId?: string
  id?: string
  hostname?: string
  acceleratorCount?: number
  gpuCount?: number
  agentEndpoint?: string
  slots?: RawSlot[]
}

interface RawSlotOverview {
  schemaVersion?: string
  configured?: boolean
  nodeCount?: number
  slotCount?: number
  schedulableSlotCount?: number
  nodes?: RawNode[]
}

/** 活跃分配摘要的真实字段（见 `allocator._get_active_allocation_summaries()`）。 */
interface RawAllocation {
  allocation_id?: string
  id?: string
  task_id?: string
  execution_attempt_id?: string | null
  gpu_node_id?: string
  gpu_index?: number | null
  slot_id?: string | null
  accelerator_model?: string | null
  accelerator_vendor?: string | null
  memory_allocated_mb?: number | null
  status?: string
  allocated_at?: string | null
}

interface RawAllocationStats {
  allocations?: RawAllocation[]
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asNullableString(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null
}

function asNullableNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/**
 * 卡位状态归一化统一走 `domain/admin/compute.ts::normalizeSlotState`，
 * 未知值落到 `UNKNOWN` 并保留原文（见 `GpuSlot.raw_state`）。
 */
function normalizeSlot(raw: RawSlot): GpuSlot {
  const deviceIds = Array.isArray(raw.deviceIds) ? raw.deviceIds.map(item => String(item)) : []
  const models = Array.isArray(raw.models) ? raw.models.map(item => String(item)) : []

  return {
    node_id: asString(raw.nodeId),
    slot_id: asString(raw.slotId) || asString(raw.identifier),
    slot_identifier: asString(raw.identifier) || asString(raw.slotId),
    device_ids: deviceIds,
    accelerator_model: asString(raw.acceleratorModel),
    accelerator_vendor: asString(raw.vendor),
    image: asString(raw.image),
    models,
    state: normalizeSlotState(raw.state),
    raw_state: asString(raw.state).trim() || 'UNKNOWN',
    schedulable: raw.schedulable === true,
    state_message: asString(raw.stateMessage),
    device_count: typeof raw.deviceCount === 'number' ? raw.deviceCount : deviceIds.length
  }
}

function normalizeNode(raw: RawNode): GpuSlotNode {
  const slots = Array.isArray(raw.slots) ? raw.slots.map(normalizeSlot) : []

  return {
    id: asString(raw.nodeId) || asString(raw.id),
    hostname: asString(raw.hostname),
    gpu_count: typeof raw.acceleratorCount === 'number' ? raw.acceleratorCount : slots.length,
    agent_endpoint: asString(raw.agentEndpoint),
    slots
  }
}

function normalizeSlotOverview(raw: RawSlotOverview): GpuSlotOverview {
  const nodes = Array.isArray(raw.nodes) ? raw.nodes.map(normalizeNode) : []
  const slotCount = nodes.reduce((total, node) => total + node.slots.length, 0)

  return {
    schemaVersion: asString(raw.schemaVersion),
    configured: raw.configured === true,
    nodeCount: typeof raw.nodeCount === 'number' ? raw.nodeCount : nodes.length,
    slotCount: typeof raw.slotCount === 'number' ? raw.slotCount : slotCount,
    schedulableSlotCount: typeof raw.schedulableSlotCount === 'number'
      ? raw.schedulableSlotCount
      : nodes.reduce(
        (total, node) => total + node.slots.filter(slot => slot.schedulable).length,
        0
      ),
    nodes
  }
}

function normalizeAllocation(raw: RawAllocation): GpuAllocation {
  return {
    id: asString(raw.allocation_id) || asString(raw.id),
    task_id: asString(raw.task_id),
    execution_attempt_id: asNullableString(raw.execution_attempt_id),
    gpu_node_id: asString(raw.gpu_node_id),
    gpu_index: asNullableNumber(raw.gpu_index),
    slot_id: asNullableString(raw.slot_id),
    accelerator_model: asNullableString(raw.accelerator_model),
    accelerator_vendor: asNullableString(raw.accelerator_vendor),
    memory_allocated_mb: asNullableNumber(raw.memory_allocated_mb),
    status: asString(raw.status),
    allocated_at: asNullableString(raw.allocated_at)
  }
}

/** 卡位总览：节点与卡位声明、当前状态。 */
export async function getGpuSlotOverview(): Promise<ApiResponse<GpuSlotOverview>> {
  const response = await get<RawSlotOverview>('/gpu/slots', undefined, READ_OPTIONS)
  // 后端已按 docs/05 §1.2 返回 { code, message, data }，这里不再对「信封缺失」做兜底：
  // 若 data 缺失就让 normalizer 抛错，由视图区分「未配置卡位」与「请求失败」。
  return { ...response, data: normalizeSlotOverview(response.data) }
}

/** 活跃的 GPU 分配列表。 */
export async function listGpuAllocations(params?: { status?: string }): Promise<ApiResponse<GpuAllocation[]>> {
  const response = await get<RawAllocationStats>('/gpu/allocations', params, READ_OPTIONS)
  const allocations = Array.isArray(response.data?.allocations) ? response.data.allocations : []
  return { ...response, data: allocations.map(normalizeAllocation) }
}
