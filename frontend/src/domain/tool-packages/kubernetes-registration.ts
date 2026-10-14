import type {
  KubernetesToolVersionSmokeInput,
  KubernetesToolVersionSummary,
  KubernetesRegistrationOptions,
  KubernetesRegistrationVariant
} from '@/types/tool-packages'

export function canRegisterKubernetesPackage(
  options: KubernetesRegistrationOptions | null | undefined
): boolean {
  return Boolean(
    options?.kubernetes_supported &&
    Boolean(options.image) &&
    isSha256Digest(options.image_digest) &&
    options.variants.length > 0 &&
    options.resource_profiles.length > 0
  )
}

export function getKubernetesRegistrationVariants(
  options: KubernetesRegistrationOptions | null | undefined
): KubernetesRegistrationVariant[] {
  return canRegisterKubernetesPackage(options) ? options!.variants : []
}

export function createDefaultKubernetesToolVersion(
  packageVersion: string,
  variantName: string
): string {
  const suffix = `-k8s-${variantName}`
  const versionPrefix = packageVersion.slice(0, Math.max(1, 50 - suffix.length))
  return `${versionPrefix}${suffix}`.slice(0, 50)
}

export function canSmokeKubernetesToolVersion(
  version: KubernetesToolVersionSummary
): boolean {
  return version.executor_type === 'k8s_job' && !version.is_active && !version.deprecated
}

export function canPromoteKubernetesToolVersion(
  version: KubernetesToolVersionSummary,
  currentVersionId: string | null | undefined
): boolean {
  if (version.id === currentVersionId || version.deprecated) return false
  if (version.is_active) return true
  return version.executor_type === 'k8s_job' && version.smoke_status === 'SUCCESS'
}

export function parseKubernetesSmokeInput(
  value: string
): KubernetesToolVersionSmokeInput | null {
  try {
    const parsed: unknown = JSON.parse(value)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return null
    return parsed as KubernetesToolVersionSmokeInput
  } catch {
    return null
  }
}

function isSha256Digest(value: string | null | undefined): boolean {
  return typeof value === 'string' && /^sha256:[a-fA-F0-9]{64}$/.test(value)
}
