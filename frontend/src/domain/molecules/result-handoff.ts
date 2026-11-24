import { uploadFile } from '@/api/files'
import { buildMoleculeCsv } from './molecule-export'

export interface MoleculeHandoffRow {
  smiles: string
  moleculeId?: string
}

const PLACEHOLDERS = new Set(['-', '--', 'n/a', 'na', 'null', 'none', 'undefined', 'smiles'])
const SMILES_CHARS = /^[A-Za-z0-9@+\-\[\]()#=.:\\/%$*]+$/

/** Conservative, environment-independent SMILES sanity check for handoff inputs. */
export function isValidHandoffSmiles(value: string): boolean {
  const smiles = value.trim()
  if (!smiles || PLACEHOLDERS.has(smiles.toLowerCase()) || !SMILES_CHARS.test(smiles)) return false
  if (!/[A-Za-z]/.test(smiles) || /^(?:[=#:.]|\.|.*[=#:.])$/.test(smiles)) return false
  let brackets = 0
  let parentheses = 0
  let escaped = false
  for (const char of smiles) {
    if (escaped) { escaped = false; continue }
    if (char === '\\') { escaped = true; continue }
    if (char === '[') brackets += 1
    if (char === ']') { brackets -= 1; if (brackets < 0) return false }
    if (brackets === 0) {
      if (char === '(') parentheses += 1
      if (char === ')') { parentheses -= 1; if (parentheses < 0) return false }
    }
  }
  return !escaped && brackets === 0 && parentheses === 0
}

export async function uploadMoleculeHandoff(
  rows: readonly MoleculeHandoffRow[],
  filename: string
): Promise<{ file_id: string; filename: string }> {
  if (!rows.length || rows.some(row => !isValidHandoffSmiles(row.smiles))) {
    throw new Error('Handoff requires valid SMILES for every molecule')
  }
  const withIds = rows.some(row => row.moleculeId)
  const columns = [
    { key: 'smiles', title: 'smiles' },
    ...(withIds ? [{ key: 'molecule_id', title: 'molecule_id' }] : [])
  ]
  const csvRows = rows.map(row => ({ smiles: row.smiles.trim(), molecule_id: row.moleculeId }))
  const csv = buildMoleculeCsv(columns, csvRows)
  const response = await uploadFile(new File([csv], filename, { type: 'text/csv' }))
  const fileId = response.data?.id
  if (!fileId) throw new Error('File upload did not return a file id')
  return { file_id: fileId, filename }
}
