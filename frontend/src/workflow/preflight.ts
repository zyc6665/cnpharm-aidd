import type { ArtifactFile, ToolContract } from '@/types/models'
import type {
  WorkflowArtifactSemanticType,
  WorkflowStepStatus,
  WorkflowTaskRef,
} from './artifact-types.ts'
import {
  WORKFLOW_ARTIFACT_SEMANTIC_TYPES,
  normalizeWorkflowSemanticType,
} from './semantic-types.ts'
import type { WorkflowCanvasPreset } from './canvas-types.ts'
import { formatWorkflowKey } from './i18n-utils.ts'

export type WorkflowPreflightIssueType =
  | 'missing_tool'
  | 'missing_workflow_input'
  | 'waiting_upstream'
  | 'waiting_input'
  | 'invalid_file_extension'
  | 'invalid_semantic_edge'
  | 'invalid_tool_contract'
  | 'running'
  | 'failed'
  | 'invalidated'

export type WorkflowPreflightSeverity = 'error' | 'warning' | 'info'

export interface WorkflowPreflightIssue {
  id: string
  nodeId: string
  nodeTitle: string
  type: WorkflowPreflightIssueType
  severity: WorkflowPreflightSeverity
  title: string
  detail: string
}

export type WorkflowPreflightResourceScalar = string | number | boolean

export interface WorkflowPreflightResourceSummary {
  id: string
  nodeId: string
  nodeTitle: string
  toolSlug: string
  toolName: string
  executorType?: string
  tier?: string
  cpu?: WorkflowPreflightResourceScalar
  memoryGb?: WorkflowPreflightResourceScalar
  gpuRequired?: boolean
  gpuMemoryGb?: WorkflowPreflightResourceScalar
  expectedMinutes?: WorkflowPreflightResourceScalar
  timeoutMinutes?: WorkflowPreflightResourceScalar
  label: string
}

export interface WorkflowPreflightSummary {
  canRun: boolean
  runnableCount: number
  blockedCount: number
  completedCount: number
  runningCount: number
  failedCount: number
  issues: WorkflowPreflightIssue[]
  resourceSummaries: WorkflowPreflightResourceSummary[]
  primaryMessage: string
}

interface WorkflowPreflightTool {
  slug: string
  name?: string
  contract?: ToolContract | null
}

const WORKFLOW_INPUT_ACCEPTED_EXTENSIONS: Record<WorkflowArtifactSemanticType, readonly string[]> = {
  'protein_structure@1': ['.pdb', '.cif'],
  'binding_pocket@1': ['.pdb', '.cif'],
  'ligand_structure@1': ['.sdf', '.mol2', '.pdb'],
  'molecule_table@1': ['.csv', '.smi', '.txt', '.tsv', '.json'],
  'run_report@1': ['.json', '.csv', '.txt', '.md'],
  protein_pdb: ['.pdb', '.cif'],
  pocket_pdb: ['.pdb', '.cif'],
  generated_ligand: ['.sdf', '.mol2', '.pdb'],
  ligand_pdb: ['.pdb', '.sdf', '.mol2'],
  smiles_csv: ['.csv', '.smi', '.txt'],
  ranking_csv: ['.csv', '.tsv'],
  docking_pose: ['.pdb', '.sdf', '.mol2'],
  docking_report: ['.json', '.csv', '.txt'],
  affinity_report: ['.json', '.csv', '.txt'],
  property_report: ['.json', '.csv', '.txt'],
  optimized_lead: ['.sdf', '.mol2', '.csv', '.json'],
}

