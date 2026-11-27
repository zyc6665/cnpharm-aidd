import { describe, expect, it } from 'vitest'
import {
  exportSelectedFragmentSdf, findConnectedComponent, findRingAtomIndices, formatAtomIndices,
  parseAtomIndices, parseFragmentMolecule
} from './fragment-graph'

const planarSdf = `Example
  Fragment          2D

  3  2  0  0  0  0  0  0  0  0999 V2000
    1.0000    2.0000    0.0000 O   0  5  0  0  0  0  0  0  0  0  0  0
    2.0000    3.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    3.0000    1.0000    0.0000 N   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  2  0
M  CHG  1   3   1
M  END
$$$$
`

const mol2 = `@<TRIPOS>MOLECULE
Mol2 example
 4 3 0 0 0
SMALL
USER_CHARGES
@<TRIPOS>ATOM
7 N1 0 0 0 N.ar 1 LIG -0.22
2 C2 0 0 1 C.ar 1 LIG 0.12
4 O1 0 1 1 O.2 1 LIG -0.15
8 C1 0 1 0 C.3 1 LIG 0.25
@<TRIPOS>BOND
1 7 2 ar
2 2 4 2
3 4 8 am
`

const pdb = `MODEL        1
HETATM   12  C1  UNL A   1      22.000   5.000  52.000  1.00  0.00           C
HETATM   14  O1  UNL A   1      23.200   5.000  52.000  1.00  0.00           O
HETATM    4  N1  UNL A   1      26.000   5.000  52.000  1.00  0.00           N1+
ENDMDL
MODEL        2
HETATM   12  C1  UNL A   1      21.000   5.000  52.000  1.00  0.00           C
ENDMDL
`

function readFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(file)
  })
}

describe('parseFragmentMolecule', () => {
  it('keeps first-record V2000 order, exact coordinates and formal charges', () => {
    const input = (planarSdf + planarSdf.replace('Example', 'Another')).replace(/\n/g, '\r\n')
    const mol = parseFragmentMolecule(input, 'example.SDF')!
    expect(mol).toMatchObject({ name: 'Example', format: 'sdf', rawText: input })
    expect(mol.atoms.map(({ index, element, charge }) => [index, element, charge])).toEqual([
      [0, 'O', undefined], [1, 'C', undefined], [2, 'N', 1]
    ])
    expect(parseFragmentMolecule(planarSdf.replace('M  CHG  1   3   1\n', ''), 'example.sdf')?.atoms[0]?.charge).toBe(-1)
    expect(mol.atoms[0]).toMatchObject({ x: 1, y: 2, z: 0, x2d: 0, y2d: 0.5, isHetero: true })
    expect(mol.atoms[1]).toMatchObject({ x2d: 0.5, y2d: 0, isHetero: false })
    expect(mol.bonds).toEqual([{ a: 0, b: 1, order: 1 }, { a: 1, b: 2, order: 2 }])
    expect(parseFragmentMolecule(planarSdf.replace('$$$$\n', ''), 'example.mol')?.format).toBe('mol')
  })

  it('uses MOL2 file order rather than IDs and projects an out-of-plane square', () => {
    const mol = parseFragmentMolecule(mol2 + mol2, 'example.mol2')!
    expect(mol.atoms.map(atom => atom.element)).toEqual(['N', 'C', 'O', 'C'])
    expect(mol.atoms[0]?.charge).toBeUndefined() // Partial MOL2 charge is not a formal charge.
    expect(mol.bonds).toEqual([{ a: 0, b: 1, order: 1.5 }, { a: 1, b: 2, order: 2 }, { a: 2, b: 3, order: 1 }])
    const distance = (a: number, b: number) => {
      const from = mol.atoms[a]!
      const to = mol.atoms[b]!
      return Math.hypot(from.x2d - to.x2d, from.y2d - to.y2d)
    }
    expect(distance(0, 1)).toBeCloseTo(1)
    expect(distance(0, 3)).toBeCloseTo(1)
    expect(distance(0, 2)).toBeCloseTo(Math.SQRT2)
  })

  it('keeps PDB atom order, applying explicit connectivity or distance inference only when absent', () => {
    const explicit = parseFragmentMolecule(pdb + 'CONECT   12    4    4\nCONECT    4   12\nEND\n', 'ligand.pdb')!
    expect(explicit.atoms.map(({ element, charge }) => [element, charge])).toEqual([['C', undefined], ['O', undefined], ['N', 1]])
    expect(explicit.atoms[0]?.x).toBe(22)
    expect(explicit.bonds).toEqual([{ a: 0, b: 2, order: 2 }])
    expect(parseFragmentMolecule(pdb, 'ligand.pdb')?.bonds).toEqual([{ a: 0, b: 1, order: 1 }])
  })

  it('parses V3000 CTAB records with formal charges, aromatic bonds, and line continuation', () => {
    const v3000Sdf = `V3000Example
  RDKit          3D

  0  0  0     0  0            999 V3000
M  V30 BEGIN CTAB
M  V30 COUNTS 3 2 0 0 0
M  V30 BEGIN ATOM
M  V30 10 O 1.0 2.0 0.0 0 -
M  V30 CHG=-1
M  V30 20 C 2.0 3.0 0.0 0
M  V30 30 N 3.0 1.0 0.0 0 CHG=+1
M  V30 END ATOM
M  V30 BEGIN BOND
M  V30 1 4 10 20
M  V30 2 5 20 30
M  V30 END BOND
M  V30 END CTAB
M  END
$$$$
`
    const mol = parseFragmentMolecule(v3000Sdf, 'v3000.sdf')!
    expect(mol).not.toBeNull()
    expect(mol.name).toBe('V3000Example')
    expect(mol.atoms.map(({ index, element, charge }) => [index, element, charge])).toEqual([
      [0, 'O', -1],
      [1, 'C', undefined],
      [2, 'N', 1],
    ])
    expect(mol.bonds).toEqual([
      { a: 0, b: 1, order: 1.5 },
      { a: 1, b: 2, order: 1 },
    ])
  })

  it('rejects unsupported files and malformed records rather than shifting atom indices', () => {
    expect(parseFragmentMolecule(planarSdf, 'example.txt')).toBeNull()
    expect(parseFragmentMolecule(planarSdf.replace('V2000', 'V3000'), 'example.sdf')).toBeNull()
    expect(parseFragmentMolecule(planarSdf.replace('    1.0000', '          '), 'example.sdf')).toBeNull()
    expect(parseFragmentMolecule(planarSdf.replace('  1  2  1  0', '  1  4  1  0'), 'example.sdf')).toBeNull()
  })
})

