import type {
  ArtifactBindingDecision,
  ArtifactFile,
  ToolContract,
  WorkflowRunNodeState,
} from '@/types/models'
import type {
  WorkflowArtifactSemanticType,
  WorkflowStepStatus,
  WorkflowTaskRef,
} from './artifact-types.ts'
import { normalizeWorkflowSemanticType } from './semantic-types.ts'
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
  | 'needs_preparation'
  | 'needs_conversion'
  | 'invalid_artifact_binding'
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

interface WorkflowPreflightIssueContext {
  semanticType: string
  sourceNodeTitle: string
  filename: string
  toolSlug: string
}

interface WorkflowPreflightIssueLabel {
  title: string
  detail: (context: WorkflowPreflightIssueContext) => string
}

export interface WorkflowPreflightLabels {
  nodeTitleFallback: string
  sourceNodeFallback: string
  filenameFallback: string
  toolSlugFallback: string
  inputArtifactFallback: string
  invalidArtifactBindingTitle: string
  primary: {
    runnableNodes: (count: number) => string
    missingWorkflowInput: string
    invalidToolContract: string
    invalidSemanticEdge: string
    needsPreparationOrConversion: string
    invalidArtifactBinding: string
    empty: string
  }
  issues: Record<WorkflowPreflightIssueType, WorkflowPreflightIssueLabel>
  savedArtifactBindingMissing: (input: { slotName: string; artifactId: string }) => string
  savedArtifactBindingMismatch: (input: { slotName: string; artifactId: string }) => string
  bindingSuggestion: (suggestedTool: string) => string
  bindingFallbackPreparation: (target: string) => string
  bindingFallbackConversion: (target: string) => string
  bindingFallbackInvalid: (target: string) => string
}

const WORKFLOW_PREFLIGHT_ISSUE_SEVERITY: Record<WorkflowPreflightIssueType, WorkflowPreflightSeverity> = {
  missing_tool: 'error',
  missing_workflow_input: 'error',
  waiting_upstream: 'warning',
  waiting_input: 'warning',
  invalid_file_extension: 'error',
  invalid_semantic_edge: 'error',
  invalid_tool_contract: 'error',
  needs_preparation: 'warning',
  needs_conversion: 'warning',
  invalid_artifact_binding: 'error',
  running: 'info',
  failed: 'error',
  invalidated: 'warning',
}