export function buildWorkflowPreflight(input: {
  template: WorkflowCanvasPreset
  nodeStatuses: Record<string, WorkflowStepStatus>
  readyNodeIds: string[]
  selectedWorkflowInputFiles?: Record<string, string>
  artifacts?: ArtifactFile[]
  taskByNode?: Record<string, WorkflowTaskRef | null | undefined>
  selectedToolByNode?: Record<string, string>
  toolsBySlug?: Record<string, WorkflowPreflightTool>
}): WorkflowPreflightSummary {
  const toolNodes = input.template.nodes.filter((node) => node.type === 'tool')
  const readyNodeIds = new Set(input.readyNodeIds)
  const artifactsById = new Map((input.artifacts ?? []).map((artifact) => [artifact.id, artifact]))
  const nodeById = new Map(input.template.nodes.map((node) => [node.id, node]))
  const issues: WorkflowPreflightIssue[] = []
  const resourceSummaries: WorkflowPreflightResourceSummary[] = []
  const issueIds = new Set<string>()
  let completedCount = 0
  let runningCount = 0
  let failedCount = 0

  for (const edge of input.template.edges) {
    const sourceNode = nodeById.get(edge.source)
    const targetNode = nodeById.get(edge.target)
    const artifactType = edge.artifactType
    if (!sourceNode || !targetNode || !artifactType) {
      continue
    }

    const sourceOutputs = sourceNode.producedOutputTypes ?? []
    const targetInputs = targetNode.requiredInputTypes ?? []
    if (!sourceOutputs.includes(artifactType) || !targetInputs.includes(artifactType)) {
      pushIssue(issues, issueIds, createIssue(edge.target, formatWorkflowKey(targetNode.titleKey), 'invalid_semantic_edge', {
        semanticType: artifactType,
        sourceNodeTitle: formatWorkflowKey(sourceNode.titleKey),
      }))
    }
  }

  for (const node of toolNodes) {
    const status = input.nodeStatuses[node.id] ?? 'idle'
    if (status === 'completed') {
      completedCount += 1
    }
    if (status === 'running') {
      runningCount += 1
      pushIssue(issues, issueIds, createIssue(node.id, formatWorkflowKey(node.titleKey), 'running'))
    }
    if (status === 'failed') {
      failedCount += 1
      pushIssue(issues, issueIds, createIssue(node.id, formatWorkflowKey(node.titleKey), 'failed'))
    }
    if (status === 'invalidated') {
      pushIssue(issues, issueIds, createIssue(node.id, formatWorkflowKey(node.titleKey), 'invalidated'))
    }
    if (status === 'needs_tool_selection') {
      pushIssue(issues, issueIds, createIssue(node.id, formatWorkflowKey(node.titleKey), 'missing_tool'))
    }

    const selectedToolSlug = input.selectedToolByNode?.[node.id]
      ?? node.recommendedToolSlug
      ?? ((node.toolSlugs?.length ?? 0) === 1 ? node.toolSlugs?.[0] : undefined)
    const selectedTool = selectedToolSlug ? input.toolsBySlug?.[selectedToolSlug] : undefined
    if (selectedToolSlug && selectedTool && hasInvalidToolContract(selectedTool.contract)) {
      pushIssue(issues, issueIds, createIssue(node.id, formatWorkflowKey(node.titleKey), 'invalid_tool_contract', {
        toolSlug: selectedToolSlug,
      }))
    }
    if (selectedToolSlug && selectedTool) {
      const resourceSummary = buildResourceSummary({
        nodeId: node.id,
        nodeTitle: formatWorkflowKey(node.titleKey),
        toolSlug: selectedToolSlug,
        tool: selectedTool,
      })
      if (resourceSummary) {
        resourceSummaries.push(resourceSummary)
      }
    }

    const incomingEdges = input.template.edges.filter((edge) => edge.target === node.id && edge.artifactType)
    for (const edge of incomingEdges) {
      const sourceNode = nodeById.get(edge.source)
      const artifactType = edge.artifactType
      if (!sourceNode || !artifactType) {
        continue
      }

      if (sourceNode.type === 'input') {
        const selectedArtifactId = input.selectedWorkflowInputFiles?.[artifactType]
        if (!selectedArtifactId) {
          pushIssue(issues, issueIds, createIssue(node.id, formatWorkflowKey(node.titleKey), 'missing_workflow_input', {
            semanticType: artifactType,
          }))
          continue
        }

        const artifact = artifactsById.get(selectedArtifactId)
        if (artifact && !hasAcceptedExtensionForSemanticType(artifact.filename, artifactType)) {
          pushIssue(issues, issueIds, createIssue(node.id, formatWorkflowKey(node.titleKey), 'invalid_file_extension', {
            semanticType: artifactType,
            filename: artifact.filename,
          }))
        }
        continue
      }

      const upstreamTask = input.taskByNode?.[sourceNode.id]
      if (upstreamTask?.status !== 'success') {
        pushIssue(issues, issueIds, createIssue(node.id, formatWorkflowKey(node.titleKey), 'waiting_upstream', {
          semanticType: artifactType,
          sourceNodeTitle: formatWorkflowKey(sourceNode.titleKey),
        }))
      }
    }

    if (status === 'idle' && node.requiredInputTypes?.length && incomingEdges.length === 0) {
      pushIssue(issues, issueIds, createIssue(node.id, formatWorkflowKey(node.titleKey), 'waiting_input'))
    }
  }

  const runnableCount = toolNodes.filter((node) => readyNodeIds.has(node.id)).length
  const blockedCount = issues.filter((issue) => issue.severity === 'error' || issue.severity === 'warning').length

  return {
    canRun: runnableCount > 0 && runningCount === 0,
    runnableCount,
    blockedCount,
    completedCount,
    runningCount,
    failedCount,
    issues,
    resourceSummaries,
    primaryMessage: resolvePrimaryMessage({
      runnableCount,
      issues,
    }),
  }
}

