import type { Tool, ToolCreateParams } from '@/types/models'
import {
  keyValueEntriesToRecord,
  normalizeStringList,
  recordToKeyValueEntries,
  stringListForConfig,
  type KeyValueEntry,
} from '@/utils/tool-config-editors'
import {
  buildAgentCapabilityConfig,
  createAgentCapabilityInputForm,
  createAgentCapabilityOutputForm,
  isAgentCapabilityFormComplete,
  parseAgentCapabilityForm,
  type AgentCapabilityInputForm,
  type AgentCapabilityOutputForm,
} from './agent-capability'
import {
  formatToolConfigJsonText,
  isToolConfigRecord,
  serializeToolConfigForComparison,
} from './tool-config'
import { buildToolVersionConfig } from './tool-version-config'

export const DEFAULT_SSH_OUTPUT_GLOBS = [
  'output/result.json',
  'output/logs/run.log',
  'output/artifacts/**/*',
]

export interface ToolCreateFormState extends ToolCreateParams {
  tag_ids: string[]
  version: string
  changelog: string
  notes: string
  tool_type: 'remote_api' | 'docker_image' | 'python_script' | 'ssh_job'
  remote_api_registration_mode: 'self_register' | 'manual'
  remote_base_url: string
  remote_run_smoke_test: boolean
  remote_publish_on_success: boolean
  api_endpoint: string
  api_method: 'GET' | 'POST'
  docker_image: string
  python_script: string
  ssh_host: string
  ssh_port: number
  ssh_username: string
  ssh_auth_type: 'key' | 'password'
  ssh_auth_ref: string
  ssh_password_ref: string
  ssh_runner_mode: 'docker_exec' | 'shell'
  ssh_remote_base_dir: string
  ssh_container_base_dir: string
  ssh_entrypoint: string
  ssh_container_name: string
  ssh_device: string
  ssh_cleanup_remote: boolean
  ssh_strict_host_key_checking: boolean
  input_schema: string
  output_schema: string
  documentation_markdown: string
  agent_capability_enabled: boolean
  agent_capability: string
  agent_stage: string
  agent_inputs: AgentCapabilityInputForm[]
  agent_outputs: AgentCapabilityOutputForm[]
}

export interface ToolCreateEditorState {
  apiHeaderEntries: KeyValueEntry[]
  dockerCommandItems: string[]
  dockerEnvEntries: KeyValueEntry[]
  pythonArgumentItems: string[]
  sshEnvEntries: KeyValueEntry[]
  sshOutputGlobItems: string[]
}

export interface ToolConfigFormPatch {
  form: Partial<ToolCreateFormState>
  editor: Partial<ToolCreateEditorState>
  agentDefaultsText: string
}

export interface ToolEditFormPatch extends ToolConfigFormPatch {
  originalVersion: string
  originalChangelog: string
  originalNotes: string
  originalConfigSnapshot: string
}

export interface ToolTemplateFormPatchInput {
  currentToolType: ToolCreateFormState['tool_type']
  template: {
    name: string
    slug: string
    description: string
    version: string
    executor_types: string[]
    capability: string
    stage: string
    inputs: Array<Record<string, unknown>>
    outputs: Array<Record<string, unknown>>
    resource_profile: Record<string, unknown>
  }
}

export interface RemoteToolRegistrationPayload {
  base_url: string
  category_id: string
  run_smoke_test: boolean
  publish_on_success: boolean
  icon?: string
  icon_url?: string
  is_public: boolean
  timeout_sec?: number
}

export interface ToolTemplateDraftPayload {
  executor_type: ToolCreateFormState['tool_type']
  executor_config: Record<string, unknown>
  category_id?: string
  publish: boolean
}

export interface ToolVersionCreatePayload {
  version: string
  changelog?: string
  notes?: string
  config: Record<string, unknown>
  is_active: boolean
}

export type RemoteToolStageStatus = 'success' | 'warning' | 'failure'

export interface RemoteToolStageStatusDisplay {
  color: 'green' | 'orange' | 'red'
  text: string
}