export const DEFAULT_WORKFLOW_PREFLIGHT_LABELS: WorkflowPreflightLabels = {
  nodeTitleFallback: 'Untitled Node',
  sourceNodeFallback: 'upstream node',
  filenameFallback: 'unknown file',
  toolSlugFallback: 'unspecified tool',
  inputArtifactFallback: 'input artifact',
  invalidArtifactBindingTitle: 'Invalid standard artifact binding',
  primary: {
    runnableNodes: count => `${count} node${count === 1 ? '' : 's'} ready to run`,
    missingWorkflowInput: 'Complete workflow inputs first',
    invalidToolContract: 'Some tool contracts are not executable; fix node tools first',
    invalidSemanticEdge: 'Some links are invalid; fix node dependencies first',
    needsPreparationOrConversion: 'Some standard artifacts need preparation or conversion',
    invalidArtifactBinding: 'Some standard artifact bindings are unavailable',
    empty: 'No runnable nodes right now',
  },
  issues: {
    missing_tool: {
      title: 'Missing tool selection',
      detail: () => 'This node has multiple candidate tools. Select one before running.',
    },
    missing_workflow_input: {
      title: 'Missing workflow input',
      detail: ({ semanticType }) => `Select an available file for semantic input ${semanticType} before continuing.`,
    },
    waiting_upstream: {
      title: 'Waiting for upstream artifact',
      detail: ({ sourceNodeTitle, semanticType }) => `Run ${sourceNodeTitle} first; ${semanticType} will bind to this node after success.`,
    },
    waiting_input: {
      title: 'Waiting for input link',
      detail: () => 'This node declares required inputs, but no available input source is configured.',
    },
    invalid_file_extension: {
      title: 'Input file format mismatch',
      detail: ({ filename, semanticType }) => `Selected file ${filename} does not match extension requirements for ${semanticType}.`,
    },
    invalid_semantic_edge: {
      title: 'Invalid link semantic type',
      detail: ({ semanticType }) => `The link semantic type ${semanticType} does not match upstream and downstream node definitions.`,
    },
    invalid_tool_contract: {
      title: 'Tool contract is not executable',
      detail: ({ toolSlug }) => `The bound tool ${toolSlug} has no valid workflow contract or is disabled.`,
    },
    needs_preparation: {
      title: 'Input artifact needs preparation',
      detail: () => 'This node input artifact does not satisfy tool requirements. Run the matching preparation tool first.',
    },
    needs_conversion: {
      title: 'Input artifact needs conversion',
      detail: () => 'This node input artifact must be converted before the tool can consume it.',
    },
    invalid_artifact_binding: {
      title: 'Invalid standard artifact binding',
      detail: () => 'This node standard artifact binding is unavailable. Select the input again or check upstream outputs.',
    },
    running: {
      title: 'Node is running',
      detail: () => 'Wait for the current task to finish before scheduling downstream nodes.',
    },
    failed: {
      title: 'Node task failed',
      detail: () => 'Check task logs, parameters, or input files before deciding whether to rerun.',
    },
    invalidated: {
      title: 'Node needs rerun',
      detail: () => 'Upstream inputs or parameters changed. Rerun this node to refresh results.',
    },
  },
  savedArtifactBindingMissing: ({ slotName, artifactId }) => `Saved ${slotName} binding ${artifactId} is not in the available artifact list. Select the input again.`,
  savedArtifactBindingMismatch: ({ slotName, artifactId }) => `Saved ${slotName} binding ${artifactId} does not match current input requirements. Select the input again.`,
  bindingSuggestion: suggestedTool => `Suggested tool: ${suggestedTool}.`,
  bindingFallbackPreparation: target => `${target} must be prepared first.`,
  bindingFallbackConversion: target => `${target} must be converted first.`,
  bindingFallbackInvalid: target => `${target} binding is unavailable.`,
}

