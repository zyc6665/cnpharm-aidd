export interface FragmentAtom {
  index: number
  element: string
  x: number
  y: number
  z: number
  x2d: number
  y2d: number
  charge?: number
  isHetero: boolean
}

export interface FragmentBond {
  a: number
  b: number
  order: number
}

export interface FragmentMolecule {
  name: string
  format: 'sdf' | 'mol' | 'mol2' | 'pdb'
  atoms: FragmentAtom[]
  bonds: FragmentBond[]
  rawText: string
}

interface Graph {
  atoms: FragmentAtom[]
  bonds: FragmentBond[]
}

function makeAtom(index: number, symbol: string, coordinates: string[], charge?: number): FragmentAtom | null {
  if (!/^[a-z]{1,3}$/i.test(symbol) || coordinates.length !== 3 || coordinates.some(value => !value.trim())) return null
  const [x = NaN, y = NaN, z = NaN] = coordinates.map(Number)
  if (![x, y, z].every(Number.isFinite)) return null
  const element = symbol.charAt(0).toUpperCase() + symbol.slice(1).toLowerCase()
  return { index, element, x, y, z, x2d: 0, y2d: 0, charge, isHetero: element !== 'C' && element !== 'H' }
}

function makeBond(a: number | undefined, b: number | undefined, order: number, atomCount: number): FragmentBond | null {
  if (a === undefined || b === undefined || !Number.isInteger(a) || !Number.isInteger(b) || a === b ||
      a < 0 || b < 0 || a >= atomCount || b >= atomCount || ![1, 2, 3, 1.5].includes(order)) return null
  return { a, b, order }
}

function unfoldV3000Lines(rawLines: string[]): string[] {
  const unfolded: string[] = []
  let buffer = ''
  for (const raw of rawLines) {
    if (!/^M\s+V30\s/.test(raw)) {
      if (buffer) {
        unfolded.push(buffer)
        buffer = ''
      }
      unfolded.push(raw)
      continue
    }
    const content = raw.replace(/^M\s+V30\s+/, '').trimEnd()
    const merged = buffer ? `${buffer} ${content}` : content
    if (merged.endsWith('-') && !merged.endsWith('--')) {
      buffer = merged.slice(0, -1).trimEnd()
    } else {
      unfolded.push(`M  V30 ${merged}`)
      buffer = ''
    }
  }
  if (buffer) unfolded.push(`M  V30 ${buffer}`)
  return unfolded
}