function resolvePrimaryMessage(input: {
  runnableCount: number
  issues: WorkflowPreflightIssue[]
}): string {
  if (input.runnableCount > 0) {
    return `有 ${input.runnableCount} 个节点可运行`
  }

  if (input.issues.some((issue) => issue.type === 'missing_workflow_input')) {
    return '请先补齐工作流输入'
  }

  if (input.issues.some((issue) => issue.type === 'invalid_tool_contract')) {
    return '存在不可执行的工具契约，请先修复节点工具'
  }

  if (input.issues.some((issue) => issue.type === 'invalid_semantic_edge')) {
    return '存在无效连线，请先修复节点依赖'
  }

  return '当前没有可运行节点'
}

function pushIssue(
  issues: WorkflowPreflightIssue[],
  issueIds: Set<string>,
  issue: WorkflowPreflightIssue,
) {
  if (issueIds.has(issue.id)) {
    return
  }

  issueIds.add(issue.id)
  issues.push(issue)
}

function createIssue(
  nodeId: string,
  nodeTitle: string,
  type: WorkflowPreflightIssueType,
  detailInput: {
    semanticType?: string
    sourceNodeTitle?: string
    filename?: string
    toolSlug?: string
  } = {},
): WorkflowPreflightIssue {
  const semanticType = detailInput.semanticType ?? ''
  const sourceNodeTitle = detailInput.sourceNodeTitle ?? '上游节点'
  const filename = detailInput.filename ?? '未知文件'
  const toolSlug = detailInput.toolSlug ?? '未指定工具'

  const issueTextByType: Record<WorkflowPreflightIssueType, {
    severity: WorkflowPreflightSeverity
    title: string
    detail: string
  }> = {
    missing_tool: {
      severity: 'error',
      title: '缺少工具选择',
      detail: '该节点存在多个候选工具，运行前需要明确指定其中一个工具。'
    },
    missing_workflow_input: {
      severity: 'error',
      title: '缺少工作流输入',
      detail: `请先为语义输入 ${semanticType} 选择可用文件后再继续运行。`
    },
    waiting_upstream: {
      severity: 'warning',
      title: '等待上游产物',
      detail: `依赖 ${sourceNodeTitle} 输出的 ${semanticType} 结果，当前还没有成功产出。`
    },
    waiting_input: {
      severity: 'warning',
      title: '等待输入连线',
      detail: '该节点声明了必需输入，但当前还没有配置任何可用输入来源。'
    },
    invalid_file_extension: {
      severity: 'error',
      title: '输入文件格式不匹配',
      detail: `已选择文件 ${filename} 与当前语义输入 ${semanticType} 的扩展名要求不匹配。`
    },
    invalid_semantic_edge: {
      severity: 'error',
      title: '连线语义无效',
      detail: `当前连线的语义类型 ${semanticType} 与上下游节点定义不一致，请检查节点依赖。`
    },
    invalid_tool_contract: {
      severity: 'error',
      title: '工具契约不可执行',
      detail: `当前节点绑定的工具 ${toolSlug} 缺少有效工作流契约或已被禁用。`
    },
    running: {
      severity: 'info',
      title: '节点正在运行',
      detail: '等待当前任务结束后再继续调度后续节点。'
    },
    failed: {
      severity: 'error',
      title: '节点任务失败',
      detail: '请先检查任务日志、参数或输入文件，再决定是否重新运行。'
    },
    invalidated: {
      severity: 'warning',
      title: '节点需要重跑',
      detail: '上游输入或参数已经变化，建议重新运行该节点以刷新结果。'
    }
  }
  const text = issueTextByType[type]

  return {
    id: `${nodeId}-${type}-${semanticType}-${toolSlug}`,
    nodeId,
    nodeTitle,
    type,
    severity: text.severity,
    title: text.title,
    detail: text.detail,
  }
}

