import type { ArtifactFile, SchemaProperty, Tool, ToolSchema } from '../types/models.d.ts'
import { flattenToolInputSchema } from '../domain/tools/detail-schema.ts'
import {
  resolveStandardInputFileFieldBindings,
  type StandardArtifactInputSlot,
} from '../domain/tools/standard-artifact-inputs.ts'
import {
  resolveToolRunInputSurface,
} from '../domain/tools/tool-run-input-surface.ts'
import type { WorkflowNodeArtifactRecommendation } from './canvas-artifacts.ts'
import { normalizeWorkflowSemanticType } from './semantic-types.ts'

export interface StandardArtifactInputLike {
  name: string
  type: string
  required?: boolean
}

export interface AutoBoundArtifactCard {
  key: string
  fieldTitle: string
  sourceLabel: string
  filename: string
}

export interface WorkflowNodeRunInputLabels {
  standardArtifactDescription: (artifactType: string) => string
  upstreamNodeFallback: string
}

const DEFAULT_WORKFLOW_NODE_RUN_INPUT_LABELS: WorkflowNodeRunInputLabels = {
  standardArtifactDescription: artifactType => `Standard artifact type: ${artifactType}`,
  upstreamNodeFallback: 'Upstream node',
}

export interface ResolveRecommendedArtifactBindingsInput {
  fileFieldKeys: readonly string[]
  flattenedSchema: ToolSchema
  selectedArtifacts: Record<string, ArtifactFile | undefined>
  fileList: Record<string, readonly unknown[] | undefined>
  recommendations?: readonly WorkflowNodeArtifactRecommendation[]
}

export interface ApplyRecommendedArtifactBindingsInput extends ResolveRecommendedArtifactBindingsInput {
  formState: Record<string, unknown>
  autoBoundArtifactByField: Record<string, ArtifactFile | undefined>
}

export interface WorkflowRunFileSelectionItem {
  uid?: string
  name?: string
}

export interface ApplyManualFileSelectionInput<FileItem extends WorkflowRunFileSelectionItem> {
  fieldKey: string
  files: FileItem[]
  fileList: Record<string, FileItem[]>
  selectedArtifacts: Record<string, ArtifactFile | undefined>
  formState: Record<string, unknown>
  autoBoundArtifactByField: Record<string, ArtifactFile | undefined>
}

export interface ApplyManualArtifactSelectionInput<FileItem extends WorkflowRunFileSelectionItem> {
  fieldKey: string
  artifact: ArtifactFile | null
  fileList: Record<string, FileItem[]>
  selectedArtifacts: Record<string, ArtifactFile | undefined>
  formState: Record<string, unknown>
  autoBoundArtifactByField: Record<string, ArtifactFile | undefined>
}

export interface WorkflowNodeRunInputSurface {
  schema?: ToolSchema
  flattenedSchema: ToolSchema
  standardInputSlots: StandardArtifactInputSlot[]
  standardInputFileFieldBindings: Record<string, string>
  usesSyntheticStandardInputFields: boolean
}

export function resolveWorkflowNodeRunInputSurface(input: {
  tool?: Tool | null
  standardInputSlots?: readonly StandardArtifactInputSlot[]
  labels?: WorkflowNodeRunInputLabels
}): WorkflowNodeRunInputSurface {
  const toolSurface = resolveToolRunInputSurface(input.tool)
  const standardInputSlots = [...(input.standardInputSlots ?? toolSurface.standardInputSlots)]
  const schema = toolSurface.schema?.properties && Object.keys(toolSurface.schema.properties).length > 0
    ? toolSurface.schema
    : standardInputSlots.length > 0
      ? buildArtifactInputSchema(standardInputSlots, input.labels)
      : undefined
  const flattenedSchema = flattenToolInputSchema(schema) ?? {
    type: 'object',
    properties: {},
    required: [],
  }

  if (Object.keys(toolSurface.standardInputFileFieldBindings).length > 0) {
    return {
      schema,
      flattenedSchema,
      standardInputSlots,
      standardInputFileFieldBindings: toolSurface.standardInputFileFieldBindings,
      usesSyntheticStandardInputFields: false,
    }
  }

  const standardInputFileFieldBindings = resolveStandardInputFileFieldBindings({
    slots: standardInputSlots,
    flattenedSchema,
  })

  return {
    schema,
    flattenedSchema,
    standardInputSlots,
    standardInputFileFieldBindings,
    usesSyntheticStandardInputFields: schema !== toolSurface.schema,
  }
}

export function buildArtifactInputSchema(
  artifactInputs: readonly StandardArtifactInputLike[],
  labels: WorkflowNodeRunInputLabels = DEFAULT_WORKFLOW_NODE_RUN_INPUT_LABELS,
): ToolSchema {
  const properties: ToolSchema['properties'] = {}
  const required: string[] = []

  for (const input of artifactInputs) {
    properties[input.name] = {
      type: 'file',
      title: input.name,
      description: labels.standardArtifactDescription(input.type),
      format: 'file',
    }

    if (input.required) {
      required.push(input.name)
    }
  }

  return {
    type: 'object',
    properties,
    required,
  }
}

export function resolveRecommendedArtifactBindings(
  input: ResolveRecommendedArtifactBindingsInput,
): Record<string, ArtifactFile> {
  const bindings: Record<string, ArtifactFile> = {}
  const usedArtifactIds = new Set(
    Object.values(input.selectedArtifacts)
      .filter((artifact): artifact is ArtifactFile => Boolean(artifact))
      .map(artifact => artifact.id),
  )

  for (const fileFieldKey of input.fileFieldKeys) {
    if (input.selectedArtifacts[fileFieldKey] || input.fileList[fileFieldKey]?.length) {
      continue
    }

    const artifact = pickRecommendedArtifactForField({
      fileFieldKey,
      flattenedSchema: input.flattenedSchema,
      recommendations: input.recommendations ?? [],
      usedArtifactIds,
    })
    if (!artifact) {
      continue
    }

    bindings[fileFieldKey] = artifact
    usedArtifactIds.add(artifact.id)
  }

  return bindings
}