function parseV3000Molfile(lines: string[]): Graph | null {
  const unfolded = unfoldV3000Lines(lines.slice(4))
  let inCtab = false
  let inAtom = false
  let inBond = false
  let expectedAtoms: number | null = null
  let expectedBonds: number | null = null
  const atoms: FragmentAtom[] = []
  const bonds: FragmentBond[] = []
  const atomIds = new Map<number, number>()

  for (const line of unfolded) {
    if (/^M\s+END\s*$/.test(line)) {
      if (!inCtab && atoms.length > 0 && (expectedAtoms === null || atoms.length === expectedAtoms) &&
          (expectedBonds === null || bonds.length === expectedBonds)) {
        return { atoms, bonds }
      }
      return null
    }
    if (!/^M\s+V30\s+/.test(line)) continue
    const body = line.replace(/^M\s+V30\s+/, '').trim()
    if (body === 'BEGIN CTAB') {
      inCtab = true
      continue
    }
    if (body === 'END CTAB') {
      inCtab = false
      inAtom = false
      inBond = false
      continue
    }
    if (!inCtab) continue
    if (body.startsWith('COUNTS ')) {
      const parts = body.split(/\s+/)
      const nAtoms = Number(parts[1])
      const nBonds = Number(parts[2])
      if (!Number.isInteger(nAtoms) || nAtoms < 1 || !Number.isInteger(nBonds) || nBonds < 0) return null
      expectedAtoms = nAtoms
      expectedBonds = nBonds
      continue
    }
    if (body === 'BEGIN ATOM') {
      inAtom = true
      continue
    }
    if (body === 'END ATOM') {
      inAtom = false
      continue
    }
    if (body === 'BEGIN BOND') {
      inBond = true
      continue
    }
    if (body === 'END BOND') {
      inBond = false
      continue
    }
    if (inAtom) {
      const tokens = body.split(/\s+/)
      if (tokens.length < 6) return null
      const atomId = Number(tokens[0])
      if (!Number.isSafeInteger(atomId) || atomId < 1 || atomIds.has(atomId)) return null
      let charge: number | undefined
      for (const token of tokens.slice(6)) {
        const chgMatch = /^CHG=(-?\d+)$/i.exec(token)
        if (chgMatch) {
          const parsed = Number(chgMatch[1])
          if (Number.isInteger(parsed) && parsed !== 0) charge = parsed
        }
      }
      const atom = makeAtom(atoms.length, tokens[1] ?? '', [tokens[2] ?? '', tokens[3] ?? '', tokens[4] ?? ''], charge)
      if (!atom) return null
      atomIds.set(atomId, atom.index)
      atoms.push(atom)
      continue
    }
    if (inBond) {
      const tokens = body.split(/\s+/)
      if (tokens.length < 4) return null
      const type = Number(tokens[1])
      const order = type === 4 ? 1.5 : type
      const bond = makeBond(atomIds.get(Number(tokens[2])), atomIds.get(Number(tokens[3])), order, atoms.length)
      if (!bond) return null
      bonds.push(bond)
    }
  }
  return null
}

function parseMolfile(lines: string[]): Graph | null {
  const counts = lines[3] ?? ''
  if (/V3000\s*$/.test(counts)) return parseV3000Molfile(lines)
  if (!/V2000\s*$/.test(counts)) return null
  const atomCount = Number(counts.slice(0, 3))
  const bondCount = Number(counts.slice(3, 6))
  if (!Number.isInteger(atomCount) || atomCount < 1 || !Number.isInteger(bondCount) || bondCount < 0 ||
      4 + atomCount + bondCount >= lines.length) return null
  const atoms: FragmentAtom[] = []
  const bonds: FragmentBond[] = []
  const chargeCodes = [0, 3, 2, 1, 0, -1, -2, -3]
  for (const line of lines.slice(4, 4 + atomCount)) {
    const atom = makeAtom(atoms.length, line.slice(31, 34).trim(), [line.slice(0, 10), line.slice(10, 20), line.slice(20, 30)],
      chargeCodes[Number(line.slice(36, 39))] || undefined)
    if (!atom) return null // Never skip a bad line and silently shift the remaining indices.
    atoms.push(atom)
  }
  const propertyStart = 4 + atomCount + bondCount
  for (const line of lines.slice(4 + atomCount, propertyStart)) {
    const type = Number(line.slice(6, 9))
    const bond = makeBond(Number(line.slice(0, 3)) - 1, Number(line.slice(3, 6)) - 1, type === 4 ? 1.5 : type, atomCount)
    if (!bond) return null
    bonds.push(bond)
  }
  let explicitCharges = false
  for (const line of lines.slice(propertyStart)) {
    if (/^M  END\s*$/.test(line)) return { atoms, bonds }
    if (!/^M  CHG\s/.test(line)) continue
    // An M CHG block supersedes atom-block charge codes for the entire record.
    if (!explicitCharges) {
      for (const atom of atoms) delete atom.charge
      explicitCharges = true
    }
    const [, , count, ...fields] = line.trim().split(/\s+/)
    const entryCount = Number(count)
    if (!Number.isInteger(entryCount) || entryCount < 1 || entryCount * 2 !== fields.length) return null
    for (let i = 0; i < entryCount; i++) {
      const atom = atoms[Number(fields[i * 2]) - 1]
      const charge = Number(fields[i * 2 + 1])
      if (!atom || !Number.isInteger(charge)) return null
      atom.charge = charge
    }
  }
  return null
}

