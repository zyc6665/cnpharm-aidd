/**
 * 算力卡位（GPU slot）相关类型。
 *
 * 卡位声明随部署版本化（DRP_NODE_SLOTS_YAML / DRP_NODE_SLOTS_FILE），
 * 后端只提供只读视图与分配查询，前端不提供任何写接口。
 */

/**
 * 卡位状态枚举，与后端 SLOT_STATES 一致。
 *
 * `UNKNOWN` 是前端侧的安全兜底：后端若返回未声明状态（新增状态或拼写错误），
 * 一律落到 `UNKNOWN` 并保留原始字符串，绝不降级成 `FREE`——
 * 把不确定的卡位显示成「空闲」会直接误导调度。
 */
export type GpuSlotState = 'FREE' | 'RESERVED' | 'BUSY' | 'FAULT' | 'BORROWED' | 'UNKNOWN'

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
  /** 后端原始状态字符串；`state === 'UNKNOWN'` 时页面需原样展示以便排障。 */
  raw_state: string
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

/**
 * 一次 GPU 占用租约。
 *
 * 字段严格对应 `backend/app/gpu/allocator.py::_get_active_allocation_summaries()`
 * 的真实返回，不虚构后端没有的列。`gpu_index` 允许为 null（缺失时页面渲染 '-'，
 * 不能捏造成 0 假装是 0 号卡）。
 */
export interface GpuAllocation {
  id: string
  task_id: string
  execution_attempt_id: string | null
  gpu_node_id: string
  gpu_index: number | null
  slot_id: string | null
  accelerator_model: string | null
  accelerator_vendor: string | null
  memory_allocated_mb: number | null
  status: string
  allocated_at: string | null
}

/** GET /api/v1/gpu/k8s 的返回体（管理后台「算力队列」K8s 视图）。 */
export interface K8sComputeNode {
  name: string
  ready: boolean
  roles: string[]
  gpuCapacity: number
  gpuAllocatable: number
  cpu?: string | null
  memory?: string | null
  os?: string | null
  kubeletVersion?: string | null
  createdAt?: string | null
}

export interface K8sComputePod {
  name: string
  phase?: string | null
  node?: string | null
  gpu: number
  jobName?: string | null
  startTime?: string | null
}

export interface K8sComputeJob {
  name: string
  active: number
  succeeded: number
  failed: number
  startTime?: string | null
  completionTime?: string | null
}

export interface K8sComputeOverview {
  configured: boolean
  clusterAlias?: string | null
  namespace?: string
  apiServer?: string | null
  reason?: string
  nodeCount: number
  gpuCapacity: number
  gpuAllocatable: number
  gpuAllocated: number
  runningPods?: number
  runningJobs: number
  nodes: K8sComputeNode[]
  pods: K8sComputePod[]
  jobs: K8sComputeJob[]
}