function buildResourceSummary(input: {
  nodeId: string
  nodeTitle: string
  toolSlug: string
  tool: WorkflowPreflightTool
}): WorkflowPreflightResourceSummary | null {
  const contract = input.tool.contract
  const resourceProfile = contract?.resource_profile
  if (!resourceProfile || Object.keys(resourceProfile).length === 0) {
    return null
  }

  const label = formatResourceProfileLabel(resourceProfile)
  if (!label) {
    return null
  }

  return {
    id: `${input.nodeId}-${input.toolSlug}-resources`,
    nodeId: input.nodeId,
    nodeTitle: input.nodeTitle,
    toolSlug: input.toolSlug,
    toolName: input.tool.name ?? contract?.name ?? input.toolSlug,
    executorType: contract?.executor.type,
    tier: readResourceText(resourceProfile.tier),
    cpu: readResourceScalar(resourceProfile.cpu),
    memoryGb: readResourceScalar(resourceProfile.memory_gb),
    gpuRequired: readResourceBoolean(resourceProfile.gpu_required),
    gpuMemoryGb: readResourceScalar(resourceProfile.gpu_memory_gb),
    expectedMinutes: readResourceScalar(resourceProfile.expected_minutes),
    timeoutMinutes: readResourceScalar(resourceProfile.timeout_minutes),
    label,
  }
}

function formatResourceProfileLabel(resourceProfile: Record<string, unknown>): string {
  const segments: string[] = []
  const tier = readResourceText(resourceProfile.tier)
  const cpu = readResourceScalar(resourceProfile.cpu)
  const memoryGb = readResourceScalar(resourceProfile.memory_gb)
  const gpuRequired = readResourceBoolean(resourceProfile.gpu_required)
  const gpuMemoryGb = readResourceScalar(resourceProfile.gpu_memory_gb)
  const expectedMinutes = readResourceScalar(resourceProfile.expected_minutes)
  const timeoutMinutes = readResourceScalar(resourceProfile.timeout_minutes)

  if (tier) {
    segments.push(tier)
  }
  if (cpu !== undefined) {
    segments.push(`CPU ${cpu}`)
  }
  if (memoryGb !== undefined) {
    segments.push(`MEM ${memoryGb}GB`)
  }
  if (gpuRequired) {
    segments.push(gpuMemoryGb !== undefined ? `GPU ${gpuMemoryGb}GB` : 'GPU')
  }
  if (expectedMinutes !== undefined) {
    segments.push(`ETA ${expectedMinutes}m`)
  }
  if (timeoutMinutes !== undefined) {
    segments.push(`Timeout ${timeoutMinutes}m`)
  }

  return segments.join(' · ')
}

function readResourceText(value: unknown): string | undefined {
  const scalar = readResourceScalar(value)
  return scalar === undefined ? undefined : String(scalar)
}

function readResourceScalar(value: unknown): WorkflowPreflightResourceScalar | undefined {
  if (value === undefined || value === null || value === '') {
    return undefined
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return value
  }
  return String(value)
}

function readResourceBoolean(value: unknown): boolean | undefined {
  if (typeof value === 'boolean') {
    return value
  }
  if (typeof value === 'number') {
    return value > 0
  }
  if (typeof value === 'string') {
    if (value.toLowerCase() === 'true') {
      return true
    }
    if (value.toLowerCase() === 'false') {
      return false
    }
  }
  return undefined
}

function hasInvalidToolContract(contract?: ToolContract | null) {
  if (!contract) {
    return true
  }

  return contract.validation.status !== 'valid' || contract.capability.enabled !== true
}

function hasAcceptedExtensionForSemanticType(filename: string, semanticType: string): boolean {
  const normalizedType = normalizeWorkflowSemanticType(semanticType)
  if (!(WORKFLOW_ARTIFACT_SEMANTIC_TYPES as readonly string[]).includes(normalizedType)) {
    return true
  }

  const acceptedExtensions = WORKFLOW_INPUT_ACCEPTED_EXTENSIONS[normalizedType as WorkflowArtifactSemanticType]
  if (!acceptedExtensions || acceptedExtensions.length === 0) {
    return true
  }

  const normalizedFilename = filename.toLowerCase()
  return acceptedExtensions.some((extension) => normalizedFilename.endsWith(extension.toLowerCase()))
}
