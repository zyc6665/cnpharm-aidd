import { parseFragmentMolecule } from '@/domain/molecules/fragment-graph'

/**
 * 从 PDB / 配体文本里取口袋的几何中心与包围盒。
 *
 * 口袋预测的产物有两种常见形态：
 * - `pocket0.pdb`：用 `UNL` / `UNK` 伪原子标出**口袋空间**（体素点），最能代表口袋位置；
 * - `protein_pocket_residues.pdb`：口袋残基的真实原子，取 CA 或全部重原子也能定位。
 * 前者优先，后者兜底——两者都有时不要混算，混算会把中心拉向残基多的一侧。
 *
 * 此外还支持：
 * - 从蛋白 PDB 里的非溶剂 `HETATM` 共晶配体提取中心坐标；
 * - 从用户上传的参考配体（`.sdf` / `.mol` / `.mol2` / `.pdb`）解析几何中心。
 */
export interface Point3 {
  x: number
  y: number
  z: number
}

export interface PocketGeometry {
  center: Point3
  boxSize: Point3
  pointCount: number
  source: 'unl' | 'ca' | 'atoms' | 'hetatm' | 'ligand'
}

interface RawAtom {
  record: string
  residueName: string
  atomName: string
  element: string
  x: number
  y: number
  z: number
}

const POCKET_MARKERS = new Set(['UNL', 'UNK'])
const SOLVENT_RESIDUES = new Set(['HOH', 'WAT', 'DOD', 'TIP', 'TP3'])

function parseAtoms(pdbText: string): RawAtom[] {
  const atoms: RawAtom[] = []
  for (const line of pdbText.split(/\r?\n/)) {
    const record = line.slice(0, 6).trim()
    if (record !== 'ATOM' && record !== 'HETATM') continue
    const x = Number.parseFloat(line.slice(30, 38))
    const y = Number.parseFloat(line.slice(38, 46))
    const z = Number.parseFloat(line.slice(46, 54))
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) continue
    atoms.push({
      record,
      residueName: line.slice(17, 20).trim().toUpperCase(),
      atomName: line.slice(12, 16).trim().toUpperCase(),
      element: line.slice(76, 78).trim().toUpperCase(),
      x,
      y,
      z
    })
  }
  return atoms
}

function geometryOf(points: Point3[], source: PocketGeometry['source']): PocketGeometry {
  const sum = { x: 0, y: 0, z: 0 }
  const min = { x: Number.POSITIVE_INFINITY, y: Number.POSITIVE_INFINITY, z: Number.POSITIVE_INFINITY }
  const max = { x: Number.NEGATIVE_INFINITY, y: Number.NEGATIVE_INFINITY, z: Number.NEGATIVE_INFINITY }
  for (const point of points) {
    sum.x += point.x
    sum.y += point.y
    sum.z += point.z
    min.x = Math.min(min.x, point.x)
    min.y = Math.min(min.y, point.y)
    min.z = Math.min(min.z, point.z)
    max.x = Math.max(max.x, point.x)
    max.y = Math.max(max.y, point.y)
    max.z = Math.max(max.z, point.z)
  }
  const count = points.length
  return {
    center: { x: sum.x / count, y: sum.y / count, z: sum.z / count },
    boxSize: { x: max.x - min.x, y: max.y - min.y, z: max.z - min.z },
    pointCount: count,
    source
  }
}

export function parsePocketGeometry(pdbText: string): PocketGeometry | null {
  const atoms = parseAtoms(pdbText)
  if (!atoms.length) return null

  const markers = atoms.filter((atom) => POCKET_MARKERS.has(atom.residueName))
  if (markers.length) return geometryOf(markers, 'unl')

  const ca = atoms.filter((atom) => atom.atomName === 'CA')
  if (ca.length) return geometryOf(ca, 'ca')

  return geometryOf(atoms, 'atoms')
}

export function extractProteinHetatmPocketGeometry(pdbText: string): PocketGeometry | null {
  const heavyHetatm = parseAtoms(pdbText).filter((atom) => {
    if (atom.record !== 'HETATM') return false
    if (SOLVENT_RESIDUES.has(atom.residueName)) return false
    if (atom.element === 'H' || atom.atomName.startsWith('H')) return false
    return true
  })
  if (heavyHetatm.length < 2) return null
  return geometryOf(heavyHetatm, 'hetatm')
}

export function parseReferenceLigandGeometry(rawText: string, filename: string): PocketGeometry | null {
  const molecule = parseFragmentMolecule(rawText, filename)
  if (!molecule || molecule.atoms.length === 0) return null
  const heavy = molecule.atoms.filter((atom) => atom.element.toUpperCase() !== 'H')
  const points = heavy.length > 0 ? heavy : molecule.atoms
  return geometryOf(points, 'ligand')
}