export interface ToolCreateSubmissionInput {
  formState: ToolCreateFormState
  editorState: ToolCreateEditorState
  agentDefaultsText: string
  isEdit: boolean
  originalVersion: string
  originalChangelog: string
  originalNotes: string
  originalConfigSnapshot: string
}

export interface ToolCreateSubmissionResult {
  data: ToolCreateParams & { initial_version?: unknown }
  config: Record<string, unknown>
  versionConfigChanged: boolean
  agentCapabilityComplete: boolean
}

export interface ToolCreateSubmissionBlockerInput {
  submission: Pick<ToolCreateSubmissionResult, 'agentCapabilityComplete' | 'versionConfigChanged'>
  version: string
  originalVersion: string
}

export function createToolCreateFormState(): ToolCreateFormState {
  return {
    name: '',
    slug: '',
    description: '',
    category_id: '',
    icon: '',
    icon_url: '',
    is_public: true,
    gpu_required: false,
    gpu_memory_mb: undefined,
    timeout_sec: 3600,
    tag_ids: [],
    version: '1.0.0',
    changelog: '',
    notes: '',
    tool_type: 'remote_api',
    remote_api_registration_mode: 'self_register',
    remote_base_url: '',
    remote_run_smoke_test: true,
    remote_publish_on_success: false,
    api_endpoint: '',
    api_method: 'POST',
    docker_image: '',
    python_script: '',
    ssh_host: '',
    ssh_port: 22,
    ssh_username: '',
    ssh_auth_type: 'key',
    ssh_auth_ref: '',
    ssh_password_ref: '',
    ssh_runner_mode: 'docker_exec',
    ssh_remote_base_dir: '',
    ssh_container_base_dir: '',
    ssh_entrypoint: '',
    ssh_container_name: '',
    ssh_device: '',
    ssh_cleanup_remote: true,
    ssh_strict_host_key_checking: true,
    input_schema: '{}',
    output_schema: '{}',
    documentation_markdown: '',
    agent_capability_enabled: false,
    agent_capability: 'molecule_generation',
    agent_stage: 'molecule_generation',
    agent_inputs: [],
    agent_outputs: [],
  }
}

export function createToolCreateEditorState(): ToolCreateEditorState {
  return {
    apiHeaderEntries: [],
    dockerCommandItems: [],
    dockerEnvEntries: [],
    pythonArgumentItems: [],
    sshEnvEntries: [],
    sshOutputGlobItems: [...DEFAULT_SSH_OUTPUT_GLOBS],
  }
}

export function mergeToolCreateEditorStatePatch(
  current: ToolCreateEditorState,
  patch: Partial<ToolCreateEditorState>,
): ToolCreateEditorState {
  return {
    apiHeaderEntries: patch.apiHeaderEntries ?? current.apiHeaderEntries,
    dockerCommandItems: patch.dockerCommandItems ?? current.dockerCommandItems,
    dockerEnvEntries: patch.dockerEnvEntries ?? current.dockerEnvEntries,
    pythonArgumentItems: patch.pythonArgumentItems ?? current.pythonArgumentItems,
    sshEnvEntries: patch.sshEnvEntries ?? current.sshEnvEntries,
    sshOutputGlobItems: patch.sshOutputGlobItems ?? current.sshOutputGlobItems,
  }
}

export function buildRemoteToolRegistrationPayload(
  formState: ToolCreateFormState,
): RemoteToolRegistrationPayload {
  return {
    base_url: formState.remote_base_url.trim(),
    category_id: formState.category_id,
    run_smoke_test: formState.remote_run_smoke_test,
    publish_on_success: formState.remote_run_smoke_test
      ? formState.remote_publish_on_success
      : false,
    icon: formState.icon || undefined,
    icon_url: formState.icon_url || undefined,
    is_public: formState.is_public ?? true,
    timeout_sec: formState.timeout_sec,
  }
}

export function remoteToolStageStatusDisplay(
  status: RemoteToolStageStatus,
): RemoteToolStageStatusDisplay {
  if (status === 'success') {
    return { color: 'green', text: '成功' }
  }
  if (status === 'warning') {
    return { color: 'orange', text: '警告' }
  }

  return { color: 'red', text: '失败' }
}

