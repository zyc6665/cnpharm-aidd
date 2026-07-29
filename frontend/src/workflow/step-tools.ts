import type { ToolOptionSummary } from '@/types/models'
import type { WorkflowStepKey } from './artifact-types.ts'
import { AIDD_WORKFLOW_STEP_MAP } from './aidd-catalog.ts'

export type WorkflowToolAvailability = 'available' | 'missing'

export interface WorkflowStepToolOption {
  slug: string
  availability: WorkflowToolAvailability
  isRecommended: boolean
  tool?: ToolOptionSummary
}

export interface WorkflowStepToolViewModel {
  stepKey: WorkflowStepKey
  tools: WorkflowStepToolOption[]
  availableToolSlugs: string[]
  missingToolSlugs: string[]
  defaultSelectedToolSlug: string | null
}

function isWorkflowAvailableTool(tool: ToolOptionSummary): boolean {
  return tool.status === 'published' && tool.is_public !== false
}

export function buildWorkflowStepToolViewModel(input: {
  stepKey: WorkflowStepKey
  tools: ToolOptionSummary[]
}): WorkflowStepToolViewModel {
  const step = AIDD_WORKFLOW_STEP_MAP[input.stepKey]
  const availableToolMap = new Map(
    input.tools.filter(isWorkflowAvailableTool).map((tool) => [tool.slug, tool] as const)
  )

  const tools = step.toolSlugs.map<WorkflowStepToolOption>((slug) => {
    const tool = availableToolMap.get(slug)

    return {
      slug,
      availability: tool ? 'available' : 'missing',
      isRecommended: slug === step.recommendedToolSlug,
      tool
    }
  })

  const availableToolSlugs = tools
    .filter((tool) => tool.availability === 'available')
    .map((tool) => tool.slug)
  const missingToolSlugs = tools
    .filter((tool) => tool.availability === 'missing')
    .map((tool) => tool.slug)

  const defaultSelectedToolSlug =
    step.recommendedToolSlug && availableToolSlugs.includes(step.recommendedToolSlug)
      ? step.recommendedToolSlug
      : availableToolSlugs[0] ?? null

  return {
    stepKey: input.stepKey,
    tools,
    availableToolSlugs,
    missingToolSlugs,
    defaultSelectedToolSlug
  }
}