const WORKFLOW_INPUT_ACCEPTED_EXTENSIONS: Partial<Record<WorkflowArtifactSemanticType, readonly string[]>> = {
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
  artifactBindingsByNode?: Record<string, Record<string, string>>
  taskByNode?: Record<string, WorkflowTaskRef | null | undefined>
  workflowRunNodeStates?: Record<string, WorkflowRunNodeState | null | undefined>
  selectedToolByNode?: Record<string, string>
  toolsBySlug?: Record<string, WorkflowPreflightTool>
  labels?: WorkflowPreflightLabels
}): WorkflowPreflightSummary {
  const labels = input.labels ?? DEFAULT_WORKFLOW_PREFLIGHT_LABELS
  const toolNodes = input.template.nodes.filter((node) => node.type === 'tool')
  const readyNodeIds = new Set(input.readyNodeIds)
  const artifactsById = new Map((input.artifacts ?? []).map((artifact) => [artifact.id, artifact]))
  const artifactsByBindingId = buildArtifactBindingLookup(input.artifacts ?? [])
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
      pushIssue(issues, issueIds, createIssue(edge.target, formatPreflightNodeTitle(targetNode.titleKey, labels), 'invalid_semantic_edge', labels, {
        semanticType: artifactType,
        sourceNodeTitle: formatPreflightNodeTitle(sourceNode.titleKey, labels),
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
      pushIssue(issues, issueIds, createIssue(node.id, formatPreflightNodeTitle(node.titleKey, labels), 'running', labels))
    }
    if (status === 'failed') {
      failedCount += 1
      pushIssue(issues, issueIds, createIssue(node.id, formatPreflightNodeTitle(node.titleKey, labels), 'failed', labels))
    }
    if (status === 'invalidated') {
      pushIssue(issues, issueIds, createIssue(node.id, formatPreflightNodeTitle(node.titleKey, labels), 'invalidated', labels))
    }
    if (status === 'needs_tool_selection') {
      pushIssue(issues, issueIds, createIssue(node.id, formatPreflightNodeTitle(node.titleKey, labels), 'missing_tool', labels))
    }

    for (const issue of createBindingDecisionIssues({
      nodeId: node.id,
      nodeTitle: formatPreflightNodeTitle(node.titleKey, labels),
      task: input.taskByNode?.[node.id] ?? null,
      nodeState: input.workflowRunNodeStates?.[node.id] ?? null,
      labels,
    })) {
      pushIssue(issues, issueIds, issue)
    }

    for (const issue of createSavedArtifactBindingIssues({
      node,
      nodeTitle: formatPreflightNodeTitle(node.titleKey, labels),
      bindings: input.artifactBindingsByNode?.[node.id],
      artifactsByBindingId,
      labels,
    })) {
      pushIssue(issues, issueIds, issue)
    }

    const selectedToolSlug = input.selectedToolByNode?.[node.id]
      ?? node.recommendedToolSlug
      ?? ((node.toolSlugs?.length ?? 0) === 1 ? node.toolSlugs?.[0] : undefined)
    const selectedTool = selectedToolSlug ? input.toolsBySlug?.[selectedToolSlug] : undefined
    if (selectedToolSlug && selectedTool && hasInvalidToolContract(selectedTool.contract)) {
      pushIssue(issues, issueIds, createIssue(node.id, formatPreflightNodeTitle(node.titleKey, labels), 'invalid_tool_contract', labels, {
        toolSlug: selectedToolSlug,
      }))
    }
    if (selectedToolSlug && selectedTool) {
      const resourceSummary = buildResourceSummary({
        nodeId: node.id,
        nodeTitle: formatPreflightNodeTitle(node.titleKey, labels),
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
          pushIssue(issues, issueIds, createIssue(node.id, formatPreflightNodeTitle(node.titleKey, labels), 'missing_workflow_input', labels, {
            semanticType: artifactType,
          }))
          continue
        }

        const artifact = artifactsById.get(selectedArtifactId)
        if (artifact && !hasAcceptedExtensionForSemanticType(artifact.filename, artifactType)) {
          pushIssue(issues, issueIds, createIssue(node.id, formatPreflightNodeTitle(node.titleKey, labels), 'invalid_file_extension', labels, {
            semanticType: artifactType,
            filename: artifact.filename,
          }))
        }
        continue
      }

      const upstreamTask = input.taskByNode?.[sourceNode.id]
      if (upstreamTask?.status !== 'success') {
        pushIssue(issues, issueIds, createIssue(node.id, formatPreflightNodeTitle(node.titleKey, labels), 'waiting_upstream', labels, {
          semanticType: artifactType,
          sourceNodeTitle: formatPreflightNodeTitle(sourceNode.titleKey, labels),
        }))
      }
    }

    if (status === 'idle' && node.requiredInputTypes?.length && incomingEdges.length === 0) {
      pushIssue(issues, issueIds, createIssue(node.id, formatPreflightNodeTitle(node.titleKey, labels), 'waiting_input', labels))
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
      labels,
    }),
  }
}

function buildArtifactBindingLookup(artifacts: ArtifactFile[]): Map<string, ArtifactFile> {
  const lookup = new Map<string, ArtifactFile>()
  for (const artifact of artifacts) {
    indexArtifactBindingId(lookup, artifact.id, artifact)
    indexArtifactBindingId(lookup, artifact.artifact_id, artifact)
    indexArtifactBindingId(lookup, artifact.artifact_version_id, artifact)
  }
  return lookup
}

function indexArtifactBindingId(
  lookup: Map<string, ArtifactFile>,
  value: string | null | undefined,
  artifact: ArtifactFile,
) {
  const id = normalizeDecisionText(value)
  if (id) {
    lookup.set(id, artifact)
  }
}