export function applyRecommendedArtifactBindings(
  input: ApplyRecommendedArtifactBindingsInput,
): string[] {
  const bindings = resolveRecommendedArtifactBindings(input)

  for (const [fileFieldKey, artifact] of Object.entries(bindings)) {
    input.selectedArtifacts[fileFieldKey] = artifact
    input.formState[fileFieldKey] = artifact.id
    input.autoBoundArtifactByField[fileFieldKey] = artifact
  }

  return Object.keys(bindings)
}

export function applyManualFileSelection<FileItem extends WorkflowRunFileSelectionItem>(
  input: ApplyManualFileSelectionInput<FileItem>,
): void {
  input.fileList[input.fieldKey] = input.files
  input.selectedArtifacts[input.fieldKey] = undefined
  input.autoBoundArtifactByField[input.fieldKey] = undefined
  input.formState[input.fieldKey] = input.files[0]?.uid ?? input.files[0]?.name
}

export function applyManualArtifactSelection<FileItem extends WorkflowRunFileSelectionItem>(
  input: ApplyManualArtifactSelectionInput<FileItem>,
): void {
  input.selectedArtifacts[input.fieldKey] = input.artifact ?? undefined
  input.autoBoundArtifactByField[input.fieldKey] = undefined
  input.formState[input.fieldKey] = input.artifact?.id
  if (input.artifact) {
    input.fileList[input.fieldKey] = []
  }
}

export function clearAutoBoundArtifactBindings(
  autoBoundArtifactByField: Record<string, ArtifactFile | undefined>,
): void {
  for (const key of Object.keys(autoBoundArtifactByField)) {
    delete autoBoundArtifactByField[key]
  }
}

export function buildAutoBoundArtifactCards(input: {
  autoBoundArtifactByField: Record<string, ArtifactFile | undefined>
  flattenedSchema: ToolSchema
  labels?: Pick<WorkflowNodeRunInputLabels, 'upstreamNodeFallback'>
}): AutoBoundArtifactCard[] {
  const upstreamNodeFallback = input.labels?.upstreamNodeFallback
    ?? DEFAULT_WORKFLOW_NODE_RUN_INPUT_LABELS.upstreamNodeFallback

  return Object.entries(input.autoBoundArtifactByField)
    .filter((entry): entry is [string, ArtifactFile] => Boolean(entry[1]))
    .map(([fieldKey, artifact]) => ({
      key: `${fieldKey}-${artifact.id}`,
      fieldTitle: input.flattenedSchema.properties[fieldKey]?.title ?? fieldKey,
      sourceLabel: `${artifact.tool_name || artifact.tool_slug || upstreamNodeFallback} · ${artifact.semantic_type || 'artifact'}`,
      filename: artifact.filename,
    }))
}

function pickRecommendedArtifactForField(input: {
  fileFieldKey: string
  flattenedSchema: ToolSchema
  recommendations: readonly WorkflowNodeArtifactRecommendation[]
  usedArtifactIds: Set<string>
}): ArtifactFile | null {
  const recommendations = input.recommendations
    .filter(recommendation => recommendation.artifact && !input.usedArtifactIds.has(recommendation.artifact.id))

  if (recommendations.length === 0) {
    return null
  }

  const prop = input.flattenedSchema.properties[input.fileFieldKey]
  if (!prop) {
    return null
  }

  const matchedRecommendation = recommendations.find(recommendation =>
    fieldLooksCompatibleWithSemantic(input.fileFieldKey, prop, recommendation.semanticType),
  )

  if (matchedRecommendation?.artifact) {
    return matchedRecommendation.artifact
  }

  return recommendations.length === 1 ? recommendations[0]?.artifact ?? null : null
}

function fieldLooksCompatibleWithSemantic(fieldKey: string, prop: SchemaProperty, semanticType: string) {
  const targetSemanticType = normalizeSemanticToken(semanticType)
  const directCandidates = [fieldKey, prop._originalKey]
    .filter((candidate): candidate is string => Boolean(candidate))

  if (directCandidates.some(candidate => normalizeSemanticToken(candidate) === targetSemanticType)) {
    return true
  }

  const fieldText = [fieldKey, prop._originalKey, prop.title, prop.description]
    .map(value => normalizeFieldToken(value))
    .filter(Boolean)
    .join(' ')

  if (!fieldText) {
    return false
  }

  if (targetSemanticType === 'protein_structure@1') {
    return /\b(protein|receptor)\b/.test(fieldText)
  }

  if (targetSemanticType === 'binding_pocket@1') {
    return /\b(pocket|binding)\b/.test(fieldText)
  }

  if (targetSemanticType === 'ligand_structure@1') {
    return /\b(ligand|sdf|mol2?|smiles)\b/.test(fieldText)
  }

  if (targetSemanticType === 'molecule_table@1') {
    return /\b(molecule|table|csv|smiles)\b/.test(fieldText)
  }

  if (targetSemanticType === 'run_report@1') {
    return /\b(report|metadata|json)\b/.test(fieldText)
  }

  return fieldText.includes(normalizeFieldToken(targetSemanticType))
}

function normalizeSemanticToken(value?: string | null): string {
  return String(normalizeWorkflowSemanticType(String(value ?? '').trim())).trim().toLowerCase()
}

function normalizeFieldToken(value?: string | null): string {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}
