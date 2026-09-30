import type { Tool, ToolSchema } from '@/types/models'
import { flattenToolInputSchema } from './detail-schema'
import {
  resolveStandardInputFileFieldBindings,
  resolveToolPackageParameterSchema,
  resolveToolStandardInputSlots,
  type StandardArtifactInputSlot,
} from './standard-artifact-inputs'

export interface ToolRunInputSurface {
  schema?: ToolSchema
  flattenedSchema?: ToolSchema
  standardInputSlots: StandardArtifactInputSlot[]
  standardInputFileFieldBindings: Record<string, string>
  showStandardArtifactInputs: boolean
  usesConcreteStandardInputFields: boolean
}

function resolveContractInputSchema(tool?: Tool | null): ToolSchema | undefined {
  const schema = tool?.contract?.schema?.input
  return schema?.type === 'object' && schema.properties && typeof schema.properties === 'object'
    ? schema
    : undefined
}

function resolveLegacyInputSchema(tool?: Tool | null): ToolSchema | undefined {
  const config = tool?.current_version?.config
  if (config && typeof config === 'object' && 'input_schema' in config) {
    const schema = config.input_schema as ToolSchema
    return schema?.properties && Object.keys(schema.properties).length > 0 ? schema : undefined
  }
  return undefined
}

function concreteFieldsCoverAllStandardInputs(
  slots: readonly StandardArtifactInputSlot[],
  fieldBindings: Record<string, string>,
): boolean {
  return slots.length > 0 && slots.every(slot => Boolean(fieldBindings[slot.name]))
}

export function resolveToolRunInputSurface(tool?: Tool | null): ToolRunInputSurface {
  const standardInputSlots = resolveToolStandardInputSlots(tool)
  const standardParameterSchema = resolveToolPackageParameterSchema(tool) ?? undefined
  const inputSchema = resolveContractInputSchema(tool) ?? resolveLegacyInputSchema(tool)
  const flattenedInputSchema = flattenToolInputSchema(inputSchema)
  const legacyStandardFieldBindings = resolveStandardInputFileFieldBindings({
    slots: standardInputSlots,
    flattenedSchema: flattenedInputSchema,
  })
  const usesConcreteStandardInputFields = concreteFieldsCoverAllStandardInputs(
    standardInputSlots,
    legacyStandardFieldBindings,
  )
  const schema = usesConcreteStandardInputFields
    ? inputSchema
    : standardParameterSchema ?? inputSchema

  return {
    schema,
    flattenedSchema: flattenToolInputSchema(schema),
    standardInputSlots,
    standardInputFileFieldBindings: usesConcreteStandardInputFields
      ? legacyStandardFieldBindings
      : {},
    showStandardArtifactInputs: standardInputSlots.length > 0 && !usesConcreteStandardInputFields,
    usesConcreteStandardInputFields,
  }
}
