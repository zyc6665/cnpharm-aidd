import { describe, expect, it } from 'vitest'
import {
  extractProteinHetatmPocketGeometry,
  parsePocketGeometry,
  parseReferenceLigandGeometry
} from './pocket-geometry'

describe('pocket-geometry', () => {
  it('prefers UNL marker atoms over protein CA or ATOM records', () => {
    const pdb = [
      'ATOM      1  CA  ALA A   1      10.000  10.000  10.000  1.00  0.00           C',
      'HETATM    2  C1  UNL A   1       0.000   2.000   4.000  1.00  0.00           C',
      'HETATM    3  C2  UNL A   1       2.000   6.000   8.000  1.00  0.00           C',
      'END'
    ].join('\n')
    const geometry = parsePocketGeometry(pdb)
    expect(geometry).toEqual({
      center: { x: 1, y: 4, z: 6 },
      boxSize: { x: 2, y: 4, z: 4 },
      pointCount: 2,
      source: 'unl'
    })
  })

  it('extracts co-crystal non-solvent HETATM ligand geometry while ignoring waters and hydrogens', () => {
    const pdb = [
      'ATOM      1  CA  GLY A   1      50.000  50.000  50.000  1.00  0.00           C',
      'HETATM    2  C1  IRE A 201      10.000  20.000  30.000  1.00  0.00           C',
      'HETATM    3  N1  IRE A 201      14.000  24.000  36.000  1.00  0.00           N',
      'HETATM    4  H1  IRE A 201      99.000  99.000  99.000  1.00  0.00           H',
      'HETATM    5  O   HOH A 301      80.000  80.000  80.000  1.00  0.00           O',
      'END'
    ].join('\n')
    const geometry = extractProteinHetatmPocketGeometry(pdb)
    expect(geometry).toEqual({
      center: { x: 12, y: 22, z: 33 },
      boxSize: { x: 4, y: 4, z: 6 },
      pointCount: 2,
      source: 'hetatm'
    })
  })

  it('selects the largest non-cofactor ligand residue instead of averaging additives, metals, or cofactors', () => {
    const pdb = [
      'HETATM    1  C1  IRE A 201      10.000  20.000  30.000  1.00  0.00           C',
      'HETATM    2  N1  IRE A 201      14.000  24.000  36.000  1.00  0.00           N',
      'HETATM    3  C2  IRE A 201      12.000  22.000  33.000  1.00  0.00           C',
      // Alternate conformer B should be skipped so weights aren't doubled on conformer A
      'HETATM    4  C2 BIRE A 201      99.000  99.000  99.000  0.50  0.00           C',
      // Crystallization buffer / additive
      'HETATM    5  C1  GOL A 301      60.000  60.000  60.000  1.00  0.00           C',
      'HETATM    6  O1  GOL A 301      62.000  62.000  62.000  1.00  0.00           O',
      // Cofactor larger than ligand: should not override drug ligand
      'HETATM    7  PA  NAD A 501      80.000  80.000  80.000  1.00  0.00           P',
      'HETATM    8  O1A NAD A 501      82.000  82.000  82.000  1.00  0.00           O',
      'HETATM    9  O2A NAD A 501      84.000  84.000  84.000  1.00  0.00           O',
      'HETATM   10  PN  NAD A 501      86.000  86.000  86.000  1.00  0.00           P',
      'END'
    ].join('\n')
    const geometry = extractProteinHetatmPocketGeometry(pdb)
    expect(geometry).toEqual({
      center: { x: 12, y: 22, z: 33 },
      boxSize: { x: 4, y: 4, z: 6 },
      pointCount: 3,
      source: 'hetatm'
    })
  })

  it('does not average multiple chains of the same ligand and keeps HG heavy atoms while dropping H atoms', () => {
    const pdb = [
      'HETATM    1  C1  LIG A 201       0.000   0.000   0.000  1.00  0.00           C',
      'HETATM    2  HG1 LIG A 201       4.000   4.000   4.000  1.00  0.00          HG',
      'HETATM    3  C1  LIG B 201     100.000 100.000 100.000  1.00  0.00           C',
      'HETATM    4  O1  LIG B 201     102.000 102.000 102.000  1.00  0.00           O',
      'END'
    ].join('\n')
    const geometry = extractProteinHetatmPocketGeometry(pdb)
    expect(geometry).toEqual({
      center: { x: 2, y: 2, z: 2 },
      boxSize: { x: 4, y: 4, z: 4 },
      pointCount: 2,
      source: 'hetatm'
    })
  })

  it('returns null when PDB only has solvent or a single isolated HETATM ion', () => {
    const pdb = [
      'HETATM    1 ZN   ZN  A 401      10.000  10.000  10.000  1.00  0.00          ZN',
      'HETATM    2  O   HOH A 402      20.000  20.000  20.000  1.00  0.00           O',
      'END'
    ].join('\n')
    expect(extractProteinHetatmPocketGeometry(pdb)).toBeNull()
  })

  it('parses 3D coordinates from SDF reference ligands and ignores explicit hydrogens', () => {
    const sdf = [
      'Ligand',
      '  RDKit          3D',
      '',
      '  3  2  0  0  0  0  0  0  0  0999 V2000',
      '    2.0000    4.0000    6.0000 C   0  0  0  0  0  0  0  0  0  0  0  0',
      '    6.0000    8.0000   10.0000 O   0  0  0  0  0  0  0  0  0  0  0  0',
      '  100.0000  100.0000  100.0000 H   0  0  0  0  0  0  0  0  0  0  0  0',
      '  1  2  1  0',
      '  2  3  1  0',
      'M  END',
      '$$$$',
      ''
    ].join('\n')
    const geometry = parseReferenceLigandGeometry(sdf, 'ref.sdf')
    expect(geometry).toEqual({
      center: { x: 4, y: 6, z: 8 },
      boxSize: { x: 4, y: 4, z: 4 },
      pointCount: 2,
      source: 'ligand'
    })
  })
})
