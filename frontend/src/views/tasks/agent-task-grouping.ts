import type {
  AiddAgentRun,
  AiddAgentRunStatus,
  AiddAgentStepStatus,
  Task
} from '@/types/models'

export type TaskCenterTab = 'all' | 'running' | 'history'
export type TaskContentTypeTab = 'all' | 'agent' | 'standalone'

export interface AgentRunFilterOptions {
  tab: TaskCenterTab
  keyword?: string
  toolId?: string
}

export interface AgentRunProgress {
  total: number
  completed: number
  failed: number
  active: number
  percent: number
}

export interface TaskCenterPaginationOptions {
  taskTypeTab: TaskContentTypeTab
  visibleStandaloneTaskTotal: number
  filteredAgentRunTotal: number
}

export interface AgentRunPaginationOptions {
  taskTypeTab: TaskContentTypeTab
  currentPage: number
  pageSize: number
}

export function shouldShowAgentSection(tab: TaskContentTypeTab): boolean {
  return tab === 'all' || tab === 'agent'
}

export function shouldShowStandaloneSection(tab: TaskContentTypeTab): boolean {
  return tab === 'all' || tab === 'standalone'
}

const TERMINAL_AGENT_RUN_STATUSES = new Set<AiddAgentRunStatus>(['success', 'failure', 'canceled'])
const ACTIVE_AGENT_STEP_STATUSES = new Set<AiddAgentStepStatus>(['pending', 'ready', 'running', 'waiting_task'])

export function isTerminalAgentRunStatus(status: AiddAgentRunStatus): boolean {
  return TERMINAL_AGENT_RUN_STATUSES.has(status)
}

export function isActiveAgentRunStatus(status: AiddAgentRunStatus): boolean {
  return !isTerminalAgentRunStatus(status)
}

export function collectAgentTaskIds(runs: AiddAgentRun[]): Set<string> {
  const ids = new Set<string>()

  for (const run of runs) {
    for (const step of run.steps || []) {
      if (step.task_id) {
        ids.add(step.task_id)
      }
    }
  }

  return ids
}

export function filterStandaloneTasks(tasks: Task[], agentTaskIds: Set<string>): Task[] {
  return tasks.filter(task => !agentTaskIds.has(task.id))
}

function runMatchesTab(run: AiddAgentRun, tab: TaskCenterTab): boolean {
  if (tab === 'running') {
    return isActiveAgentRunStatus(run.status)
  }

  if (tab === 'history') {
    return isTerminalAgentRunStatus(run.status)
  }

  return true
}

function normalizeSearchText(value: unknown): string {
  return typeof value === 'string' ? value.toLowerCase() : ''
}

function runMatchesKeyword(run: AiddAgentRun, keyword?: string): boolean {
  const normalizedKeyword = keyword?.trim().toLowerCase()
  if (!normalizedKeyword) {
    return true
  }

  const searchableText = [
    run.id,
    run.message,
    run.summary,
    run.intent,
    ...run.steps.flatMap(step => [
      step.id,
      step.step_key,
      step.tool_slug,
      step.task_id
    ])
  ]
    .map(normalizeSearchText)
    .join(' ')

  return searchableText.includes(normalizedKeyword)
}

function runMatchesTool(run: AiddAgentRun, toolId?: string): boolean {
  if (!toolId) {
    return true
  }

  return run.steps.some(step => step.tool_id === toolId)
}

export function filterAgentRunsForTaskCenter(
  runs: AiddAgentRun[],
  options: AgentRunFilterOptions
): AiddAgentRun[] {
  return runs.filter(run =>
    runMatchesTab(run, options.tab) &&
    runMatchesKeyword(run, options.keyword) &&
    runMatchesTool(run, options.toolId)
  )
}

export function getTaskCenterPaginationTotal(options: TaskCenterPaginationOptions): number {
  if (options.taskTypeTab === 'agent') {
    return options.filteredAgentRunTotal
  }

  return options.visibleStandaloneTaskTotal
}

export function paginateStandaloneTasksForTaskCenter(
  tasks: Task[],
  options: AgentRunPaginationOptions
): Task[] {
  if (options.taskTypeTab === 'agent') {
    return []
  }

  const start = (options.currentPage - 1) * options.pageSize
  return tasks.slice(start, start + options.pageSize)
}

export function paginateAgentRunsForTaskCenter(
  runs: AiddAgentRun[],
  options: AgentRunPaginationOptions
): AiddAgentRun[] {
  if (options.taskTypeTab === 'standalone') {
    return []
  }

  if (options.taskTypeTab === 'all') {
    return options.currentPage === 1 ? runs : []
  }

  const start = (options.currentPage - 1) * options.pageSize
  return runs.slice(start, start + options.pageSize)
}

export function getAgentRunProgress(run: AiddAgentRun): AgentRunProgress {
  const steps = run.steps || []
  const total = steps.length
  const completed = steps.filter(step => step.status === 'success').length
  const failed = steps.filter(step => step.status === 'failure').length
  const active = steps.filter(step => ACTIVE_AGENT_STEP_STATUSES.has(step.status)).length
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0

  return {
    total,
    completed,
    failed,
    active,
    percent
  }
}