describe('fragment selection', () => {
  it('finds the shortest cycle, even when a longer cycle shares the seed', () => {
    const input = mol2.replace('4 3 0 0 0', '6 7 0 0 0')
      .replace('@<TRIPOS>BOND', '9 S1 1 1 1 S.3\n10 Cl1 9 8 7 Cl\n@<TRIPOS>BOND')
      + '4 8 7 1\n5 2 8 1\n6 4 9 1\n'
    const mol = parseFragmentMolecule(input, 'example.mol2')!
    expect(findRingAtomIndices(mol, 0)).toEqual([0, 1, 3])
    expect(findRingAtomIndices(mol, 4)).toEqual([4])
    expect(findConnectedComponent(mol, 4)).toEqual([0, 1, 2, 3, 4])
    expect(findConnectedComponent(mol, 5)).toEqual([5])
    expect(findConnectedComponent(mol, -1)).toEqual([])
  })

  it('writes a re-indexed SDF in file order with original coordinates and charges', async () => {
    const original = parseFragmentMolecule(planarSdf, 'example.sdf')!
    const file = exportSelectedFragmentSdf(original, [2, 1, 2], 'parent.mol')
    expect(file.name).toBe('parent_fragment.sdf')
    const text = await readFile(file)
    expect(text.endsWith('M  END\n$$$$\n')).toBe(true)
    const exported = parseFragmentMolecule(text, file.name)!
    expect(exported.atoms.map(({ index, x, y, z, element, charge }) => [index, x, y, z, element, charge])).toEqual([
      [0, 2, 3, 0, 'C', undefined], [1, 3, 1, 0, 'N', 1]
    ])
    expect(exported.bonds).toEqual([{ a: 0, b: 1, order: 2 }])
    expect(() => exportSelectedFragmentSdf(original, [])).toThrow('Select at least one atom')
    expect(() => exportSelectedFragmentSdf(original, [3])).toThrow('outside the molecule')
  })

  it('accepts whitespace/comma-separated zero-based indices and checks bounds', () => {
    expect(formatAtomIndices([4, 0, 4, 2])).toBe('0 2 4')
    expect(parseAtomIndices(' 4, 0\t2 4 ', 5)).toEqual({ valid: true, indices: [0, 2, 4] })
    expect(parseAtomIndices('', 0)).toEqual({ valid: true, indices: [] })
    expect(parseAtomIndices('48', null)).toEqual({ valid: true, indices: [48] })
    for (const bad of ['-1', '1,,2', '1,', '1.5', '5', '9007199254740992', '0x3']) {
      expect(parseAtomIndices(bad, 5)).toEqual({ valid: false, indices: [] })
    }
  })
})