export function buildToolAgentCapabilityEnablePatch(
  formState: ToolCreateFormState,
): Partial<ToolCreateFormState> {
  return {
    ...(formState.agent_inputs.length === 0
      ? { agent_inputs: [createAgentCapabilityInputForm()] }
      : {}),
    ...(formState.agent_outputs.length === 0
      ? { agent_outputs: [createAgentCapabilityOutputForm()] }
      : {}),
    ...(!formState.agent_stage.trim()
      ? { agent_stage: formState.agent_capability }
      : {}),
  }
}

export function formatToolCreateSubmissionErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.includes('配置键')) {
    return error.message
  }

  return 'JSON 格式错误，请检查配置'
}

export function resolveToolCreateSubmissionBlocker(
  input: ToolCreateSubmissionBlockerInput,
): string | null {
  if (!input.submission.agentCapabilityComplete) {
    return 'Agent 编排能力需要填写能力、至少一个输入和至少一个输出'
  }

  if (input.submission.versionConfigChanged && input.version === input.originalVersion) {
    return '修改版本配置时请填写新的版本号'
  }

  return null
}

export function buildTemplateExecutorConfig(
  formState: ToolCreateFormState,
  editorState: ToolCreateEditorState,
): Record<string, unknown> {
  if (formState.tool_type === 'remote_api') {
    return {
      endpoint: formState.api_endpoint,
      method: formState.api_method,
      headers: keyValueEntriesToRecord(editorState.apiHeaderEntries),
    }
  }
  if (formState.tool_type === 'docker_image') {
    return {
      image: formState.docker_image,
      command: stringListForConfig(editorState.dockerCommandItems),
      env: keyValueEntriesToRecord(editorState.dockerEnvEntries),
    }
  }
  if (formState.tool_type === 'python_script') {
    return {
      script_path: formState.python_script,
      args: stringListForConfig(editorState.pythonArgumentItems),
    }
  }

  return buildSshTemplateExecutorConfig(formState, editorState)
}

export function buildToolTemplateDraftPayload(
  formState: ToolCreateFormState,
  editorState: ToolCreateEditorState,
): ToolTemplateDraftPayload {
  return {
    category_id: formState.category_id,
    executor_type: formState.tool_type,
    executor_config: buildTemplateExecutorConfig(formState, editorState),
    publish: false,
  }
}

export function isSupportedToolType(value: string): value is ToolCreateFormState['tool_type'] {
  return ['remote_api', 'docker_image', 'python_script', 'ssh_job'].includes(value)
}

export function templateInputToForm(input: Record<string, unknown>): AgentCapabilityInputForm {
  return {
    semantic_type: String(input.semantic_type || ''),
    field: String(input.field || input.semantic_type || ''),
    accepted_extensions: Array.isArray(input.accepted_extensions)
      ? input.accepted_extensions.map(item => String(item)).join(',')
      : '',
  }
}

export function templateOutputToForm(output: Record<string, unknown>): AgentCapabilityOutputForm {
  const match = isToolConfigRecord(output.match) ? output.match : {}
  return {
    semantic_type: String(output.semantic_type || ''),
    source: output.source === 'output_data' ? 'output_data' : 'output_files',
    path: String(output.path || ''),
    match_extension: String(match.extension || ''),
    filename_contains_any: Array.isArray(match.filename_contains_any)
      ? match.filename_contains_any.map(item => String(item)).join(',')
      : '',
    required: output.required !== false,
  }
}

export function numberFromTemplate(value: unknown, fallback: number): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

export function formatToolTemplateResourceText(resourceProfile?: Record<string, unknown>): string {
  if (!resourceProfile) {
    return ''
  }

  const tier = String(resourceProfile.tier || 'unknown')
  const cpu = String(resourceProfile.cpu || '-')
  const memory = String(resourceProfile.memory_gb || '-')
  const expected = String(resourceProfile.expected_minutes || '-')
  const timeout = String(resourceProfile.timeout_minutes || '-')
  const gpu = resourceProfile.gpu_required
    ? `GPU ${resourceProfile.gpu_memory_gb || '-'}GB`
    : 'CPU'

  return `${tier} · ${gpu} · CPU ${cpu} · MEM ${memory}GB · ${expected}/${timeout} min`
}

