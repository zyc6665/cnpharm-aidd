import type { TypedArtifact } from '@/types/artifacts'
import type { ArtifactFile, Tool, ToolContract, ToolSchema } from '@/types/models'
import {
  deriveArtifactSlotsFromToolContract,
  type ArtifactInputSlot,
} from '@/workflow/contract-bindings'
import {
  isWorkflowSemanticType,
  normalizeWorkflowSemanticType,
} from '@/workflow/semantic-types'
import { isFileSchemaProperty, type UploadedToolFile } from './detail-schema'

export type StandardArtifactInputSlot = ArtifactInputSlot

export interface StandardInputFileFieldProjection {
  inputBindings: Record<string, string>
  boundFieldKeys: string[]
}

export interface StandardInputUploadFieldProjection {
  standardInputUploads: Record<string, string>
  boundFieldKeys: string[]
}

type UnknownRecord = Record<string, unknown>

const STANDARD_TYPE_FILE_FIELD_TOKENS: Record<string, readonly string[]> = {
  'protein_structure@1': ['protein_pdb', 'receptor_pdb', 'protein', 'receptor', 'structure_file'],
  'binding_pocket@1': ['pocket_pdb', 'binding_pocket', 'pocket', 'pocket_file'],
  'ligand_structure@1': ['ligand_pdb', 'ligand_sdf', 'ligand', 'structure_file'],
  'molecule_table@1': ['molecules', 'molecule_table', 'smiles_csv', 'ranking_csv', 'table_file'],
  'run_report@1': ['report_json', 'report', 'run_report'],
}

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

function normalizeFieldToken(value: unknown): string {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

function candidateFieldTokens(key: string, prop: { _originalKey?: string }): string[] {
  return Array.from(
    new Set(
      [key, key.split('.').pop(), prop._originalKey]
        .map(normalizeFieldToken)
        .filter(Boolean)
    )
  )
}

function standardTypeFileFieldTokens(slot: StandardArtifactInputSlot): string[] {
  const standardBase = normalizeFieldToken(String(slot.type).split('@')[0])
  return Array.from(
    new Set(
      [slot.name, standardBase, ...(STANDARD_TYPE_FILE_FIELD_TOKENS[slot.type] ?? [])]
        .map(normalizeFieldToken)
        .filter(Boolean)
    )
  )
}

function scoreStandardInputFileField(
  slot: StandardArtifactInputSlot,
  key: string,
  prop: { _originalKey?: string }
): number {
  const fieldTokens = candidateFieldTokens(key, prop)
  const slotName = normalizeFieldToken(slot.name)
  const standardTokens = standardTypeFileFieldTokens(slot)

  if (fieldTokens.includes(slotName)) {
    return 100
  }
  if (fieldTokens.some(field => field.includes(slotName))) {
    return 90
  }
  if (standardTokens.some(token => fieldTokens.includes(token))) {
    return 80
  }
  if (standardTokens.some(token => fieldTokens.some(field => field.includes(token)))) {
    return 70
  }
  return 0
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

export function resolveStandardInputFileFieldBindings(input: {
  slots: readonly StandardArtifactInputSlot[]
  flattenedSchema?: ToolSchema | null
}): Record<string, string> {
  const properties = input.flattenedSchema?.properties
  if (!properties) {
    return {}
  }

  const bindings: Record<string, string> = {}
  const usedFieldKeys = new Set<string>()

  for (const slot of input.slots) {
    let bestMatch: { key: string; score: number } | undefined
    for (const [key, prop] of Object.entries(properties)) {
      if (usedFieldKeys.has(key) || !isFileSchemaProperty(prop)) {
        continue
      }

      const score = scoreStandardInputFileField(slot, key, prop)
      if (score > (bestMatch?.score ?? 0)) {
        bestMatch = { key, score }
      }
    }

    if (bestMatch) {
      bindings[slot.name] = bestMatch.key
      usedFieldKeys.add(bestMatch.key)
    }
  }

  return bindings
}

export function buildStandardInputBindingsFromFileFields(input: {
  slots: readonly StandardArtifactInputSlot[]
  fileFieldBindings: Record<string, string>
  selectedArtifacts: Record<string, ArtifactFile | null | undefined>
}): StandardInputFileFieldProjection {
  const inputBindings: Record<string, string> = {}
  const boundFieldKeys = new Set<string>()

  for (const slot of input.slots) {
    const fieldKey = input.fileFieldBindings[slot.name]
    const versionId = fieldKey ? input.selectedArtifacts[fieldKey]?.artifact_version_id?.trim() : ''
    if (!fieldKey || !versionId) {
      continue
    }

    inputBindings[slot.name] = versionId
    boundFieldKeys.add(fieldKey)
  }

  return { inputBindings, boundFieldKeys: Array.from(boundFieldKeys) }
}

export function buildStandardInputUploadsFromFileFields(input: {
  slots: readonly StandardArtifactInputSlot[]
  fileFieldBindings: Record<string, string>
  uploadedFiles: Record<string, UploadedToolFile | undefined>
  selectedArtifacts: Record<string, ArtifactFile | null | undefined>
  inputBindings: Record<string, string | null | undefined>
}): StandardInputUploadFieldProjection {
  const standardInputUploads: Record<string, string> = {}
  const boundFieldKeys = new Set<string>()

  for (const slot of input.slots) {
    if (input.inputBindings[slot.name]?.trim()) {
      continue
    }

    const fieldKey = input.fileFieldBindings[slot.name]
    if (!fieldKey) {
      continue
    }

    const fileId =
      input.selectedArtifacts[fieldKey]?.id?.trim() || input.uploadedFiles[fieldKey]?.fileId?.trim()
    if (!fileId) {
      continue
    }

    standardInputUploads[slot.name] = fileId
    boundFieldKeys.add(fieldKey)
  }

  return { standardInputUploads, boundFieldKeys: Array.from(boundFieldKeys) }
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
