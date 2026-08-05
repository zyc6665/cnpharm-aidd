export interface AgentCapabilityInputForm {
  semantic_type: string
  field: string
  accepted_extensions: string
}

export interface AgentCapabilityOutputForm {
  semantic_type: string
  source: 'output_files' | 'output_data'
  path: string
  match_extension: string
  filename_contains_any: string
  required: boolean
}

export interface AgentCapabilityFormState {
  enabled: boolean
  capability: string
  stage: string
  inputs: AgentCapabilityInputForm[]
  outputs: AgentCapabilityOutputForm[]
}

export interface ParsedAgentCapabilityForm extends AgentCapabilityFormState {
  defaultsText: string
}

export function createAgentCapabilityInputForm(): AgentCapabilityInputForm {
  return {
    semantic_type: '',
    field: '',
    accepted_extensions: ''
  }
}

export function createAgentCapabilityOutputForm(): AgentCapabilityOutputForm {
  return {
    semantic_type: '',
    source: 'output_files',
    path: '',
    match_extension: '',
    filename_contains_any: '',
    required: true
  }
}

export function parseAgentCapabilityForm(config: Record<string, unknown>): ParsedAgentCapabilityForm {
  const rawCapability = config.agent_capability
  if (!isRecord(rawCapability)) {
    return createDisabledAgentCapabilityForm()
  }

  return {
    enabled: rawCapability.enabled === true,
    capability: String(rawCapability.capability || 'molecule_generation'),
    stage: String(rawCapability.stage || rawCapability.capability || 'molecule_generation'),
    defaultsText: formatJsonText(rawCapability.defaults || {}, '{}'),
    inputs: Array.isArray(rawCapability.inputs)
      ? rawCapability.inputs.filter(isRecord).map(item => ({
        semantic_type: String(item.semantic_type || ''),
        field: String(item.field || item.semantic_type || ''),
        accepted_extensions: joinStringList(item.accepted_extensions)
      }))
      : [],
    outputs: Array.isArray(rawCapability.outputs)
      ? rawCapability.outputs.filter(isRecord).map(item => {
        const match = isRecord(item.match) ? item.match : {}
        return {
          semantic_type: String(item.semantic_type || ''),
          source: item.source === 'output_data' ? 'output_data' : 'output_files',
          path: String(item.path || ''),
          match_extension: String(match.extension || ''),
          filename_contains_any: joinStringList(match.filename_contains_any),
          required: item.required !== false
        }
      })
      : []
  }
}

export function isAgentCapabilityFormComplete(form: AgentCapabilityFormState): boolean {
  if (!form.enabled) {
    return true
  }
  return Boolean(
    form.capability.trim() &&
      form.inputs.some(input => input.semantic_type.trim()) &&
      form.outputs.some(output => output.semantic_type.trim())
  )
}

export function buildAgentCapabilityConfig(
  form: AgentCapabilityFormState,
  defaults: Record<string, unknown>
): Record<string, unknown> | undefined {
  if (!form.enabled) {
    return undefined
  }

  const capability = form.capability.trim()
  return {
    enabled: true,
    capability,
    stage: form.stage.trim() || capability,
    inputs: form.inputs
      .filter(input => input.semantic_type.trim())
      .map(input => ({
        semantic_type: input.semantic_type.trim(),
        field: input.field.trim() || input.semantic_type.trim(),
        accepted_extensions: splitCommaList(input.accepted_extensions)
      })),
    outputs: form.outputs
      .filter(output => output.semantic_type.trim())
      .map(output => {
        const match = buildOutputMatch(output)
        return {
          semantic_type: output.semantic_type.trim(),
          source: output.source,
          path: output.path.trim() || undefined,
          required: output.required,
          match: Object.keys(match).length > 0 ? match : undefined
        }
      }),
    defaults
  }
}

function createDisabledAgentCapabilityForm(): ParsedAgentCapabilityForm {
  return {
    enabled: false,
    capability: 'molecule_generation',
    stage: 'molecule_generation',
    defaultsText: '{}',
    inputs: [],
    outputs: []
  }
}

function buildOutputMatch(output: AgentCapabilityOutputForm): Record<string, unknown> {
  const match: Record<string, unknown> = {}
  if (output.match_extension.trim()) {
    match.extension = output.match_extension.trim()
  }

  const filenameContainsAny = splitCommaList(output.filename_contains_any)
  if (filenameContainsAny.length > 0) {
    match.filename_contains_any = filenameContainsAny
  }

  return match
}

function splitCommaList(value: string): string[] {
  return value
    .split(',')
    .map(item => item.trim())
    .filter(Boolean)
}

function joinStringList(value: unknown): string {
  return Array.isArray(value) ? value.map(item => String(item)).join(',') : ''
}

function formatJsonText(value: unknown, fallback: string): string {
  if (value == null) {
    return fallback
  }

  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return fallback
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
