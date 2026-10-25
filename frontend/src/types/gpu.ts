/**
 * 算力卡位（GPU slot）相关类型。
 *
 * 卡位声明随部署版本化（DRP_NODE_SLOTS_YAML / DRP_NODE_SLOTS_FILE），
 * 后端只提供只读视图与分配查询，前端不提供任何写接口。
 */

/** 卡位状态枚举，与后端 SLOT_STATES 一致。 */
export type GpuSlotState = 'FREE' | 'RESERVED' | 'BUSY' | 'FAULT' | 'BORROWED'

/** 单个卡位（可调度最小单元）。 */
export interface GpuSlot {
  node_id: string
  slot_id: string
  slot_identifier: string
  device_ids: string[]
  accelerator_model: string
  accelerator_vendor: string
  image: string
  models: string[]
  state: GpuSlotState
  schedulable: boolean
  state_message: string
  device_count: number
}

/** 卡位所属节点。 */
export interface GpuSlotNode {
  id: string
  hostname: string
  gpu_count: number
  agent_endpoint: string
  slots: GpuSlot[]
}

/** GET /api/v1/gpu/slots 的返回体。 */
export interface GpuSlotOverview {
  schemaVersion: string
  configured: boolean
  nodeCount: number
  slotCount: number
  schedulableSlotCount: number
  nodes: GpuSlotNode[]
}

/** 一次 GPU 占用租约。 */
export interface GpuAllocation {
  id: string
  task_id: string
  slot_id: string
  gpu_node_id: string
  gpu_index: number
  accelerator_model: string
  status: string
  allocated_at: string
  released_at: string | null
}
