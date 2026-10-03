export type ToolDeploymentKind = 'platform_builtin' | 'external_service'

export function normalizeToolDeploymentKind(kind?: string | null): ToolDeploymentKind {
  return kind === 'platform_builtin' ? 'platform_builtin' : 'external_service'
}

export function toolDeploymentLabelKey(kind?: string | null):
  | 'platformBuiltin'
  | 'externalService' {
  return normalizeToolDeploymentKind(kind) === 'platform_builtin'
    ? 'platformBuiltin'
    : 'externalService'
}