function parseMol2(lines: string[]): Graph | null {
  const atoms: FragmentAtom[] = []
  const bonds: FragmentBond[] = []
  const atomIds = new Map<number, number>()
  let section = ''
  for (const line of lines) {
    const text = line.trim()
    if (!text || text.startsWith('#')) continue
    if (text.startsWith('@<TRIPOS>')) {
      section = text.slice(9)
      continue
    }
    const fields = text.split(/\s+/)
    if (section === 'ATOM') {
      const id = Number(fields[0])
      const type = fields[5]?.split('.')[0] ?? ''
      const atom = makeAtom(atoms.length, type, fields.slice(2, 5))
      if (!atom || !Number.isSafeInteger(id) || id < 1 || atomIds.has(id)) return null
      atomIds.set(id, atom.index)
      atoms.push(atom)
    } else if (section === 'BOND') {
      // An amide is a single bond; nc means explicitly not connected.
      if (fields[3] === 'nc') continue
      const order = fields[3] === 'ar' ? 1.5 : fields[3] === 'am' ? 1 : Number(fields[3])
      const bond = makeBond(atomIds.get(Number(fields[1])), atomIds.get(Number(fields[2])), order, atoms.length)
      if (!bond) return null
      bonds.push(bond)
    }
  }
  return atoms.length ? { atoms, bonds } : null
}

const COVALENT_RADIUS: Record<string, number> = {
  H: 0.31, B: 0.84, C: 0.76, N: 0.71, O: 0.66, F: 0.57, Si: 1.11,
  P: 1.07, S: 1.05, Cl: 1.02, Br: 1.2, I: 1.39
}

function inferBonds(atoms: FragmentAtom[]): FragmentBond[] {
  // Limit proximity checks to nearby cells even for large uploaded PDB files.
  const cells = new Map<string, FragmentAtom[]>()
  const bonds: FragmentBond[] = []
  for (const atom of atoms) {
    const radius = COVALENT_RADIUS[atom.element]
    if (!radius) continue
    const x = Math.floor(atom.x / 3.3)
    const y = Math.floor(atom.y / 3.3)
    const z = Math.floor(atom.z / 3.3)
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        for (let dz = -1; dz <= 1; dz++) {
          for (const other of cells.get(`${x + dx},${y + dy},${z + dz}`) ?? []) {
            const distance = Math.hypot(atom.x - other.x, atom.y - other.y, atom.z - other.z)
            if (distance >= 0.4 && distance <= radius + COVALENT_RADIUS[other.element]! + 0.45) {
              bonds.push({ a: other.index, b: atom.index, order: 1 })
            }
          }
        }
      }
    }
    const key = `${x},${y},${z}`
    if (!cells.has(key)) cells.set(key, [])
    cells.get(key)!.push(atom)
  }
  return bonds
}