export function buildToolTemplateFormPatch(
  input: ToolTemplateFormPatchInput,
): Pick<ToolConfigFormPatch, 'form' | 'agentDefaultsText'> {
  const preferredExecutor = input.template.executor_types.find(isSupportedToolType)
  const toolType = preferredExecutor && !input.template.executor_types.includes(input.currentToolType)
    ? preferredExecutor
    : input.currentToolType
  const resourceProfile = input.template.resource_profile
  const form: Partial<ToolCreateFormState> = {
    name: input.template.name,
    slug: input.template.slug,
    description: input.template.description,
    version: input.template.version,
    agent_capability_enabled: true,
    agent_capability: input.template.capability,
    agent_stage: input.template.stage,
    agent_inputs: input.template.inputs.map(templateInputToForm),
    agent_outputs: input.template.outputs.map(templateOutputToForm),
    gpu_required: resourceProfile.gpu_required === true,
    gpu_memory_mb: numberFromTemplate(resourceProfile.gpu_memory_gb, 0) * 1024,
    timeout_sec: Math.min(
      86400,
      Math.max(60, numberFromTemplate(resourceProfile.timeout_minutes, 60) * 60),
    ),
  }

  if (toolType !== input.currentToolType) {
    form.tool_type = toolType
  }
  if (toolType === 'remote_api') {
    form.remote_api_registration_mode = 'manual'
  }

  return { form, agentDefaultsText: '{}' }
}

export function buildToolEditFormPatch(tool: Tool): ToolEditFormPatch {
  const version = tool.current_version
  const config = isToolConfigRecord(version?.config) ? version.config : {}
  const configPatch = toolConfigToCreateFormPatch(config)
  const originalVersion = version?.version || ''
  const originalChangelog = version?.changelog || ''
  const originalNotes = version?.notes || ''

  return {
    form: {
      name: tool.name,
      slug: tool.slug,
      description: tool.description || '',
      category_id: tool.category_id || '',
      icon: tool.icon || '',
      icon_url: tool.icon_url || '',
      is_public: tool.is_public ?? true,
      gpu_required: tool.gpu_required,
      gpu_memory_mb: tool.gpu_memory_mb,
      timeout_sec: tool.timeout_sec || 3600,
      tag_ids: tool.tags?.map(tag => tag.id) || [],
      version: originalVersion,
      changelog: originalChangelog,
      notes: originalNotes,
      ...configPatch.form,
    },
    editor: configPatch.editor,
    agentDefaultsText: configPatch.agentDefaultsText,
    originalVersion,
    originalChangelog,
    originalNotes,
    originalConfigSnapshot: serializeToolConfigForComparison(config),
  }
}

export function toolConfigToCreateFormPatch(config?: Record<string, unknown>): ToolConfigFormPatch {
  if (!config || typeof config.type !== 'string') {
    return { form: {}, editor: {}, agentDefaultsText: '{}' }
  }

  const parsedCapability = parseAgentCapabilityForm(config)
  const patch: ToolConfigFormPatch = {
    form: {
      agent_capability_enabled: parsedCapability.enabled,
      agent_capability: parsedCapability.capability,
      agent_stage: parsedCapability.stage,
      agent_inputs: parsedCapability.inputs,
      agent_outputs: parsedCapability.outputs,
      input_schema: formatToolConfigJsonText(config.input_schema || {}, '{}'),
      output_schema: formatToolConfigJsonText(config.output_schema || {}, '{}'),
      documentation_markdown: typeof config.documentation_markdown === 'string'
        ? config.documentation_markdown
        : '',
    },
    editor: {},
    agentDefaultsText: parsedCapability.defaultsText,
  }

  applyExecutorConfigPatch(patch, config)
  return patch
}

