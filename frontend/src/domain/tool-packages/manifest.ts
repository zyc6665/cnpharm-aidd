import type { ToolPackage } from '@/types/tool-packages'

export type ArtifactSlotKind = 'inputs' | 'outputs'

export function getToolPackageManifest(
  item: ToolPackage | null | undefined
): Record<string, unknown> | undefined {
  return item?.current_version?.manifest
}

export function formatToolPackageManifest(item: ToolPackage | null | undefined): string {
  return JSON.stringify(getToolPackageManifest(item) ?? {}, null, 2)
}

export function getToolPackageValidationErrors(item: ToolPackage | null | undefined): string[] {
  return item?.current_version?.validation_errors ?? []
}

export function getToolPackageValidationColor(status?: string): string {
  if (status === 'valid') return 'green'
  if (status === 'invalid') return 'red'
  return 'default'
}

export function getToolPackageContractSummary(item: ToolPackage): string {
  const artifacts = asRecord(item.current_version?.manifest.artifacts)
  const inputs = Array.isArray(artifacts?.inputs) ? artifacts.inputs.length : 0
  const outputs = Array.isArray(artifacts?.outputs) ? artifacts.outputs.length : 0
  return `${inputs} 输入 / ${outputs} 输出`
}

export function getToolPackageVariantSummary(item: ToolPackage): string {
  const variants = item.current_version?.manifest.variants
  if (!Array.isArray(variants)) return '无 variants'

  return variants
    .map(variant => asRecord(variant)?.accelerator)
    .filter(Boolean)
    .map(String)
    .join(' · ') || `${variants.length} variants`
}

export function getToolPackageArtifactSlots(
  item: ToolPackage | null | undefined,
  kind: ArtifactSlotKind
): Record<string, unknown>[] {
  const artifacts = asRecord(getToolPackageManifest(item)?.artifacts)
  const slots = artifacts?.[kind]
  return Array.isArray(slots)
    ? slots
        .map(slot => asRecord(slot))
        .filter((slot): slot is Record<string, unknown> => Boolean(slot))
    : []
}

export function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}