function parsePdb(lines: string[]): Graph | null {
  const atoms: FragmentAtom[] = []
  const serials = new Map<number, number>()
  let firstModelEnded = false
  const conect: string[] = []
  for (const line of lines) {
    const record = line.slice(0, 6).trim()
    if (record === 'CONECT') {
      conect.push(line)
    } else if (record === 'ENDMDL' || record === 'END') {
      firstModelEnded = true
    } else if (!firstModelEnded && (record === 'ATOM' || record === 'HETATM')) {
      const alternate = line[16]
      if (alternate !== ' ' && alternate !== 'A' && alternate !== '1') continue
      const serial = Number(line.slice(6, 11))
      const atomName = line.slice(12, 16)
      const inferredSymbol = atomName.startsWith(' ') ? atomName.trim()[0] : atomName.trim().replace(/^\d+/, '').match(/^[A-Za-z]{1,2}/)?.[0]
      const chargeField = line.slice(78, 80).trim()
      const charge = /^\d[+-]$/.test(chargeField) ? Number(chargeField[0]) * (chargeField[1] === '-' ? -1 : 1) : undefined
      const atom = makeAtom(atoms.length, line.slice(76, 78).trim() || inferredSymbol || '',
        [line.slice(30, 38), line.slice(38, 46), line.slice(46, 54)], charge)
      if (!atom || !Number.isInteger(serial) || serials.has(serial)) return null
      serials.set(serial, atom.index)
      atoms.push(atom)
    }
  }
  if (!atoms.length) return null
  if (!conect.length) return { atoms, bonds: inferBonds(atoms) }

  const unique = new Map<string, FragmentBond>()
  for (const line of conect) {
    const a = serials.get(Number(line.slice(6, 11)))
    if (a === undefined) continue
    const partners = new Map<number, number>()
    // Only the four covalent-partner columns; later columns denote other interactions.
    for (let offset = 11; offset < 31 && offset < line.length; offset += 5) {
      const field = line.slice(offset, offset + 5).trim()
      const b = field ? serials.get(Number(field)) : undefined
      if (b !== undefined && a !== b) partners.set(b, (partners.get(b) ?? 0) + 1)
    }
    for (const [b, count] of partners) {
      const key = `${Math.min(a, b)},${Math.max(a, b)}`
      const order = Math.min(count, 3)
      if ((unique.get(key)?.order ?? 0) < order) unique.set(key, { a, b, order })
    }
  }
  return { atoms, bonds: [...unique.values()] }
}

// Jacobi rotations of the symmetric 3×3 covariance matrix give orthogonal
// principal axes, including for rank-deficient projections (lines or points).
type Vec3 = [number, number, number]
type Axis = 0 | 1 | 2

function principalAxes(centered: Vec3[]): Vec3[] {
  const axes: [Vec3, Vec3, Vec3] = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
  const dimensions: [Axis, Axis, Axis] = [0, 1, 2]
  const covarianceRow = (i: Axis): Vec3 => {
    const entry = (j: Axis) => centered.reduce((sum, p) => sum + p[i] * p[j], 0)
    return [entry(0), entry(1), entry(2)]
  }
  const covariance: [Vec3, Vec3, Vec3] = [covarianceRow(0), covarianceRow(1), covarianceRow(2)]
  const pairs = [[0, 1], [0, 2], [1, 2]] as const
  for (let sweep = 0; sweep < 12; sweep++) {
    for (const [i, j] of pairs) {
      const offDiagonal = covariance[i][j]
      if (Math.abs(offDiagonal) <= Number.EPSILON * (Math.abs(covariance[i][i]) + Math.abs(covariance[j][j]))) continue
      const angle = 0.5 * Math.atan2(2 * offDiagonal, covariance[i][i] - covariance[j][j])
      const c = Math.cos(angle)
      const s = Math.sin(angle)
      for (const matrix of [covariance, axes]) {
        for (const row of matrix) {
          const [a, b] = [row[i], row[j]]
          row[i] = c * a + s * b
          row[j] = -s * a + c * b
        }
      }
      for (const k of dimensions) {
        const a = covariance[i][k]
        const b = covariance[j][k]
        covariance[i][k] = c * a + s * b
        covariance[j][k] = -s * a + c * b
      }
    }
  }
  dimensions.sort((i, j) => covariance[j][j] - covariance[i][i])
  return dimensions.map(i => [axes[0][i], axes[1][i], axes[2][i]])
}