export function createToolCreateSubmission(
  input: ToolCreateSubmissionInput,
): ToolCreateSubmissionResult {
  const inputSchema = parseJsonRecord(input.formState.input_schema, '{}')
  const outputSchema = parseJsonRecord(input.formState.output_schema, '{}')
  const agentDefaults = input.formState.agent_capability_enabled
    ? parseJsonRecord(input.agentDefaultsText, '{}')
    : {}

  const agentForm = {
    enabled: input.formState.agent_capability_enabled,
    capability: input.formState.agent_capability,
    stage: input.formState.agent_stage,
    inputs: input.formState.agent_inputs,
    outputs: input.formState.agent_outputs,
  }
  const agentCapabilityComplete = isAgentCapabilityFormComplete(agentForm)
  const agentCapabilityConfig = buildAgentCapabilityConfig(agentForm, agentDefaults)
  const config = buildToolVersionConfig({
    toolType: input.formState.tool_type,
    timeoutSec: input.formState.timeout_sec ?? 3600,
    gpuRequired: input.formState.gpu_required ?? false,
    gpuMemoryMb: input.formState.gpu_memory_mb,
    inputSchema,
    outputSchema,
    documentationMarkdown: input.formState.documentation_markdown,
    agentCapabilityConfig,
    apiEndpoint: input.formState.api_endpoint,
    apiMethod: input.formState.api_method,
    apiHeaders: keyValueEntriesToRecord(input.editorState.apiHeaderEntries),
    dockerImage: input.formState.docker_image,
    dockerCommand: stringListForConfig(input.editorState.dockerCommandItems),
    dockerEnv: keyValueEntriesToRecord(input.editorState.dockerEnvEntries),
    pythonScript: input.formState.python_script,
    pythonArguments: stringListForConfig(input.editorState.pythonArgumentItems),
    sshHost: input.formState.ssh_host,
    sshPort: input.formState.ssh_port,
    sshUsername: input.formState.ssh_username,
    sshAuthType: input.formState.ssh_auth_type,
    sshAuthRef: input.formState.ssh_auth_ref,
    sshPasswordRef: input.formState.ssh_password_ref,
    sshRunnerMode: input.formState.ssh_runner_mode,
    sshRemoteBaseDir: input.formState.ssh_remote_base_dir,
    sshContainerBaseDir: input.formState.ssh_container_base_dir,
    sshEntrypoint: input.formState.ssh_entrypoint,
    sshContainerName: input.formState.ssh_container_name,
    sshDevice: input.formState.ssh_device,
    sshCleanupRemote: input.formState.ssh_cleanup_remote,
    sshStrictHostKeyChecking: input.formState.ssh_strict_host_key_checking,
    sshEnv: keyValueEntriesToRecord(input.editorState.sshEnvEntries),
    sshOutputGlobs: stringListForConfig(input.editorState.sshOutputGlobItems),
  })
  const versionConfigChanged = input.isEdit && (
    input.formState.version !== input.originalVersion ||
    input.formState.changelog !== input.originalChangelog ||
    input.formState.notes !== input.originalNotes ||
    serializeToolConfigForComparison(config) !== input.originalConfigSnapshot
  )
  const data: ToolCreateParams & { initial_version?: unknown } = {
    name: input.formState.name,
    slug: input.formState.slug,
    description: input.formState.description || undefined,
    category_id: input.formState.category_id,
    icon: input.formState.icon || undefined,
    icon_url: input.formState.icon_url || undefined,
    is_public: input.formState.is_public,
    gpu_required: input.formState.gpu_required,
    gpu_memory_mb: input.formState.gpu_required ? input.formState.gpu_memory_mb : undefined,
    timeout_sec: input.formState.timeout_sec,
    tag_ids: input.formState.tag_ids.length > 0 ? input.formState.tag_ids : undefined,
  }

  if (!input.isEdit) {
    data.initial_version = buildToolVersionCreatePayload(input.formState, config)
  }

  return { data, config, versionConfigChanged, agentCapabilityComplete }
}

export function buildToolVersionCreatePayload(
  formState: ToolCreateFormState,
  config: Record<string, unknown>,
): ToolVersionCreatePayload {
  return {
    version: formState.version,
    changelog: formState.changelog || undefined,
    notes: formState.notes || undefined,
    config,
    is_active: true,
  }
}

