/**
 * 从 PDB 文本里取口袋的几何中心与包围盒。
 *
 * 口袋预测的产物有两种常见形态：
 * - `pocket0.pdb`：用 `UNL` / `UNK` 伪原子标出**口袋空间**（体素点），最能代表口袋位置；
 * - `protein_pocket_residues.pdb`：口袋残基的真实原子，取 CA 或全部重原子也能定位。
 * 前者优先，后者兜底——两者都有时不要混算，混算会把中心拉向残基多的一侧。
 *
 * 这里是纯展示/参数推导用：真正的打分与口袋定义在后端，
 * 前端只负责把「用户上传的口袋文件」变成 `center_x/y/z` 与 `pocket_radius`。
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
  source: 'unl' | 'ca' | 'atoms'
}

interface RawAtom {
  residueName: string
  atomName: string
  x: number
  y: number
  z: number
}

const POCKET_MARKERS = new Set(['UNL', 'UNK'])

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
      residueName: line.slice(17, 20).trim().toUpperCase(),
      atomName: line.slice(12, 16).trim().toUpperCase(),
      x,
      y,
      z
    })
  }
  return atoms
}

function geometryOf(points: RawAtom[], source: PocketGeometry['source']): PocketGeometry {
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

/** 口袋半径取包围盒最长边的一半，和「以口袋中心为球心」的语义对齐。 */
export function radiusOf(geometry: PocketGeometry): number {
  const longest = Math.max(geometry.boxSize.x, geometry.boxSize.y, geometry.boxSize.z)
  if (!Number.isFinite(longest) || longest <= 0) return 0
  return Number((longest / 2).toFixed(1))
}
