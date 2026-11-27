import {
  exportSelectedFragmentSdf,
  parseFragmentMolecule,
  type FragmentMolecule
} from './fragment-graph'

export interface PreparedLigandUpload {
  uploadFile: File
  atomCount: number | null
  molecule: FragmentMolecule | null
}

/**
 * 解析配体 / 片段文件（.sdf / .sd / .mol / .mol2 / .pdb），并按需标准化为 SDF。
 *
 * - `.mol`（V2000 / V3000）会直接包裹为单条 `.sdf` 记录；
 * - `convertNonSdfToSdf=true` 时，`.mol2` / `.pdb` 若解析成功且不超过 999 原子，
 *   同样转换为单分子 `.sdf`（适配仅接受 SDF 的 `--ref_ligand` 等下游入口）。
 */
export async function parseAndNormalizeLigandUpload(
  file: File,
  text: string,
  options: { convertNonSdfToSdf?: boolean } = {}
): Promise<PreparedLigandUpload | null> {
  const extension = file.name.split('.').pop()?.toLowerCase()
  const lines = text.split(/\r?\n/)
  let atomCount: number | null = null
  let resolvedUpload: File | null = null

  if (extension === 'pdb') {
    const count = lines.filter(line => /^(ATOM|HETATM)/.test(line)).length
    if (count <= 0) return null
    atomCount = count
    resolvedUpload = file
  } else if (extension === 'mol2') {
    if (!/@<TRIPOS>MOLECULE/i.test(text)) return null
    const atomIndex = lines.findIndex(line => line.trim().toUpperCase() === '@<TRIPOS>ATOM')
    const nextSection =
      atomIndex >= 0
        ? lines.slice(atomIndex + 1).findIndex(line => line.trim().startsWith('@<TRIPOS>'))
        : -1
    if (atomIndex >= 0) {
      const slice =
        nextSection >= 0
          ? lines.slice(atomIndex + 1, atomIndex + 1 + nextSection)
          : lines.slice(atomIndex + 1)
      const count = slice.filter(line => line.trim().length > 0).length
      if (count > 0) atomCount = count
    }
    resolvedUpload = file
  } else {
    const countsLine = lines[3] ?? ''
    const count = /V2000\s*$/.test(countsLine) ? Number(countsLine.slice(0, 3)) : 0
    if (Number.isInteger(count) && count > 0) atomCount = count
    if ((extension === 'sdf' || extension === 'sd') && lines.some(line => line.trim() === '$$$$')) {
      resolvedUpload = file
    } else if (
      extension === 'mol' &&
      /V(?:2000|3000)\s*$/.test(countsLine) &&
      /(?:^|\n)M  END\s*$/.test(text)
    ) {
      resolvedUpload = new File([`${text.trimEnd()}\n$$$$\n`], file.name.replace(/\.mol$/i, '.sdf'), {
        type: 'chemical/x-mdl-sdfile'
      })
    } else {
      return null
    }
  }

  const molecule = parseFragmentMolecule(text, file.name)
  if (molecule && atomCount === null) {
    atomCount = molecule.atoms.length
  }

  if (
    options.convertNonSdfToSdf &&
    (extension === 'mol2' || extension === 'pdb') &&
    molecule &&
    molecule.atoms.length > 0 &&
    molecule.atoms.length <= 999
  ) {
    const converted = exportSelectedFragmentSdf(
      molecule,
      molecule.atoms.map(atom => atom.index),
      file.name
    )
    const stem = file.name.replace(/\.(mol2|pdb)$/i, '') || 'ligand'
    resolvedUpload = new File([await converted.text()], `${stem}.sdf`, {
      type: 'chemical/x-mdl-sdfile'
    })
  }

  return {
    uploadFile: resolvedUpload,
    atomCount,
    molecule
  }
}
