/**
 * 算力卡位与分配相关接口（P-36）。
 *
 * 全部为只读查询：卡位声明随部署版本化（DRP_NODE_SLOTS_YAML /
 * DRP_NODE_SLOTS_FILE），后端不提供写接口，前端亦不提供任何写操作。
 */
import { get } from '@/api/request'
import type { ApiResponse } from '@/types/api'
import type { GpuAllocation, GpuSlot, GpuSlotNode, GpuSlotOverview, GpuSlotState } from '@/types/gpu'

/** 只读查询统一配置：不弹全局错误提示，失败重试一次。 */
const READ_OPTIONS = { silent: true, retry: 1 } as const

const SLOT_STATE_VALUES: readonly GpuSlotState[] = ['FREE', 'RESERVED', 'BUSY', 'FAULT', 'BORROWED']

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

interface RawAllocation {
  id?: string
  allocation_id?: string
  task_id?: string
  slot_id?: string
  gpu_node_id?: string
  gpu_index?: number
  accelerator_model?: string
  status?: string
  allocated_at?: string
  released_at?: string | null
}

interface RawAllocationStats {
  allocations?: RawAllocation[]
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function toSlotState(value: unknown): GpuSlotState {
  return SLOT_STATE_VALUES.find(state => state === value) ?? 'FREE'
}

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
    state: toSlotState(raw.state),
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
    id: asString(raw.id) || asString(raw.allocation_id),
    task_id: asString(raw.task_id),
    slot_id: asString(raw.slot_id),
    gpu_node_id: asString(raw.gpu_node_id),
    gpu_index: typeof raw.gpu_index === 'number' ? raw.gpu_index : 0,
    accelerator_model: asString(raw.accelerator_model),
    status: asString(raw.status),
    allocated_at: asString(raw.allocated_at),
    released_at: typeof raw.released_at === 'string' ? raw.released_at : null
  }
}

/** 卡位总览：节点与卡位声明、当前状态。 */
export async function getGpuSlotOverview(): Promise<ApiResponse<GpuSlotOverview>> {
  const response = await get<RawSlotOverview>('/gpu/slots', undefined, READ_OPTIONS)
  return { ...response, data: normalizeSlotOverview(response.data ?? {}) }
}

/** GPU 汇总信息（显存、利用率）。 */
export async function getGpuSummary(): Promise<ApiResponse<Record<string, unknown>>> {
  return get<Record<string, unknown>>('/gpu/summary', undefined, READ_OPTIONS)
}

/** 活跃的 GPU 分配列表。 */
export async function listGpuAllocations(params?: { status?: string }): Promise<ApiResponse<GpuAllocation[]>> {
  const response = await get<RawAllocationStats>('/gpu/allocations', params, READ_OPTIONS)
  const allocations = Array.isArray(response.data?.allocations) ? response.data.allocations : []
  return { ...response, data: allocations.map(normalizeAllocation) }
}

/** GPU 健康状态。 */
export async function getGpuHealth(): Promise<ApiResponse<Record<string, unknown>>> {
  return get<Record<string, unknown>>('/gpu/health', undefined, READ_OPTIONS)
}