function createSavedArtifactBindingIssues(input: {
  node: WorkflowCanvasPreset['nodes'][number]
  nodeTitle: string
  bindings?: Record<string, string>
  artifactsByBindingId: Map<string, ArtifactFile>
  labels: WorkflowPreflightLabels
}): WorkflowPreflightIssue[] {
  if (!input.bindings || !input.node.inputArtifactSlots?.length) {
    return []
  }

  const slotsByName = new Map(input.node.inputArtifactSlots.map(slot => [slot.name, slot]))
  const issues: WorkflowPreflightIssue[] = []
  for (const [slotName, rawArtifactId] of Object.entries(input.bindings)) {
    const artifactId = normalizeDecisionText(rawArtifactId)
    const slot = slotsByName.get(slotName)
    if (!artifactId || !slot) {
      continue
    }

    const artifact = input.artifactsByBindingId.get(artifactId)
    if (!artifact) {
      issues.push(
        createSavedArtifactBindingIssue(input.node.id, input.nodeTitle, slotName, artifactId, 'missing', input.labels)
      )
      continue
    }

    const expectedType = normalizeWorkflowSemanticType(slot.type)
    const rawArtifactType = normalizeDecisionText(artifact.semantic_type)
    const artifactType = rawArtifactType ? normalizeWorkflowSemanticType(rawArtifactType) : ''
    if (expectedType && artifactType && expectedType !== artifactType) {
      issues.push(
        createSavedArtifactBindingIssue(input.node.id, input.nodeTitle, slotName, artifactId, 'mismatch', input.labels)
      )
    }
  }
  return issues
}

function createSavedArtifactBindingIssue(
  nodeId: string,
  nodeTitle: string,
  slotName: string,
  artifactId: string,
  reason: 'missing' | 'mismatch',
  labels: WorkflowPreflightLabels,
): WorkflowPreflightIssue {
  const detail = reason === 'missing'
    ? labels.savedArtifactBindingMissing({ slotName, artifactId })
    : labels.savedArtifactBindingMismatch({ slotName, artifactId })

  return {
    id: `${nodeId}-invalid_artifact_binding-${slotName}`,
    nodeId,
    nodeTitle,
    type: 'invalid_artifact_binding',
    severity: 'error',
    title: labels.invalidArtifactBindingTitle,
    detail,
  }
}

function resolvePrimaryMessage(input: {
  runnableCount: number
  issues: WorkflowPreflightIssue[]
  labels: WorkflowPreflightLabels
}): string {
  if (input.runnableCount > 0) {
    return input.labels.primary.runnableNodes(input.runnableCount)
  }

  if (input.issues.some((issue) => issue.type === 'missing_workflow_input')) {
    return input.labels.primary.missingWorkflowInput
  }

  if (input.issues.some((issue) => issue.type === 'invalid_tool_contract')) {
    return input.labels.primary.invalidToolContract
  }

  if (input.issues.some((issue) => issue.type === 'invalid_semantic_edge')) {
    return input.labels.primary.invalidSemanticEdge
  }

  if (input.issues.some((issue) => issue.type === 'needs_preparation' || issue.type === 'needs_conversion')) {
    return input.labels.primary.needsPreparationOrConversion
  }

  if (input.issues.some((issue) => issue.type === 'invalid_artifact_binding')) {
    return input.labels.primary.invalidArtifactBinding
  }

  return input.labels.primary.empty
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
  labels: WorkflowPreflightLabels,
  detailInput: {
    semanticType?: string
    sourceNodeTitle?: string
    filename?: string
    toolSlug?: string
  } = {},
): WorkflowPreflightIssue {
  const semanticType = detailInput.semanticType ?? ''
  const context: WorkflowPreflightIssueContext = {
    semanticType,
    sourceNodeTitle: detailInput.sourceNodeTitle ?? labels.sourceNodeFallback,
    filename: detailInput.filename ?? labels.filenameFallback,
    toolSlug: detailInput.toolSlug ?? labels.toolSlugFallback,
  }
  const text = labels.issues[type]

  return {
    id: `${nodeId}-${type}-${semanticType}`,
    nodeId,
    nodeTitle,
    type,
    severity: WORKFLOW_PREFLIGHT_ISSUE_SEVERITY[type],
    title: text.title,
    detail: text.detail(context),
  }
}

