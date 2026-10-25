export type ToolVersionConfigType = 'docker_image' | 'python_script' | 'ssh_job' | 'k8s_job'

export interface BuildToolVersionConfigInput {
  toolType: ToolVersionConfigType
  timeoutSec: number
  gpuRequired: boolean
  gpuMemoryMb?: number
  inputSchema: Record<string, unknown>
  outputSchema: Record<string, unknown>
  documentationMarkdown?: string
  agentCapabilityConfig?: Record<string, unknown>
  dockerImage?: string
  dockerCommand?: string[]
  dockerEnv?: Record<string, string>
  pythonScript?: string
  pythonArguments?: string[]
  sshHost?: string
  sshPort?: number
  sshUsername?: string
  sshAuthType?: 'key' | 'password'
  sshAuthRef?: string
  sshPasswordRef?: string
  sshRunnerMode?: 'docker_exec' | 'shell'
  sshRemoteBaseDir?: string
  sshContainerBaseDir?: string
  sshEntrypoint?: string
  sshContainerName?: string
  sshDevice?: string
  sshCleanupRemote?: boolean
  sshStrictHostKeyChecking?: boolean
  sshEnv?: Record<string, string>
  sshOutputGlobs?: string[]
  k8sImage?: string
  k8sResourceProfile?: string
  toolPackageManifest?: Record<string, unknown>
}

export function buildToolVersionConfig(
  input: BuildToolVersionConfigInput
): Record<string, unknown> {
  const config: Record<string, unknown> = {
    type: input.toolType,
    timeout_sec: input.timeoutSec,
    gpu_required: input.gpuRequired,
    input_schema: input.inputSchema,
    output_schema: input.outputSchema
  }

  if (input.documentationMarkdown?.trim()) {
    config.documentation_markdown = input.documentationMarkdown.trim()
  }
  if (input.agentCapabilityConfig) {
    config.agent_capability = input.agentCapabilityConfig
  }
  if (input.gpuMemoryMb !== undefined) {
    config.gpu_memory_mb = input.gpuMemoryMb
  }
  if (input.toolPackageManifest) {
    config.tool_package_manifest = input.toolPackageManifest
  }

  if (input.toolType === 'docker_image') {
    config.image = input.dockerImage
    assignNonEmptyList(config, 'command', input.dockerCommand)
    assignNonEmptyRecord(config, 'env', input.dockerEnv)
  } else if (input.toolType === 'python_script') {
    config.script_path = input.pythonScript
    assignNonEmptyList(config, 'args', input.pythonArguments)
  } else if (input.toolType === 'ssh_job') {
    assignSshJobConfig(config, input)
  } else if (input.toolType === 'k8s_job') {
    config.runtime = { image: input.k8sImage }
    config.resource_profile = input.k8sResourceProfile
  }

  return config
}

function assignSshJobConfig(
  config: Record<string, unknown>,
  input: BuildToolVersionConfigInput
): void {
  config.host = input.sshHost
  config.port = input.sshPort
  config.username = input.sshUsername
  config.auth_type = input.sshAuthType

  if (input.sshAuthType === 'password') {
    config.password_ref = input.sshPasswordRef
  } else {
    config.auth_ref = input.sshAuthRef
  }

  config.runner_mode = input.sshRunnerMode
  config.remote_base_dir = input.sshRemoteBaseDir
  config.entrypoint = input.sshEntrypoint
  config.cleanup_remote = input.sshCleanupRemote
  config.strict_host_key_checking = input.sshStrictHostKeyChecking

  if (input.sshRunnerMode === 'docker_exec') {
    config.container_name = input.sshContainerName
    if (input.sshContainerBaseDir) {
      config.container_base_dir = input.sshContainerBaseDir
    }
  }

  if (input.sshDevice) {
    config.device = input.sshDevice
  }

  assignNonEmptyRecord(config, 'env', input.sshEnv)
  assignNonEmptyList(config, 'output_globs', input.sshOutputGlobs)
}

function assignNonEmptyRecord(
  target: Record<string, unknown>,
  key: string,
  value: Record<string, string> | undefined
): void {
  if (value && Object.keys(value).length > 0) {
    target[key] = value
  }
}

function assignNonEmptyList(
  target: Record<string, unknown>,
  key: string,
  value: string[] | undefined
): void {
  if (value && value.length > 0) {
    target[key] = value
  }
}