function project(atoms: FragmentAtom[]): void {
  const [sumX, sumY, sumZ] = atoms.reduce<Vec3>((sum, atom) => [sum[0] + atom.x, sum[1] + atom.y, sum[2] + atom.z], [0, 0, 0])
  const n = atoms.length
  const centered = atoms.map<Vec3>(({ x, y, z }) => [x - sumX / n, y - sumY / n, z - sumZ / n])
  const axes = centered.some(p => Math.abs(p[2]) > 1e-8) ? principalAxes(centered) : [[1, 0, 0], [0, 1, 0]] as Vec3[]
  const dot = (p: Vec3, v: Vec3) => p[0] * v[0] + p[1] * v[1] + p[2] * v[2]
  const xy = centered.map((p): [number, number] => [dot(p, axes[0]!), dot(p, axes[1]!)])
  const [left, right, bottom, top] = xy.reduce<[number, number, number, number]>(([l, r, b, t], [x, y]) =>
    [Math.min(l, x), Math.max(r, x), Math.min(b, y), Math.max(t, y)], [Infinity, -Infinity, Infinity, -Infinity])
  const span = Math.max(right - left, top - bottom) || 1
  atoms.forEach((atom, index) => {
    const [x, y] = xy[index]!
    atom.x2d = 0.5 + (x - (left + right) / 2) / span
    atom.y2d = 0.5 - (y - (bottom + top) / 2) / span
  })
}

export function parseFragmentMolecule(rawText: string, filename: string): FragmentMolecule | null {
  const suffix = filename.split('.').pop()?.toLowerCase()
  const format = suffix === 'sd' ? 'sdf' : suffix
  if (format !== 'sdf' && format !== 'mol' && format !== 'mol2' && format !== 'pdb') return null
  const lines = rawText.replace(/^﻿/, '').split(/\r?\n/)
  let graph: Graph | null
  let title = ''
  if (format === 'mol2') {
    const start = lines.findIndex(line => line.trim() === '@<TRIPOS>MOLECULE')
    const end = start < 0 ? -1 : lines.findIndex((line, i) => i > start && line.trim() === '@<TRIPOS>MOLECULE')
    title = start < 0 ? '' : lines[start + 1]?.trim() ?? ''
    graph = parseMol2(lines.slice(start + 1, end < 0 ? undefined : end))
  } else if (format === 'pdb') {
    graph = parsePdb(lines)
  } else {
    const end = lines.findIndex(line => line.trim() === '$$$$')
    graph = parseMolfile(lines.slice(0, end < 0 ? undefined : end))
    title = lines[0]?.trim() ?? ''
  }
  if (!graph) return null
  project(graph.atoms)
  return { name: title || filename.replace(/\.[^.]+$/, ''), format, rawText, ...graph }
}

function adjacency(mol: FragmentMolecule): number[][] {
  const neighbors: number[][] = mol.atoms.map(() => [])
  for (const { a, b } of mol.bonds) {
    neighbors[a]?.push(b)
    neighbors[b]?.push(a)
  }
  return neighbors
}

function sortedUnique(indices: number[]): number[] {
  return [...new Set(indices)].sort((a, b) => a - b)
}

export function findRingAtomIndices(mol: FragmentMolecule, seedIndex: number): number[] {
  const neighbors = adjacency(mol)
  const roots = neighbors[seedIndex]
  if (!roots) return []
  if (roots.length < 2) return [seedIndex]
  // A shortest cycle through the seed is a shortest path between two different
  // seed neighbors in the graph with the seed removed. Meet BFS fronts to find it.
  const queue = sortedUnique(roots)
  const owner = new Map(queue.map(i => [i, i]))
  const parent = new Map<number, number>()
  const depth = new Map(queue.map(i => [i, 0]))
  let best: [number, number] | undefined
  let length = Infinity
  for (let head = 0; head < queue.length; head++) {
    const a = queue[head]!
    for (const b of neighbors[a]!) {
      if (b === seedIndex) continue
      if (!owner.has(b)) {
        owner.set(b, owner.get(a)!)
        parent.set(b, a)
        depth.set(b, depth.get(a)! + 1)
        queue.push(b)
      } else if (owner.get(b) !== owner.get(a)) {
        const candidate = depth.get(a)! + depth.get(b)! + 1
        if (candidate < length) {
          length = candidate
          best = [a, b]
        }
      }
    }
  }
  const ring = [seedIndex]
  for (const end of best ?? []) {
    for (let i: number | undefined = end; i !== undefined; i = parent.get(i)) ring.push(i)
  }
  return sortedUnique(ring)
}

