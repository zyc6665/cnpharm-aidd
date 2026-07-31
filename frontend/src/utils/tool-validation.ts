export interface ToolValidationBadge {
  label: string
  color: string
}

export interface ToolValidationSummary extends ToolValidationBadge {
  badges: ToolValidationBadge[]
}

type ToolVariant = {
  accelerator?: unknown
  hardware_validated?: unknown
  validation_status?: unknown
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined
}

function resolveManifest(config: Record<string, unknown>): Record<string, unknown> {
  const packageConfig = asRecord(config.tool_package)
  const manifest = asRecord(packageConfig?.manifest) ?? asRecord(config.manifest)
  return manifest ?? packageConfig ?? config
}

function variantBadge(variant: ToolVariant): ToolValidationBadge | undefined {
  const accelerator = variant.accelerator
  const isNvidia = accelerator === 'nvidia_cuda'
  const isDcu = accelerator === 'haiguang_dcu'
  const isValidated = variant.validation_status === 'validated' && variant.hardware_validated === true

  if (isDcu && (variant.validation_status === 'adapted_pending_hardware_validation' || !isValidated)) {
    return { label: '海光 DCU 待硬件验收', color: 'orange' }
  }
  if (isNvidia && isValidated) {
    return { label: 'NVIDIA 生产已验证', color: 'green' }
  }
  if (isValidated) {
    return { label: '生产已验证', color: 'green' }
  }
  if (variant.validation_status === 'unvalidated') {
    return { label: '可运行', color: 'blue' }
  }
  return undefined
}

export function getToolValidationSummary(config: unknown): ToolValidationSummary {
  const rawConfig = asRecord(config)
  if (!rawConfig) {
    return { label: '已导入', color: 'default', badges: [{ label: '已导入', color: 'default' }] }
  }

  const manifest = resolveManifest(rawConfig)
  const variants = Array.isArray(manifest.variants)
    ? manifest.variants
    : manifest.accelerator ? [manifest] : []
  const badges = variants
    .map(item => variantBadge(asRecord(item) ?? {}))
    .filter((badge): badge is ToolValidationBadge => Boolean(badge))

  if (badges.length > 0) {
    const primary = badges.find(badge => badge.color === 'green')
    if (primary) {
      return { ...primary, badges }
    }
    return { ...badges[0]!, badges }
  }

  const level = manifest.validation_level ?? manifest.validation_status
  if (level === 'production_verified' || level === 'validated') {
    return {
      label: '生产已验证',
      color: 'green',
      badges: [{ label: '生产已验证', color: 'green' }]
    }
  }
  if (level === 'runnable' || level === 'unvalidated') {
    return { label: '可运行', color: 'blue', badges: [{ label: '可运行', color: 'blue' }] }
  }
  if (level === 'adapted_pending_hardware_validation') {
    return {
      label: '待硬件验收',
      color: 'orange',
      badges: [{ label: '待硬件验收', color: 'orange' }]
    }
  }
  return { label: '已导入', color: 'default', badges: [{ label: '已导入', color: 'default' }] }
}
