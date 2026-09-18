import { describe, expect, it } from 'vitest'
import { formatWorkflowResourceProfileLabel } from './resource-profile'

describe('formatWorkflowResourceProfileLabel', () => {
  it('formats base resources and optional timing fields consistently', () => {
    expect(formatWorkflowResourceProfileLabel({
      tier: 'medium',
      cpu: 8,
      memory_gb: 16,
      gpu_required: false,
      expected_minutes: 30,
      timeout_minutes: 180,
    })).toBe('medium · CPU 8 · MEM 16GB · ETA 30m · Timeout 180m')
  })

  it('can omit timing fields and normalizes string booleans', () => {
    expect(formatWorkflowResourceProfileLabel({
      tier: 'light',
      cpu: 2,
      memory_gb: 4,
      gpu_required: 'false',
      expected_minutes: 10,
    }, { includeTiming: false })).toBe('light · CPU 2 · MEM 4GB')
  })
})
