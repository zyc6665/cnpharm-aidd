import type { DesignTableRow } from '@/types/design'
import { buildVisualizationResultItems } from '@/domain/tasks'
import type { VisualizationSceneEntry } from '@/domain/tasks'
import type { Task } from '@/types/models'
import { fetchProtectedFileText } from '@/utils/protected-file-access'
import { splitSdfRecords } from '@/domain/tasks/sdf-result'
import { readSdfRecordSmiles } from '@/domain/molecules/molecule-export'

export interface GenerationViewerMatch {
  entry: VisualizationSceneEntry
  sdfRecordIndex: number
  sdfRecordScoped: boolean
  sdfText: string
}

export async function findGenerationRowStructure(task: Task, row: DesignTableRow, rows: readonly DesignTableRow[]): Promise<GenerationViewerMatch | null> {
  const candidates = buildVisualizationResultItems(task).filter(item => item.kind === 'structure' && item.entry?.format === 'sdf' && item.entry.role === 'ligand')
  const smiles = String(row.smiles ?? '').trim()
  const siblingSmiles = rows.filter(candidate => candidate !== row).map(candidate => String(candidate.smiles ?? '').trim()).filter(Boolean)
  for (const item of candidates) {
    const entry = item.entry!
    const records = splitSdfRecords(await fetchProtectedFileText(entry.url))
    const id = String(row.molecule_id ?? row.id ?? '').trim()
    if (id) {
      const matches = records.map((record, index) => ({ record, index })).filter(({ record }) => record.match(/^>\s*<[^>]*(?:molecule[_ -]?id|candidate[_ -]?id)[^>]*>\s*\r?\n([^\r\n]+)/im)?.[1]?.trim() === id)
      if (matches.length === 1) return { entry, sdfRecordIndex: matches[0]!.index, sdfRecordScoped: true, sdfText: matches[0]!.record }
    }
    if (smiles && !siblingSmiles.includes(smiles)) {
      const matches = records.map((record, index) => ({ record, index })).filter(({ record }) => readSdfRecordSmiles(record) === smiles)
      if (matches.length === 1) return { entry, sdfRecordIndex: matches[0]!.index, sdfRecordScoped: true, sdfText: matches[0]!.record }
    }
  }
  return null
}
