export type WorkflowResourceScalar = string | number | boolean

export interface WorkflowResourceProfileFormatOptions {
  includeTiming?: boolean
}

export function formatWorkflowResourceProfileLabel(
  resourceProfile: Record<string, unknown> | undefined,
  options: WorkflowResourceProfileFormatOptions = {},
): string {
  if (!resourceProfile) {
    return ''
  }

  const segments: string[] = []
  const tier = readWorkflowResourceText(resourceProfile.tier)
  const cpu = readWorkflowResourceScalar(resourceProfile.cpu)
  const memoryGb = readWorkflowResourceScalar(resourceProfile.memory_gb)
  const gpuRequired = readWorkflowResourceBoolean(resourceProfile.gpu_required)
  const gpuMemoryGb = readWorkflowResourceScalar(resourceProfile.gpu_memory_gb)

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
  if (options.includeTiming !== false) {
    const expectedMinutes = readWorkflowResourceScalar(resourceProfile.expected_minutes)
    const timeoutMinutes = readWorkflowResourceScalar(resourceProfile.timeout_minutes)
    if (expectedMinutes !== undefined) {
      segments.push(`ETA ${expectedMinutes}m`)
    }
    if (timeoutMinutes !== undefined) {
      segments.push(`Timeout ${timeoutMinutes}m`)
    }
  }

  return segments.join(' · ')
}

export function readWorkflowResourceText(value: unknown): string | undefined {
  const scalar = readWorkflowResourceScalar(value)
  return scalar === undefined ? undefined : String(scalar)
}

export function readWorkflowResourceScalar(value: unknown): WorkflowResourceScalar | undefined {
  if (value === undefined || value === null || value === '') {
    return undefined
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return value
  }
  return String(value)
}

export function readWorkflowResourceBoolean(value: unknown): boolean | undefined {
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
