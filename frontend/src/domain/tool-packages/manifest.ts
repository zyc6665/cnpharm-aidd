import type { ToolPackage } from '@/types/tool-packages'
import type { ToolSchema } from '@/types/models'
import { createEmptyParameterSchema } from '@/domain/tools/parameter-schema'

export interface ToolPackageGuidedInput {
  name: string
  title: string
  description: string
  type: string
  required: boolean
}

export interface ToolPackageGuidedOutput {
  name: string
  type: string
  cardinality: 'one' | 'many'
  required: boolean
}

export interface ToolPackageGuidedDraft {
  slug: string
  name: string
  version: string
  description: string
  inputs: ToolPackageGuidedInput[]
  outputs: ToolPackageGuidedOutput[]
  parametersSchema: ToolSchema
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
    inputs: [{ name: 'input_artifact', title: '', description: '', type: 'protein_structure@1', required: true }],
    outputs: [{ name: 'output_report', type: 'run_report@1', cardinality: 'one', required: true }],
    parametersSchema: createEmptyParameterSchema(),
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

export function createGuidedInput(): ToolPackageGuidedInput {
  return { name: '', title: '', description: '', type: 'protein_structure@1', required: true }
}

export function createGuidedOutput(): ToolPackageGuidedOutput {
  return { name: '', type: 'run_report@1', cardinality: 'one', required: true }
}

export function buildToolPackageManifest(draft: ToolPackageGuidedDraft): Record<string, unknown> {
  const inputs = draft.inputs
    .map(item => ({ ...item, name: item.name.trim() }))
    .filter(item => item.name)
  const outputs = draft.outputs
    .map(item => ({ ...item, name: item.name.trim() }))
    .filter(item => item.name)
  if (!inputs.length) inputs.push({ name: 'input_artifact', title: '', description: '', type: 'protein_structure@1', required: true })
  if (!outputs.length) outputs.push({ name: 'output_report', type: 'run_report@1', cardinality: 'one', required: true })
  const entrypoint = draft.entrypoint.trim().split(/\s+/).filter(Boolean)

  return {
    api_version: 'aidd.sciminer/tool-package',
    kind: 'ToolPackage',
    metadata: {
      slug: draft.slug.trim(),
      name: draft.name.trim(),
      version: draft.version.trim() || '1.0.0',
      ...(draft.description.trim() ? { description: draft.description.trim() } : {})
    },
    artifacts: {
      inputs: inputs.map(item => ({
        name: item.name,
        ...(item.title.trim() ? { title: item.title.trim() } : {}),
        ...(item.description.trim() ? { description: item.description.trim() } : {}),
        type: item.type,
        required: item.required,
      })),
      outputs: outputs.map(item => ({
        name: item.name,
        type: item.type,
        cardinality: item.cardinality,
        required: item.required,
      })),
    },
    parameters_schema: draft.parametersSchema,
    adapter: {
      input: inputs.map(item => ({ input: item.name, method: `adapter.inputs.${item.name}` })),
      output: outputs.map(item => ({ output: item.name, method: `adapter.outputs.${item.name}` })),
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
