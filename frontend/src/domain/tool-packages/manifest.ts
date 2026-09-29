import type { ToolPackage } from '@/types/tool-packages'

export interface ToolPackageGuidedDraft {
  slug: string
  name: string
  version: string
  description: string
  inputName: string
  inputType: string
  outputName: string
  outputType: string
  image: string
  imageDigest: string
  entrypoint: string
  python: string
  cuda: string
  fallbackUri: string
  fallbackSha256: string
  weightsUri: string
  weightsSha256: string
  cpu: number
  memoryMb: number
  accelerator: 'cpu' | 'nvidia_cuda' | 'haiguang_dcu'
}

const ZERO_SHA256 = '0'.repeat(64)

export function createToolPackageGuidedDraft(): ToolPackageGuidedDraft {
  return {
    slug: '',
    name: '',
    version: '1.0.0',
    description: '',
    inputName: 'input_artifact',
    inputType: 'protein_structure@1',
    outputName: 'output_report',
    outputType: 'run_report@1',
    image: '',
    imageDigest: `sha256:${ZERO_SHA256}`,
    entrypoint: 'python -m adapter',
    python: '3.11',
    cuda: '',
    fallbackUri: '',
    fallbackSha256: ZERO_SHA256,
    weightsUri: '',
    weightsSha256: ZERO_SHA256,
    cpu: 2,
    memoryMb: 4096,
    accelerator: 'cpu'
  }
}

export function buildToolPackageManifest(draft: ToolPackageGuidedDraft): Record<string, unknown> {
  const input = draft.inputName.trim() || 'input_artifact'
  const output = draft.outputName.trim() || 'output_report'
  const entrypoint = draft.entrypoint.trim().split(/\s+/).filter(Boolean)
  const adapterInputMethod = `adapter.inputs.${input}`
  const adapterOutputMethod = `adapter.outputs.${output}`

  return {
    api_version: 'aidd.sciminer/tool-package.v2',
    kind: 'ToolPackage',
    metadata: {
      slug: draft.slug.trim(),
      name: draft.name.trim(),
      version: draft.version.trim() || '1.0.0',
      ...(draft.description.trim() ? { description: draft.description.trim() } : {})
    },
    artifacts: {
      inputs: [{ name: input, type: draft.inputType, required: true }],
      outputs: [{ name: output, type: draft.outputType, cardinality: 'one', required: true }]
    },
    parameters_schema: { type: 'object', properties: {} },
    adapter: {
      input: [{ input, method: adapterInputMethod }],
      output: [{ output, method: adapterOutputMethod }]
    },
    exposure: { agent: true, workflow: true, direct_run: true },
    runtime: {
      python: draft.python.trim() || '3.11',
      cuda: draft.cuda.trim() || undefined,
      executor_support: ['ssh_docker_exec'],
      selection_policy: 'prefer validated hardware, then lowest resource cost',
      artifacts: {
        primary: {
          kind: 'container',
          image: draft.image.trim(),
          image_digest: draft.imageDigest.trim()
        },
        fallback: {
          kind: 'venv_pack',
          uri: draft.fallbackUri.trim(),
          sha256: draft.fallbackSha256.trim()
        }
      },
      weights: {
        manifest_uri: draft.weightsUri.trim(),
        manifest_sha256: draft.weightsSha256.trim()
      },
      cache_policy: {
        key_fields: [
          'runtime.artifacts.selected.digest_or_sha256',
          'runtime.weights.manifest_sha256'
        ],
        mutable_host_paths_forbidden: true
      }
    },
    variants: [{
      name: `${draft.accelerator}-default`,
      accelerator: draft.accelerator,
      executor_types: ['container'],
      image: draft.image.trim(),
      entrypoint: entrypoint.length ? entrypoint : ['python', '-m', 'adapter'],
      resources: { cpu: draft.cpu, memory_mb: draft.memoryMb },
      validation_status: 'unvalidated',
      hardware_validated: false
    }]
  }
}

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