export function findConnectedComponent(mol: FragmentMolecule, seedIndex: number): number[] {
  const neighbors = adjacency(mol)
  if (!neighbors[seedIndex]) return []
  const queue = [seedIndex]
  const visited = new Set(queue)
  for (let head = 0; head < queue.length; head++) {
    for (const index of neighbors[queue[head]!]!) {
      if (!visited.has(index)) {
        visited.add(index)
        queue.push(index)
      }
    }
  }
  return queue.sort((a, b) => a - b)
}

export function exportSelectedFragmentSdf(mol: FragmentMolecule, selectedIndices: number[], originalFilename?: string): File {
  const indices = sortedUnique(selectedIndices)
  if (!indices.length) throw new Error('Select at least one atom to export a fragment.')
  if (indices.some(i => !Number.isInteger(i) || i < 0 || i >= mol.atoms.length)) {
    throw new Error('Selected atom index is outside the molecule.')
  }
  const position = new Map(indices.map((index, i) => [index, i + 1]))
  const bonds = mol.bonds.filter(({ a, b }) => position.has(a) && position.has(b))
  if (indices.length > 999 || bonds.length > 999) throw new Error('V2000 supports at most 999 atoms and 999 bonds.')
  const width3 = (value: number) => String(value).padStart(3)
  const coordinate = (value: number) => {
    const text = value.toFixed(4)
    if (text.length > 10 || !/^[-\d.]+$/.test(text)) throw new Error('Coordinate exceeds the V2000 field width.')
    return text.padStart(10)
  }
  const lines = [mol.name.replace(/[\r\n]+/g, ' '), '  Fragment          3D', '', `${width3(indices.length)}${width3(bonds.length)}  0  0  0  0  0  0  0  0999 V2000`]
  const charges: string[] = []
  for (const index of indices) {
    const { element, x, y, z, charge } = mol.atoms[index]!
    lines.push(`${coordinate(x)}${coordinate(y)}${coordinate(z)} ${element.padEnd(3)} 0  0  0  0  0  0  0  0  0  0  0  0`)
    if (charge) charges.push(`${String(position.get(index)).padStart(4)}${String(charge).padStart(4)}`)
  }
  for (const { a, b, order } of bonds) {
    lines.push(`${width3(position.get(a)!)}${width3(position.get(b)!)}${width3(order === 1.5 ? 4 : order)}  0  0  0  0`)
  }
  for (let i = 0; i < charges.length; i += 8) {
    const entries = charges.slice(i, i + 8)
    lines.push(`M  CHG${width3(entries.length)}${entries.join('')}`)
  }
  lines.push('M  END', '$$$$', '')
  const basename = (originalFilename || mol.name).split(/[/\\]/).pop()?.replace(/\.(sdf|sd|mol|mol2|pdb)$/i, '') || 'ligand'
  return new File([lines.join('\n')], `${basename}_fragment.sdf`, { type: 'chemical/x-mdl-sdfile' })
}

export function formatAtomIndices(indices: number[]): string {
  return sortedUnique(indices).join(' ')
}

export function parseAtomIndices(text: string, atomCount: number | null): { valid: boolean; indices: number[] } {
  const value = text.trim()
  if (!value) return { valid: true, indices: [] }
  if (!/^\d+(?:(?:\s*,\s*|\s+)\d+)*$/.test(value)) return { valid: false, indices: [] }
  const indices = value.split(/[\s,]+/).map(Number)
  if (indices.some(i => !Number.isSafeInteger(i) || (atomCount !== null && i >= atomCount))) {
    return { valid: false, indices: [] }
  }
  return { valid: true, indices: sortedUnique(indices) }
}