function createBindingDecisionIssues(input: {
  nodeId: string
  nodeTitle: string
  task?: WorkflowTaskRef | null
  nodeState?: WorkflowRunNodeState | null
  labels: WorkflowPreflightLabels
}): WorkflowPreflightIssue[] {
  const decisions = {
    ...normalizeBindingDecisions(input.task?.binding_decisions),
    ...normalizeBindingDecisions(input.nodeState?.binding_decisions),
  }
  const issues = Object.entries(decisions).flatMap(([inputName, decision]) => {
    const issue = createBindingDecisionIssue(input.nodeId, input.nodeTitle, inputName, decision, input.labels)
    return issue ? [issue] : []
  })

  if (issues.length === 0 && input.nodeState?.blocked_reason) {
    issues.push({
      id: `${input.nodeId}-invalid_artifact_binding-blocked`,
      nodeId: input.nodeId,
      nodeTitle: input.nodeTitle,
      type: 'invalid_artifact_binding',
      severity: 'error',
      title: input.labels.invalidArtifactBindingTitle,
      detail: input.nodeState.blocked_reason,
    })
  }

  return issues
}

function normalizeBindingDecisions(
  decisions?: Record<string, ArtifactBindingDecision> | null,
): Record<string, ArtifactBindingDecision> {
  if (!decisions || typeof decisions !== 'object') {
    return {}
  }
  return decisions
}

function createBindingDecisionIssue(
  nodeId: string,
  nodeTitle: string,
  inputName: string,
  decision: ArtifactBindingDecision,
  labels: WorkflowPreflightLabels,
): WorkflowPreflightIssue | null {
  const type = bindingIssueType(decision.status)
  if (!type) {
    return null
  }

  const text = bindingIssueText(type, labels)
  const reason = normalizeDecisionText(decision.reason)
  const suggestedTool = normalizeDecisionText(decision.suggested_tool_slug)
  const fallbackDetail = bindingFallbackDetail(type, labels, decision.standard_type, inputName)
  const suggestion = suggestedTool ? labels.bindingSuggestion(suggestedTool) : ''

  return {
    id: `${nodeId}-${type}-${inputName || decision.input_name || 'artifact'}`,
    nodeId,
    nodeTitle,
    type,
    severity: text.severity,
    title: text.title,
    detail: `${reason || fallbackDetail}${suggestion}`,
  }
}

function bindingIssueType(status: string): WorkflowPreflightIssueType | null {
  if (status === 'needs_preparation') {
    return 'needs_preparation'
  }
  if (status === 'needs_conversion') {
    return 'needs_conversion'
  }
  if (status === 'invalid') {
    return 'invalid_artifact_binding'
  }
  return null
}

function bindingIssueText(type: WorkflowPreflightIssueType, labels: WorkflowPreflightLabels): {
  severity: WorkflowPreflightSeverity
  title: string
} {
  if (type === 'needs_preparation') {
    return { severity: 'warning', title: labels.issues.needs_preparation.title }
  }
  if (type === 'needs_conversion') {
    return { severity: 'warning', title: labels.issues.needs_conversion.title }
  }
  return { severity: 'error', title: labels.invalidArtifactBindingTitle }
}

function bindingFallbackDetail(
  type: WorkflowPreflightIssueType,
  labels: WorkflowPreflightLabels,
  standardType?: string | null,
  inputName?: string,
): string {
  const target = standardType || inputName || labels.inputArtifactFallback
  if (type === 'needs_preparation') {
    return labels.bindingFallbackPreparation(target)
  }
  if (type === 'needs_conversion') {
    return labels.bindingFallbackConversion(target)
  }
  return labels.bindingFallbackInvalid(target)
}

function formatPreflightNodeTitle(key: unknown, labels: WorkflowPreflightLabels): string {
  return formatWorkflowKey(key, labels.nodeTitleFallback)
}

function normalizeDecisionText(value?: string | null): string {
  return String(value ?? '').trim()
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
  const acceptedExtensions = WORKFLOW_INPUT_ACCEPTED_EXTENSIONS[normalizedType]
  if (!acceptedExtensions || acceptedExtensions.length === 0) {
    return true
  }

  const normalizedFilename = filename.toLowerCase()
  return acceptedExtensions.some((extension) => normalizedFilename.endsWith(extension.toLowerCase()))
}
