import type { TypedArtifact } from '@/types/artifacts'
import type { Tool, ToolContract, ToolSchema } from '@/types/models'
import {
  deriveArtifactSlotsFromToolContract,
  type ArtifactInputSlot,
} from '@/workflow/contract-bindings'
import {
  isWorkflowSemanticType,
  normalizeWorkflowSemanticType,
} from '@/workflow/semantic-types'

export type StandardArtifactInputSlot = ArtifactInputSlot

type UnknownRecord = Record<string, unknown>

function isRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function normalizeStandardType(value: unknown): StandardArtifactInputSlot['type'] | null {
  if (typeof value !== 'string' || !value.trim()) {
    return null
  }

  const normalized = normalizeWorkflowSemanticType(value.trim())
  return isWorkflowSemanticType(normalized) ? normalized : null
}

function resolveToolContract(tool?: Tool | null): ToolContract | null {
  const candidate = (tool as (Tool & { contract?: ToolContract | null }) | null | undefined)?.contract
  return candidate && typeof candidate === 'object' ? candidate : null
}

function resolveEmbeddedManifest(tool?: Tool | null): UnknownRecord | null {
  const config = tool?.current_version?.config
  if (!isRecord(config)) {
    return null
  }

  if (isRecord(config.tool_package_manifest)) {
    return config.tool_package_manifest
  }

  if (isRecord(config.tool_package) && isRecord(config.tool_package.manifest)) {
    return config.tool_package.manifest
  }

  return null
}

function resolveSlotsFromManifest(manifest: UnknownRecord | null): StandardArtifactInputSlot[] {
  if (!manifest || manifest.api_version !== 'aidd.sciminer/tool-package.v2') {
    return []
  }

  const artifacts = isRecord(manifest.artifacts) ? manifest.artifacts : null
  const inputs = Array.isArray(artifacts?.inputs) ? artifacts.inputs : []

  return inputs
    .map((slot) => {
      if (!isRecord(slot) || typeof slot.name !== 'string' || !slot.name.trim()) {
        return null
      }

      const type = normalizeStandardType(slot.type)
      if (!type) {
        return null
      }

      return {
        name: slot.name.trim(),
        type,
        required: typeof slot.required === 'boolean' ? slot.required : true,
      }
    })
    .filter((slot): slot is StandardArtifactInputSlot => slot !== null)
}

export function resolveToolStandardInputSlots(tool?: Tool | null): StandardArtifactInputSlot[] {
  const contractSlots = deriveArtifactSlotsFromToolContract(resolveToolContract(tool)).inputs
  if (contractSlots.length) {
    return [...contractSlots]
  }

  return resolveSlotsFromManifest(resolveEmbeddedManifest(tool))
}

export function resolveToolPackageParameterSchema(tool?: Tool | null): ToolSchema | null {
  const manifest = resolveEmbeddedManifest(tool)
  if (!manifest || manifest.api_version !== 'aidd.sciminer/tool-package.v2') {
    return null
  }

  const schema = manifest.parameters_schema
  if (!isRecord(schema) || schema.type !== 'object' || !isRecord(schema.properties)) {
    return null
  }

  return schema as unknown as ToolSchema
}

function artifactStandardTypes(artifact: TypedArtifact): StandardArtifactInputSlot['type'][] {
  const candidates = [
    artifact.standard_type,
    artifact.semantic_type,
    artifact.artifact_type,
  ]

  return Array.from(
    new Set(
      candidates
        .map(normalizeStandardType)
        .filter((value): value is StandardArtifactInputSlot['type'] => value !== null)
    )
  )
}

function hasAvailableLatestVersion(artifact: TypedArtifact): boolean {
  if (artifact.latest_version.status !== 'available') {
    return false
  }

  const expiresAt = artifact.latest_version.expires_at
  if (!expiresAt) {
    return true
  }

  const timestamp = Date.parse(expiresAt)
  return Number.isNaN(timestamp) || timestamp > Date.now()
}

export function filterCompatibleProjectArtifacts(
  slot: StandardArtifactInputSlot,
  artifacts: readonly TypedArtifact[]
): TypedArtifact[] {
  return artifacts.filter((artifact) => {
    return hasAvailableLatestVersion(artifact) && artifactStandardTypes(artifact).includes(slot.type)
  })
}

export function buildStandardInputBindings(
  selectedArtifacts: Record<string, TypedArtifact | null | undefined>
): Record<string, string> {
  const bindings: Record<string, string> = {}

  for (const [slotName, artifact] of Object.entries(selectedArtifacts)) {
    const versionId = artifact?.latest_version?.id
    if (versionId) {
      bindings[slotName] = versionId
    }
  }

  return bindings
}

export function getStandardInputAccept(slot: StandardArtifactInputSlot): string | undefined {
  switch (slot.type) {
    case 'protein_structure@1':
    case 'binding_pocket@1':
      return '.pdb'
    case 'ligand_structure@1':
      return '.sdf'
    case 'molecule_table@1':
      return '.csv,.json'
    default:
      return undefined
  }
}

export function missingRequiredStandardInputSlots(input: {
  slots: readonly StandardArtifactInputSlot[]
  inputBindings: Record<string, string | null | undefined>
  hasUpload: (slotName: string) => boolean
}): StandardArtifactInputSlot[] {
  return input.slots.filter((slot) => {
    return slot.required && !input.inputBindings[slot.name]?.trim() && !input.hasUpload(slot.name)
  })
}
