import { describe, expect, it } from 'vitest'
import {
  buildDefaultValues,
  normalizeParameters,
  validateParameters
} from '@/domain/tools/parameterSchema'
import type { ToolSchema } from '@/types/models'

const schema: ToolSchema = {
  type: 'object',
  required: ['sequence', 'device'],
  properties: {
    sequence: { type: 'string', minLength: 4, maxLength: 20 },
    device: { type: 'string', enum: ['auto', 'cpu', 'gpu'], default: 'auto' },
    sampling_steps: { type: 'integer', minimum: 10, maximum: 100, default: 50 },
    deduplicate: { type: 'boolean', default: true }
  }
}

describe('parameterSchema helpers', () => {
  it('builds defaults and skips omitted fields', () => {
    expect(buildDefaultValues(schema, { omit: ['sequence'] })).toEqual({
      device: 'auto',
      sampling_steps: 50,
      deduplicate: true
    })
  })

  it('validates required, range, enum and length', () => {
    expect(validateParameters(schema, {})).toContain('sequence:required')
    expect(validateParameters(schema, { sequence: 'MK', device: 'auto' })).toContain('sequence:too-short')
    expect(validateParameters(schema, { sequence: 'MKTA', device: 'auto', sampling_steps: 5 })).toContain(
      'sampling_steps:below-minimum'
    )
    expect(validateParameters(schema, { sequence: 'MKTA', device: 'bad' })).toContain(
      'device:invalid-option'
    )
    expect(validateParameters(schema, { sequence: 'MKTA', device: 'auto', sampling_steps: 50 })).toEqual([])
  })

  it('normalizes values and drops empty fields', () => {
    expect(
      normalizeParameters(schema, {
        sequence: '  MKTA  ',
        device: 'auto',
        sampling_steps: 50,
        deduplicate: true
      })
    ).toEqual({ sequence: 'MKTA', device: 'auto', sampling_steps: 50, deduplicate: true })
    expect(normalizeParameters(schema, { sequence: '   ', sampling_steps: undefined })).toEqual({})
  })
})