function buildSshTemplateExecutorConfig(
  formState: ToolCreateFormState,
  editorState: ToolCreateEditorState,
): Record<string, unknown> {
  const config: Record<string, unknown> = {
    host: formState.ssh_host,
    port: formState.ssh_port,
    username: formState.ssh_username,
    auth_type: formState.ssh_auth_type,
    runner_mode: formState.ssh_runner_mode,
    remote_base_dir: formState.ssh_remote_base_dir,
    entrypoint: formState.ssh_entrypoint,
    cleanup_remote: formState.ssh_cleanup_remote,
    strict_host_key_checking: formState.ssh_strict_host_key_checking,
    env: keyValueEntriesToRecord(editorState.sshEnvEntries),
    output_globs: stringListForConfig(editorState.sshOutputGlobItems),
  }

  if (formState.ssh_auth_type === 'password') {
    config.password_ref = formState.ssh_password_ref
  } else {
    config.auth_ref = formState.ssh_auth_ref
  }
  if (formState.ssh_runner_mode === 'docker_exec') {
    config.container_name = formState.ssh_container_name
    if (formState.ssh_container_base_dir) {
      config.container_base_dir = formState.ssh_container_base_dir
    }
  }
  if (formState.ssh_device) {
    config.device = formState.ssh_device
  }
  return config
}

function applyExecutorConfigPatch(patch: ToolConfigFormPatch, config: Record<string, unknown>): void {
  if (config.type === 'remote_api') {
    patch.form.tool_type = 'remote_api'
    if (config.mode === 'remote_tool_v1') {
      patch.form.remote_api_registration_mode = 'self_register'
      patch.form.remote_base_url = String(config.base_url || '')
    } else {
      patch.form.remote_api_registration_mode = 'manual'
      patch.form.api_endpoint = String(config.endpoint || '')
      patch.form.api_method = config.method === 'GET' ? 'GET' : 'POST'
      patch.editor.apiHeaderEntries = recordToKeyValueEntries(config.headers)
    }
    return
  }

  if (config.type === 'docker_image') {
    patch.form.tool_type = 'docker_image'
    patch.form.docker_image = String(config.image || '')
    patch.editor.dockerCommandItems = normalizeStringList(config.command)
    patch.editor.dockerEnvEntries = recordToKeyValueEntries(config.env)
    return
  }

  if (config.type === 'python_script') {
    patch.form.tool_type = 'python_script'
    patch.form.python_script = String(config.script_path || config.script || '')
    patch.editor.pythonArgumentItems = normalizeStringList(config.args)
    return
  }

  if (config.type === 'ssh_job') {
    patch.form.tool_type = 'ssh_job'
    patch.form.ssh_host = String(config.host || '')
    patch.form.ssh_port = Number(config.port || 22)
    patch.form.ssh_username = String(config.username || '')
    patch.form.ssh_auth_type = config.auth_type === 'password' ? 'password' : 'key'
    patch.form.ssh_auth_ref = String(config.auth_ref || '')
    patch.form.ssh_password_ref = String(config.password_ref || '')
    patch.form.ssh_runner_mode = config.runner_mode === 'shell' ? 'shell' : 'docker_exec'
    patch.form.ssh_remote_base_dir = String(config.remote_base_dir || '')
    patch.form.ssh_container_base_dir = String(config.container_base_dir || '')
    patch.form.ssh_entrypoint = String(config.entrypoint || '')
    patch.form.ssh_container_name = String(config.container_name || '')
    patch.form.ssh_device = String(config.device || '')
    patch.form.ssh_cleanup_remote = config.cleanup_remote !== false
    patch.form.ssh_strict_host_key_checking = config.strict_host_key_checking !== false
    patch.editor.sshEnvEntries = recordToKeyValueEntries(config.env)
    patch.editor.sshOutputGlobItems = normalizeStringList(config.output_globs)
  }
}

function parseJsonRecord(value: string, fallback: string): Record<string, unknown> {
  const parsed = JSON.parse(value.trim() || fallback)
  if (!isToolConfigRecord(parsed)) {
    throw new Error('JSON value must be an object')
  }
  return parsed
}
